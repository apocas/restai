import sys
sys.setrecursionlimit(50000)

# Force ALL Pydantic models to fully resolve their schemas in the main thread
# under the raised recursion limit. Without this, TestClient triggers schema
# resolution inside a thread pool where the recursion limit may not be sufficient.
import inspect
from restai.models import models as _models_module
from pydantic import BaseModel

for _name, _obj in inspect.getmembers(_models_module):
    if inspect.isclass(_obj) and issubclass(_obj, BaseModel) and _obj is not BaseModel:
        try:
            _obj.model_rebuild()
        except Exception:
            pass


# ─── Test-only auth shim ────────────────────────────────────────────────
# Production endpoints no longer accept HTTP Basic auth (security: the
# Basic path bypassed TOTP and `enforce_2fa`). The supported auth modes
# are now JWT cookie (humans) and Bearer API keys (programmatic).
#
# Tests across the suite rely on the convenience of `client.get(..., auth=
# (user, pwd))` Basic-tuple shorthand. To keep the tests unchanged, we
# monkey-patch `starlette.testclient.TestClient.request` so that when an
# `auth=tuple` is passed:
#
#   1. We login once via POST /auth/login (which still accepts Basic —
#      it's the only password-verification surface left, and it
#      enforces TOTP after a successful password check).
#   2. We cache the resulting JWT, scoped by (username, password).
#   3. We attach the JWT as a `restai_token` cookie on the actual
#      request and strip the `auth=` kwarg so httpx doesn't also send
#      a Basic header.
#
# Hitting `/auth/login` itself with `auth=tuple` passes through
# untouched. Bad credentials → no token → request continues without
# auth so the protected endpoint returns 401 naturally.
import base64
from starlette.testclient import TestClient as _StarletteTestClient


# Stub the login rate-limiter for the whole test session. Real prod
# behavior is "10 logins per 5 minutes per IP" (`routers/auth.py`),
# which is correct under real traffic but blows up in CI: a single
# `test_login_rate_limit.py` module fills the bucket, and every
# subsequent module that needs to log in a fresh user gets 429 →
# auth shim returns None → tests look like auth failures. The
# rate-limit module's own tests still hit `/auth/login` directly via
# `auth=tuple` against `/auth/login` (which the shim passes through
# untouched), so the limiter is exercised by those tests in
# isolation but skipped everywhere else.
import restai.routers.auth as _auth_router
_real_check_login_rate_limit = _auth_router._check_login_rate_limit


def _conditional_check_login_rate_limit(request, db_wrapper):
    if getattr(_auth_router, "_rate_limit_enabled_for_tests", False):
        return _real_check_login_rate_limit(request, db_wrapper)
    return None


_auth_router._check_login_rate_limit = _conditional_check_login_rate_limit
_auth_router._rate_limit_enabled_for_tests = False


_token_cache: dict[tuple[str, str], str] = {}
_original_request = _StarletteTestClient.request


def _login_for(self, auth: tuple[str, str]) -> str | None:
    """Return a cached JWT for `(user, pwd)`, or `None` on bad creds.

    Crucially, we do NOT touch the test client's shared cookie jar —
    a successful /auth/login response would otherwise persist
    `restai_token` in `self.cookies` and bleed across subsequent
    requests in the same test, which silently leaks admin auth into
    "should be 403" negative cases. We snapshot+restore the jar
    around the login call to keep the per-request cookie strictly
    scoped to one request.
    """
    cached = _token_cache.get(auth)
    if cached is not None:
        return cached

    saved = dict(self.cookies)
    try:
        r = _original_request(
            self,
            "POST",
            "/auth/login",
            headers={"Authorization": "Basic " + base64.b64encode(
                f"{auth[0]}:{auth[1]}".encode()
            ).decode()},
        )
        if r.status_code != 200:
            return None
        token = self.cookies.get("restai_token") or ""
    finally:
        # Restore exactly what was there before login.
        self.cookies.clear()
        for k, v in saved.items():
            self.cookies.set(k, v)

    if token:
        _token_cache[auth] = token
        return token
    return None


def _shim_request(self, method, url, *args, **kwargs):
    auth = kwargs.pop("auth", None)
    if (
        auth is not None
        and isinstance(auth, tuple)
        and len(auth) == 2
        and isinstance(auth[0], str)
        and isinstance(auth[1], str)
        and "/auth/login" not in str(url)
    ):
        token = _login_for(self, auth)
        # Whether or not we got a token, never re-send the Basic auth
        # tuple — production endpoints reject it. A failed login
        # (None) means the request goes through unauthenticated and
        # the endpoint responds 401 naturally, which is what negative
        # tests expect.
        if token:
            existing = kwargs.get("headers") or {}
            if isinstance(existing, dict):
                # Attach the cookie via a fresh Cookie header rather
                # than the cookies= kwarg or the shared jar — keeps
                # this request's auth strictly isolated.
                cookie_header = existing.get("Cookie") or existing.get("cookie") or ""
                cookie_pair = f"restai_token={token}"
                existing["Cookie"] = (
                    f"{cookie_header}; {cookie_pair}" if cookie_header else cookie_pair
                )
                kwargs["headers"] = existing
        return _original_request(self, method, url, *args, **kwargs)

    if auth is not None:
        kwargs["auth"] = auth
    return _original_request(self, method, url, *args, **kwargs)


_StarletteTestClient.request = _shim_request
