"""Router registration, static-file mounts, and the health/setup/info routes.

Extracted from `main.py`'s lifespan so the entry point stays readable. These
run at startup (inside lifespan) rather than at module import — that's an
intentional RESTai pattern (the DB/Brain must be ready first).

Registration ORDER is load-bearing: the SPA catch-all (`/admin/{path}`) must
register LAST so explicit API endpoints win Starlette's first-match routing.
`register_routers()` then `register_spa()` preserves that.
"""

from pathlib import Path
import logging

from fastapi import FastAPI, Depends
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles

from restai import config


PROJECT_ROOT = Path(__file__).parent.parent
FRONTEND_BUILD_DIR = PROJECT_ROOT / "frontend" / "build"
# When installed from PyPI, frontend may be bundled inside the package.
if not FRONTEND_BUILD_DIR.exists():
    _pkg_frontend = Path(__file__).parent.parent / "frontend" / "build"
    if _pkg_frontend.exists():
        FRONTEND_BUILD_DIR = _pkg_frontend

# Separate mobile PWA (CRA build), served at /mobile.
MOBILE_BUILD_DIR = PROJECT_ROOT / "mobile" / "build"
if not MOBILE_BUILD_DIR.exists():
    _pkg_mobile = Path(__file__).parent.parent / "mobile" / "build"
    if _pkg_mobile.exists():
        MOBILE_BUILD_DIR = _pkg_mobile

WIDGET_DIR = Path(__file__).parent / "widget"


