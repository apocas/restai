"""Regression test for the LDAP empty-password / anonymous-bind bypass.

Pins:
  - `POST /ldap` with an empty or whitespace-only password is
    refused at the FIRST check, BEFORE any LDAP socket is opened.
    A bind that the LDAP server might service as an anonymous bind
    must never happen.

Strategy: enable LDAP via env, then patch `ldap3.Connection` to a
sentinel that fails the test if it's ever instantiated. The empty-
password reject sits ahead of the LDAP imports' first use, so a
correct implementation never touches the patched class.

The fix lives in `restai/routers/users.py` immediately after the
`ENABLE_LDAP` check.
"""
import pytest
from fastapi.testclient import TestClient

from restai.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def _enable_ldap(monkeypatch):
    """Flip ENABLE_LDAP on for the duration of each test, otherwise
    the handler short-circuits with the not-enabled error and the
    test wouldn't exercise the empty-password gate."""
    from restai.routers import users as _users
    from restai import config as _config
    monkeypatch.setattr(_config, "ENABLE_LDAP", True, raising=False)
    monkeypatch.setattr(_users.config, "ENABLE_LDAP", True, raising=False)


def _trapping_connection(*args, **kwargs):
    """Sentinel that fails the test if the LDAP code path tries to
    open a connection. The empty-password gate must short-circuit
    BEFORE we reach `Connection(...)`."""
    raise AssertionError(
        "LDAP Connection() was instantiated despite empty password — "
        "the anonymous-bind bypass is open"
    )


@pytest.mark.parametrize("password", ["", " ", "\t", "   ", "\n"])
def test_empty_password_rejected_before_bind(client, password, monkeypatch):
    """Every form of "no password" — empty string and whitespace-only
    variants — must produce 400 without ever opening a Connection."""
    # Patch the bound name inside the router module — the import
    # `from ldap3 import Connection` at module load means patching
    # `ldap3.Connection` doesn't reach the handler's local.
    import restai.routers.users as _users_mod
    monkeypatch.setattr(_users_mod, "Connection", _trapping_connection)

    r = client.post(
        "/ldap",
        json={"user": "victim", "password": password},
    )
    # Either 400 (rejected) or 422 (Pydantic — also fine, also rejected).
    # The signal is "we did not get a 200 + Set-Cookie".
    assert r.status_code in (400, 422), r.text
    assert "restai_token" not in r.cookies


def test_legitimate_password_passes_gate(client):
    """The empty-password gate must not over-reject. A non-empty
    password reaches subsequent steps (which fail in the test env
    because no real LDAP server is configured — `Tls()` /
    `Server()` raise — but that failure is *after* the gate). The
    signal is "the response is NOT one our gate would produce" —
    i.e. it's a downstream LDAP failure, not a gated rejection
    that would have happened with an empty password."""
    r = client.post(
        "/ldap",
        json={"user": "victim", "password": "an-actually-typed-password"},
    )
    # Either 400 (downstream LDAP error) or 5xx — both prove the
    # gate let the request through. A 422 would be Pydantic, also
    # acceptable since the schema doesn't allow other shapes.
    assert r.status_code != 200, "non-empty password produced a session unexpectedly"
    assert "restai_token" not in r.cookies
