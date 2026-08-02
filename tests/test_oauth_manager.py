"""Unit tests for restai/integrations/oauth.py — OAuthManager provider
registration, login redirect, and the callback user-provisioning paths
(auto-restricted / auto-team / github email fallback), with authlib and
aiohttp fully mocked."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException
from starlette.responses import RedirectResponse, Response

import restai.config as rconfig
import restai.integrations.oauth as oauth_mod
from restai.integrations.oauth import OAuthManager


def _providers(name="acme", **extra):
    cfg = {"register": MagicMock(), "redirect_uri": f"https://cb/{name}"}
    cfg.update(extra)
    return {name: cfg}


@pytest.fixture
def db():
    db = MagicMock()
    db.get_user_by_username.return_value = SimpleNamespace(
        username="user@example.com", is_suspended=False)
    return db


def _manager(monkeypatch, providers, db):
    monkeypatch.setattr(oauth_mod, "OAUTH_PROVIDERS", providers)
    return OAuthManager(app=MagicMock(), db_wrapper=db)


def _client(userinfo=None, token_extra=None):
    client = MagicMock()
    token = {"userinfo": userinfo}
    token.update(token_extra or {})
    client.authorize_access_token = AsyncMock(return_value=token)
    client.userinfo = AsyncMock(return_value=None)
    client.authorize_redirect = AsyncMock(return_value="redirected")
    return client


def _callback(manager, client, provider="acme"):
    manager.get_client = lambda name: client
    request = MagicMock()
    response = Response()
    result = asyncio.run(manager.handle_callback(request, provider, response))
    return result, response


# ─── registration ───────────────────────────────────────────────────────

def test_init_registers_each_provider(monkeypatch, db):
    providers = {**_providers("acme"), **_providers("beta")}
    manager = _manager(monkeypatch, providers, db)
    for cfg in providers.values():
        cfg["register"].assert_called_once_with(manager.oauth)


def test_reinit_reregisters_on_fresh_oauth(monkeypatch, db):
    providers = _providers("acme")
    manager = _manager(monkeypatch, providers, db)
    old_oauth = manager.oauth
    manager.reinit()
    assert manager.oauth is not old_oauth
    assert providers["acme"]["register"].call_count == 2
    assert providers["acme"]["register"].call_args.args == (manager.oauth,)


# ─── handle_login ───────────────────────────────────────────────────────

def test_login_unknown_provider_404(monkeypatch, db):
    manager = _manager(monkeypatch, _providers("acme"), db)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(manager.handle_login(MagicMock(), "nope"))
    assert exc.value.status_code == 404


def test_login_unregistered_client_404(monkeypatch, db):
    manager = _manager(monkeypatch, _providers("acme"), db)
    # register callback was a no-op mock → authlib has no client → None.
    with pytest.raises(HTTPException) as exc:
        asyncio.run(manager.handle_login(MagicMock(), "acme"))
    assert exc.value.status_code == 404


def test_login_redirects_with_configured_uri(monkeypatch, db):
    manager = _manager(monkeypatch, _providers("acme"), db)
    client = _client()
    manager.get_client = lambda name: client
    request = MagicMock()
    result = asyncio.run(manager.handle_login(request, "acme"))
    assert result == "redirected"
    client.authorize_redirect.assert_awaited_once_with(request, "https://cb/acme")
    request.url_for.assert_not_called()  # configured redirect_uri wins


# ─── handle_callback: failure paths ─────────────────────────────────────

def test_callback_unknown_provider_404(monkeypatch, db):
    manager = _manager(monkeypatch, _providers("acme"), db)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(manager.handle_callback(MagicMock(), "nope", Response()))
    assert exc.value.status_code == 404


def test_callback_token_exchange_failure_400(monkeypatch, db):
    manager = _manager(monkeypatch, _providers("acme"), db)
    client = _client()
    client.authorize_access_token = AsyncMock(side_effect=RuntimeError("bad state"))
    with pytest.raises(HTTPException) as exc:
        _callback(manager, client)
    assert exc.value.status_code == 400


def test_callback_missing_userinfo_400(monkeypatch, db):
    manager = _manager(monkeypatch, _providers("acme"), db)
    client = _client(userinfo=None)  # token has no userinfo, userinfo() → None
    with pytest.raises(HTTPException) as exc:
        _callback(manager, client)
    assert exc.value.status_code == 400


def test_callback_missing_sub_400(monkeypatch, db):
    manager = _manager(monkeypatch, _providers("acme"), db)
    client = _client(userinfo={"email": "a@b.com"})
    with pytest.raises(HTTPException) as exc:
        _callback(manager, client)
    assert exc.value.status_code == 400


def test_callback_missing_email_non_github_400(monkeypatch, db):
    manager = _manager(monkeypatch, _providers("acme"), db)
    client = _client(userinfo={"sub": "s1"})
    # userinfo endpoint fallback also lacks the email claim.
    client.userinfo = AsyncMock(return_value={"sub": "s1"})
    with pytest.raises(HTTPException) as exc:
        _callback(manager, client)
    assert exc.value.status_code == 400


def test_callback_userinfo_endpoint_fallback(monkeypatch, db):
    """When the token lacks userinfo, the client's userinfo endpoint is hit."""
    manager = _manager(monkeypatch, _providers("acme"), db)
    client = _client(userinfo=None)
    client.userinfo = AsyncMock(return_value={"sub": "s1", "email": "user@example.com"})
    result, _ = _callback(manager, client)
    assert isinstance(result, RedirectResponse)
    client.userinfo.assert_awaited_once()