def register_health_routes(fs_app: FastAPI) -> None:
    """Register the unauthenticated + admin health/setup/info endpoints."""
    from restai.database import get_db_wrapper, open_db_wrapper, DBWrapper
    from restai.auth import get_current_username
    from restai.models.models import User
    from modules.loaders import LOADERS

    @fs_app.get("/", tags=["Health"])
    async def get():
        from starlette.responses import RedirectResponse
        return RedirectResponse(url="/admin")

    @fs_app.get("/version", tags=["Health"])
    async def get_version(_: User = Depends(get_current_username)):
        import os as _os
        return {
            "version": fs_app.version,
            "telemetry": _os.environ.get("ANONYMIZED_TELEMETRY", "True").lower() == "true",
        }

    _update_cache = {"data": None, "ts": 0}

    @fs_app.get("/version/check", tags=["Health"])
    async def check_for_update(_: User = Depends(get_current_username)):
        # Cached for 1 hour.
        import time as _time
        import httpx
        from packaging.version import parse as parse_version

        current = fs_app.version
        now = _time.time()

        if _update_cache["data"] and (now - _update_cache["ts"]) < 3600:
            return _update_cache["data"]

        result = {
            "current": current,
            "latest": current,
            "update_available": False,
            "latest_url": "https://github.com/apocas/restai/releases",
        }

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    "https://api.github.com/repos/apocas/restai/releases/latest",
                    headers={"Accept": "application/vnd.github+json"},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    tag = data.get("tag_name", "").lstrip("v")
                    if tag:
                        result["latest"] = tag
                        result["latest_url"] = data.get("html_url", result["latest_url"])
                        result["update_available"] = parse_version(tag) > parse_version(current)
        except Exception:
            pass

        _update_cache["data"] = result
        _update_cache["ts"] = now
        return result

    @fs_app.get("/health/live", tags=["Health"])
    async def health_live():
        return {"status": "ok"}

    @fs_app.get("/health/ready", tags=["Health"])
    async def health_ready():
        health = {"status": "ok"}
        try:
            from sqlalchemy import text
            db_check = open_db_wrapper()
            db_check.db.execute(text("SELECT 1"))
            db_check.db.close()
            health["database"] = "ok"
        except Exception:
            health["database"] = "error"
            health["status"] = "degraded"

        if config.REDIS_HOST:
            try:
                import redis
                r = redis.Redis(
                    host=config.REDIS_HOST,
                    port=int(config.REDIS_PORT or 6379),
                    socket_connect_timeout=2,
                )
                r.ping()
                r.close()
                health["redis"] = "ok"
            except Exception:
                health["redis"] = "error"
                health["status"] = "degraded"

        if health["status"] != "ok":
            return JSONResponse(content=health, status_code=503)
        return health

    @fs_app.get("/setup", tags=["Health"])
    async def get_setup(
        db_wrapper: DBWrapper = Depends(get_db_wrapper),
    ):
        sso_list = []
        if isinstance(config.OAUTH_PROVIDERS, dict):
            sso_list = list(config.OAUTH_PROVIDERS.keys())
        elif isinstance(config.OAUTH_PROVIDERS, (list, tuple)):
            sso_list = list(config.OAUTH_PROVIDERS)
        else:
            sso_list = []
        sso_provider_names = {}
        for provider in sso_list:
            if provider == "oidc":
                sso_provider_names[provider] = config.OAUTH_PROVIDER_NAME or "SSO"
            else:
                sso_provider_names[provider] = provider.capitalize()

        _sv = db_wrapper.get_setting_value
        return {
            "sso": sso_list,
            "sso_provider_names": sso_provider_names,
            "proxy": bool(_sv("proxy_url")),
            "gpu": config.RESTAI_GPU,
            "app_name": _sv("app_name", "RESTai"),
            "logo_url": _sv("logo_url", ""),
            "hide_branding": _sv("hide_branding", "false").lower() in ("true", "1"),
            "proxy_url": _sv("proxy_url", ""),
            "currency": _sv("currency", "EUR"),
            "auth_disable_local": _sv("auth_disable_local", "false").lower() in ("true", "1"),
            "mcp": config.RESTAI_MCP,
            "enforce_2fa": _sv("enforce_2fa", "false").lower() in ("true", "1"),
            "app_builder": _sv("app_docker_enabled", "false").lower() in ("true", "1"),
            "payments_enabled": _sv("payment_enabled", "false").lower() in ("true", "1"),
            "payment_providers": [
                p for p in ("stripe", "paypal")
                if _sv(f"payment_{p}_enabled", "false").lower() in ("true", "1")
            ] if _sv("payment_enabled", "false").lower() in ("true", "1") else [],
            "stripe_publishable_key": _sv("payment_stripe_publishable_key", ""),
            # Intentionally NOT exposing `auth_secret_weak` here — this
            # endpoint is unauthenticated (used by the pre-login UI to
            # show SSO providers) and the weak-secret signal is a
            # reconnaissance aid for an attacker. Admins read it from
            # the authenticated /info endpoint instead.
        }

    @fs_app.get("/info", tags=["Health"])
    async def get_info(
        user: User = Depends(get_current_username),
        db_wrapper: DBWrapper = Depends(get_db_wrapper),
    ):
        from restai.vectordb.tools import get_available_vectorstores

        output = {
            "version": fs_app.version,
            "loaders": list(LOADERS.keys()),
            "embeddings": [],
            "llms": [],
            "vectorstores": get_available_vectorstores(),
            "system_llm_configured": bool(getattr(db_wrapper.get_setting("system_llm"), "value", None)),
            # Admin-only security signal. Non-admins always see False here
            # — they shouldn't know whether the instance is misconfigured.
            "auth_secret_weak": bool(getattr(fs_app.state, "auth_secret_weak", False)) if user.is_admin else False,
        }

        allowed_llm_names = None
        allowed_emb_names = None
        if not user.is_admin:
            allowed_llm_names = set()
            allowed_emb_names = set()
            for team in user.teams:
                for llm in (team.llms if hasattr(team, 'llms') and team.llms else []):
                    allowed_llm_names.add(llm.name if hasattr(llm, 'name') else llm)
                for emb in (team.embeddings if hasattr(team, 'embeddings') and team.embeddings else []):
                    allowed_emb_names.add(emb.name if hasattr(emb, 'name') else emb)

        db_llms = db_wrapper.get_llms()
        for llm in db_llms:
            if allowed_llm_names is not None and llm.name not in allowed_llm_names:
                continue
            output["llms"].append(
                {
                    "id": llm.id,
                    "name": llm.name,
                    "privacy": llm.privacy,
                    "description": llm.description,
                }
            )

        db_embeddings = db_wrapper.get_embeddings()
        for embedding in db_embeddings:
            if allowed_emb_names is not None and embedding.name not in allowed_emb_names:
                continue
            output["embeddings"].append(
                {
                    "id": embedding.id,
                    "name": embedding.name,
                    "privacy": embedding.privacy,
                    "description": embedding.description,
                }
            )
        return output


def register_static_mounts(fs_app: FastAPI):
    """Mount the admin SPA + mobile PWA static dirs + the widget script. Returns
    `(spa_build_dir, mobile_build_dir)` to hand to `register_spa()` later (each
    None when its build is missing), so the catch-alls register after all API
    routers."""
    try:
        fs_app.mount(
            "/admin/static",
            StaticFiles(directory=str(FRONTEND_BUILD_DIR / "static")),
            name="static_assets",
        )
        fs_app.mount(
            "/admin/assets",
            StaticFiles(directory=str(FRONTEND_BUILD_DIR / "assets")),
            name="static_images",
        )
        # SPA catch-all registers later so explicit API endpoints win
        # — Starlette matches routes in registration order.
        spa_build_dir = FRONTEND_BUILD_DIR
    except Exception as e:
        print(e)
        print("Admin frontend not available.")
        spa_build_dir = None

    # Mobile PWA (separate CRA app at /mobile). Disjoint prefix from /admin.
    mobile_build_dir = None
    if (MOBILE_BUILD_DIR / "static").exists():
        try:
            fs_app.mount(
                "/mobile/static",
                StaticFiles(directory=str(MOBILE_BUILD_DIR / "static")),
                name="mobile_static",
            )
            mobile_build_dir = MOBILE_BUILD_DIR
        except Exception as e:
            print(e)
            print("Mobile PWA not available.")

    if WIDGET_DIR.exists():
        @fs_app.get("/widget/chat.js")
        async def serve_widget_js():
            widget_file = WIDGET_DIR / "chat.js"
            if widget_file.exists():
                return FileResponse(str(widget_file), media_type="application/javascript")
            return JSONResponse(status_code=404, content={"detail": "Widget not found"})

    return spa_build_dir, mobile_build_dir


