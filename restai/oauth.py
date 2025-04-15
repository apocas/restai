from datetime import timedelta
import logging

import aiohttp
from authlib.integrations.starlette_client import OAuth
from authlib.oidc.core import UserInfo
from fastapi import (
    HTTPException,
    status,
)
from starlette.responses import RedirectResponse


from restai import config
from restai.auth import create_access_token
from restai.config import (
    AUTO_CREATE_USER,
    LOG_LEVEL,
    OAUTH_ALLOWED_DOMAINS,
    OAUTH_EMAIL_CLAIM,
    OAUTH_PROVIDERS,
)
from restai.constants import ERROR_MESSAGES


logging.basicConfig(level=LOG_LEVEL)
log = logging.getLogger("passlib")
log.setLevel(logging.ERROR)


class OAuthManager:
    def __init__(self, app, db_wrapper):
        self.oauth = OAuth()
        self.app = app
        self.db_wrapper = db_wrapper
        for _, provider_config in OAUTH_PROVIDERS.items():
            provider_config["register"](self.oauth)

    def get_client(self, provider_name):
        return self.oauth.create_client(provider_name)

    async def handle_login(self, request, provider):
        if provider not in OAUTH_PROVIDERS:
            raise HTTPException(404)
        # If the provider has a custom redirect URL, use that, otherwise automatically generate one
        redirect_uri = OAUTH_PROVIDERS[provider].get("redirect_uri") or request.url_for(
            "oauth_callback", provider=provider
        )
        client = self.get_client(provider)
        if client is None:
            raise HTTPException(404)
        return await client.authorize_redirect(request, redirect_uri)

    async def handle_callback(self, request, provider, response):
        if provider not in OAUTH_PROVIDERS:
            raise HTTPException(404)
        client = self.get_client(provider)
        try:
            token = await client.authorize_access_token(request)
        except Exception as e:
            log.warning(f"OAuth callback error: {e}")
            raise HTTPException(400, detail=ERROR_MESSAGES.INVALID_CRED)
        user_data: UserInfo = token.get("userinfo")
        if not user_data or OAUTH_EMAIL_CLAIM not in user_data:
            user_data: UserInfo = await client.userinfo(token=token)
        if not user_data:
            log.warning(f"OAuth callback failed, user data is missing: {token}")
            raise HTTPException(400, detail=ERROR_MESSAGES.INVALID_CRED)

        sub = user_data.get(OAUTH_PROVIDERS[provider].get("sub_claim", "sub"))
        if not sub:
            log.warning(f"OAuth callback failed, sub is missing: {user_data}")
            raise HTTPException(400, detail=ERROR_MESSAGES.INVALID_CRED)
        provider_sub = f"{provider}@{sub}"
        email_claim = OAUTH_EMAIL_CLAIM
        email = user_data.get(email_claim, "")
        if not email:
            if provider == "github":
                try:
                    access_token = token.get("access_token")
                    headers = {"Authorization": f"Bearer {access_token}"}
                    async with aiohttp.ClientSession() as session:
                        async with session.get(
                            "https://api.github.com/user/emails", headers=headers
                        ) as resp:
                            if resp.ok:
                                emails = await resp.json()
                                # use the primary email as the user's email
                                primary_email = next(
                                    (e["email"] for e in emails if e.get("primary")),
                                    None,
                                )
                                if primary_email:
                                    email = primary_email
                                else:
                                    log.warning(
                                        "No primary email found in GitHub response"
                                    )
                                    raise HTTPException(
                                        400, detail=ERROR_MESSAGES.INVALID_CRED
                                    )
                            else:
                                log.warning("Failed to fetch GitHub email")
                                raise HTTPException(
                                    400, detail=ERROR_MESSAGES.INVALID_CRED
                                )
                except Exception as e:
                    log.warning(f"Error fetching GitHub email: {e}")
                    raise HTTPException(400, detail=ERROR_MESSAGES.INVALID_CRED)
            else:
                log.warning(f"OAuth callback failed, email is missing: {user_data}")
                raise HTTPException(400, detail=ERROR_MESSAGES.INVALID_CRED)
        email = email.lower()
        if (
            "*" not in OAUTH_ALLOWED_DOMAINS
            and email.split("@")[-1] not in OAUTH_ALLOWED_DOMAINS
        ):
            log.warning(
                f"OAuth callback failed, e-mail domain is not in the list of allowed domains: {user_data}"
            )
            raise HTTPException(400, detail=ERROR_MESSAGES.INVALID_CRED)

        user = self.db_wrapper.get_user_by_username(email)
        if user is None and AUTO_CREATE_USER:
            user = self.db_wrapper.create_user(email, None, False, False)
            self.db_wrapper.db.commit()
        elif user is None:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, detail=ERROR_MESSAGES.ACCESS_PROHIBITED
            )

        jwt_token = create_access_token(
            data={"username": user.username}, expires_delta=timedelta(minutes=1440)
        )

        response.set_cookie(
            key="restai_token",
            value=jwt_token,
            samesite="strict",
            expires=86400,
            httponly=True,
        )

        return RedirectResponse(config.RESTAI_URL + "/admin", headers=response.headers)