def test_callback_domain_allowlist_rejects(monkeypatch, db):
    monkeypatch.setattr(rconfig, "OAUTH_ALLOWED_DOMAINS", ["good.com"], raising=False)
    manager = _manager(monkeypatch, _providers("acme"), db)
    client = _client(userinfo={"sub": "s1", "email": "user@evil.com"})
    with pytest.raises(HTTPException) as exc:
        _callback(manager, client)
    assert exc.value.status_code == 400


def test_callback_suspended_user_403(monkeypatch, db):
    db.get_user_by_username.return_value = SimpleNamespace(
        username="user@example.com", is_suspended=True)
    manager = _manager(monkeypatch, _providers("acme"), db)
    client = _client(userinfo={"sub": "s1", "email": "user@example.com"})
    with pytest.raises(HTTPException) as exc:
        _callback(manager, client)
    assert exc.value.status_code == 403


# ─── handle_callback: success + provisioning ────────────────────────────

def test_callback_existing_user_sets_cookie_and_redirects(monkeypatch, db):
    monkeypatch.setattr(rconfig, "RESTAI_URL", "myhost.example", raising=False)
    manager = _manager(monkeypatch, _providers("acme"), db)
    client = _client(userinfo={"sub": "s1", "email": "User@Example.COM"})
    result, response = _callback(manager, client)
    assert isinstance(result, RedirectResponse)
    # Bare host gets an https:// prefix.
    assert result.headers["location"] == "https://myhost.example/admin"
    cookie = response.headers.get("set-cookie", "")
    assert "restai_token=" in cookie
    assert "HttpOnly" in cookie
    # Email is lowercased before lookup.
    db.get_user_by_username.assert_called_once_with("user@example.com")


def test_callback_unknown_user_no_autocreate_403(monkeypatch, db):
    monkeypatch.setattr(rconfig, "AUTO_CREATE_USER", False, raising=False)
    db.get_user_by_username.return_value = None
    manager = _manager(monkeypatch, _providers("acme"), db)
    client = _client(userinfo={"sub": "s1", "email": "new@example.com"})
    with pytest.raises(HTTPException) as exc:
        _callback(manager, client)
    assert exc.value.status_code == 403
    db.create_user.assert_not_called()


def _autocreate_db(db, restricted="true", team_id=""):
    db.get_user_by_username.return_value = None
    db.create_user.return_value = SimpleNamespace(
        username="new@example.com", is_suspended=False)
    db.get_setting_value.side_effect = lambda key, default="": {
        "sso_auto_restricted": restricted,
        "sso_auto_team_id": team_id,
    }.get(key, default)


def test_callback_autocreates_restricted_user(monkeypatch, db):
    monkeypatch.setattr(rconfig, "AUTO_CREATE_USER", True, raising=False)
    _autocreate_db(db, restricted="true")
    manager = _manager(monkeypatch, _providers("acme"), db)
    client = _client(userinfo={"sub": "s1", "email": "new@example.com"})
    result, _ = _callback(manager, client)
    assert isinstance(result, RedirectResponse)
    db.create_user.assert_called_once_with(
        "new@example.com", None, False, False, restricted=True)
    db.add_user_to_team.assert_not_called()  # no auto-team configured