def register_routers(fs_app: FastAPI) -> None:
    """Include every API router. Order preserved from the original lifespan."""
    from restai.routers import (
        llms,
        projects,
        tools,
        users,
        image,
        audio,
        embeddings,
        proxy,
        statistics,
        auth,
        teams,
        settings,
        direct,
        widgets,
        search,
    )

    fs_app.include_router(llms.router, tags=["LLMs"])
    fs_app.include_router(embeddings.router, tags=["Embeddings"])
    from restai.routers import image_generators, speech_to_text, secrets, whatsapp_webhook, webhooks as webhooks_router, templates as templates_router, bulk_ingest as bulk_ingest_router
    fs_app.include_router(image_generators.router, tags=["Image Generators"])
    fs_app.include_router(speech_to_text.router, tags=["Speech-to-Text"])
    fs_app.include_router(secrets.router, tags=["Project Secrets"])
    fs_app.include_router(whatsapp_webhook.router, tags=["WhatsApp"])
    fs_app.include_router(webhooks_router.router, tags=["Webhooks"])
    from restai.routers import payments as payments_router, payment_webhook as payment_webhook_router
    fs_app.include_router(payments_router.router, tags=["Payments"])
    fs_app.include_router(payment_webhook_router.router, tags=["Payments"])
    fs_app.include_router(templates_router.router)
    fs_app.include_router(bulk_ingest_router.router)
    from restai.routers import app as app_router, app_preview as app_preview_router
    fs_app.include_router(app_router.router)
    fs_app.include_router(app_preview_router.router)
    fs_app.include_router(projects.router)
    fs_app.include_router(tools.router, tags=["Tools"])
    fs_app.include_router(users.router, tags=["Users"])
    fs_app.include_router(proxy.router, tags=["Proxy"])
    fs_app.include_router(statistics.router, tags=["Statistics"])
    fs_app.include_router(auth.router, tags=["Auth"])
    fs_app.include_router(teams.router, tags=["Teams"])
    fs_app.include_router(settings.router, tags=["Settings"])
    fs_app.include_router(direct.router, tags=["Direct Access"])
    fs_app.include_router(widgets.router, tags=["Widget"])
    fs_app.include_router(search.router, tags=["Search"])

    from restai.routers import evals
    fs_app.include_router(evals.router)

    # Image cache always mounted — `draw_image` works on non-GPU deployments
    # via OpenAI/Google generators.
    from restai.routers import image_cache
    fs_app.include_router(image_cache.router, tags=["Image"])

    # Image + audio always mounted — external providers (OpenAI, Google,
    # Deepgram, AssemblyAI) work without GPU; local workers fail cleanly with
    # a "GPU required" error from the dispatch helper.
    fs_app.include_router(image.router, tags=["Image"])
    fs_app.include_router(audio.router, tags=["Audio"])

    if config.RESTAI_MCP:
        from restai.integrations.mcp import create_mcp_server
        mcp_server = create_mcp_server(fs_app)
        fs_app.mount("/mcp", mcp_server.http_app(transport="sse"))
        logging.info("MCP server enabled at /mcp/sse")


def register_spa(fs_app: FastAPI, spa_build_dir, mobile_build_dir=None) -> None:
    """Register the SPA catch-alls. MUST run AFTER register_routers() so the
    explicit API endpoints under /admin/... and /mobile/... win the route match.
    A falsy build dir means that app isn't built → skip it."""

    def _serve_from(build_dir, full_path):
        file_path = (build_dir / full_path).resolve()
        build_root = build_dir.resolve()
        # Prevent directory traversal — resolved path must stay inside build dir
        if full_path and str(file_path).startswith(str(build_root) + "/") and file_path.is_file():
            return FileResponse(str(file_path))
        index_file = build_root / "index.html"
        if index_file.exists():
            return FileResponse(str(index_file))
        return JSONResponse(status_code=404, content={"detail": "Not found"})

    if spa_build_dir is not None:
        @fs_app.get("/admin/{full_path:path}")
        async def serve_spa(full_path: str):
            return _serve_from(spa_build_dir, full_path)

    if mobile_build_dir is not None:
        @fs_app.get("/mobile/{full_path:path}")
        async def serve_mobile(full_path: str):
            return _serve_from(mobile_build_dir, full_path)
