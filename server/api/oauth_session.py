import os
import time
from typing import Dict

import aiohttp
from oauthlib.oauth2.rfc6749.errors import (
    InsecureTransportError,
    MissingTokenError
)


class OAuth2Session(object):
    def __init__(
        self,
        client_id,
        client_secret: str,
        token_url: str,
    ) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self.token_url = token_url
        self.token = None
        self.refresh_token = None
        self.token_expires_in = None
        self.token_time = None

    def is_expired(self) -> bool:
        if not self.token_time or not self.token_expires_in:
            return True

        return time.time() - self.token_time >= self.token_expires_in - 10

    def has_refresh_token(self) -> bool:
        return self.refresh_token is not None

    async def fetch_token(self) -> None:
        if not self.token_url.startswith("https://") and "OAUTHLIB_INSECURE_TRANSPORT" not in os.environ:
            raise InsecureTransportError()
        data = {
            "grant_type": "client_credentials",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
        }
        creds = await self._make_request(data=data)
        self.update_tokens(creds)

    async def refresh_tokens(self) -> None:
        assert self.refresh_token is not None
        if not self.token_url.startswith("https://") and "OAUTHLIB_INSECURE_TRANSPORT" not in os.environ:
            raise InsecureTransportError()
        data = {
            "grant_type": "refresh_token",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "refresh_token": self.refresh_token
        }
        creds = await self._make_request(data=data)
        self.update_tokens(creds)

    def update_tokens(self, creds: Dict[str, str]) -> None:
        self.token = creds["access_token"]
        self.refresh_token = creds.get("refresh_token")
        expires_in = creds.get("expires_in")
        if expires_in is not None:
            self.token_expires_in = int(expires_in)
        self.token_time = time.time()

    async def _make_request(self, data: Dict[str, str]) -> Dict[str, str]:
        async with aiohttp.ClientSession(raise_for_status=True) as session:
            async with session.post(self.token_url, data=data) as resp:
                return await resp.json()

    async def request(self, method: str, url: str, raise_for_status=False, **kwargs):
        if self.token is None:
            raise MissingTokenError()
        kwargs.update({
            "headers": {
                "Authorization": f"Bearer {self.token}"
            }
        })
        async with aiohttp.ClientSession(raise_for_status=raise_for_status) as session:
            async with session.request(method, url, **kwargs) as resp:
                return resp.status, await resp.json()