def test_callback_autocreate_unrestricted_when_setting_off(monkeypatch, db):
    monkeypatch.setattr(rconfig, "AUTO_CREATE_USER", True, raising=False)
    _autocreate_db(db, restricted="false")
    manager = _manager(monkeypatch, _providers("acme"), db)
    client = _client(userinfo={"sub": "s1", "email": "new@example.com"})
    _callback(manager, client)
    assert db.create_user.call_args.kwargs["restricted"] is False


def test_callback_autocreate_adds_to_auto_team(monkeypatch, db):
    monkeypatch.setattr(rconfig, "AUTO_CREATE_USER", True, raising=False)
    _autocreate_db(db, team_id="42")
    team = SimpleNamespace(id=42)
    db.get_team_by_id.return_value = team
    manager = _manager(monkeypatch, _providers("acme"), db)
    client = _client(userinfo={"sub": "s1", "email": "new@example.com"})
    _callback(manager, client)
    db.get_team_by_id.assert_called_once_with(42)
    db.add_user_to_team.assert_called_once_with(team, db.create_user.return_value)


def test_callback_autocreate_garbage_team_id_ignored(monkeypatch, db):
    monkeypatch.setattr(rconfig, "AUTO_CREATE_USER", True, raising=False)
    _autocreate_db(db, team_id="not-a-number")
    manager = _manager(monkeypatch, _providers("acme"), db)
    client = _client(userinfo={"sub": "s1", "email": "new@example.com"})
    result, _ = _callback(manager, client)
    assert isinstance(result, RedirectResponse)
    db.add_user_to_team.assert_not_called()


def test_callback_custom_sub_claim(monkeypatch, db):
    providers = _providers("acme", sub_claim="oid")
    manager = _manager(monkeypatch, providers, db)
    client = _client(userinfo={"oid": "obj-1", "email": "user@example.com"})
    result, _ = _callback(manager, client)
    assert isinstance(result, RedirectResponse)


# ─── github email fallback ──────────────────────────────────────────────

class _FakeAiohttpResp:
    def __init__(self, ok, data):
        self.ok = ok
        self._data = data

    async def json(self):
        return self._data


class _ACM:
    def __init__(self, obj):
        self._obj = obj

    async def __aenter__(self):
        return self._obj

    async def __aexit__(self, *a):
        return False


class _FakeSession:
    resp = None
    last_headers = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    def get(self, url, headers=None):
        _FakeSession.last_headers = headers
        return _ACM(_FakeSession.resp)


def _github_manager(monkeypatch, db):
    manager = _manager(monkeypatch, _providers("github"), db)
    monkeypatch.setattr(oauth_mod.aiohttp, "ClientSession", _FakeSession)
    client = _client(userinfo={"sub": "gh-1"}, token_extra={"access_token": "gh-token"})
    # Fallback userinfo endpoint also lacks the email claim → github branch.
    client.userinfo = AsyncMock(return_value={"sub": "gh-1"})
    return manager, client


def test_github_email_fallback_uses_primary(monkeypatch, db):
    manager, client = _github_manager(monkeypatch, db)
    _FakeSession.resp = _FakeAiohttpResp(True, [
        {"email": "secondary@example.com", "primary": False},
        {"email": "primary@example.com", "primary": True},
    ])
    result, _ = _callback(manager, client, provider="github")
    assert isinstance(result, RedirectResponse)
    db.get_user_by_username.assert_called_once_with("primary@example.com")
    assert _FakeSession.last_headers == {"Authorization": "Bearer gh-token"}


def test_github_email_fallback_no_primary_400(monkeypatch, db):
    manager, client = _github_manager(monkeypatch, db)
    _FakeSession.resp = _FakeAiohttpResp(True, [
        {"email": "secondary@example.com", "primary": False},
    ])
    with pytest.raises(HTTPException) as exc:
        _callback(manager, client, provider="github")
    assert exc.value.status_code == 400


def test_github_email_fallback_api_failure_400(monkeypatch, db):
    manager, client = _github_manager(monkeypatch, db)
    _FakeSession.resp = _FakeAiohttpResp(False, [])
    with pytest.raises(HTTPException) as exc:
        _callback(manager, client, provider="github")
    assert exc.value.status_code == 400
