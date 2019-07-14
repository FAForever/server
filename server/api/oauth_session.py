import asyncio
import os
from typing import Dict

import aiohttp
from oauthlib.oauth2.rfc6749.errors import (InsecureTransportError,
                                            MissingTokenError)


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

    async def fetch_token(self) -> None:
        if not self.token_url.startswith('https://') and 'OAUTHLIB_INSECURE_TRANSPORT' not in os.environ:
            raise InsecureTransportError()
        data = {
            'grant_type': 'client_credentials',
            'client_id': self.client_id,
            'client_secret': self.client_secret,
        }
        creds = await self._make_request(data=data)
        self.update_tokens(creds)

    async def refresh_tokens(self) -> None:
        assert self.refresh_token is not None
        data = {
            'grant_type': 'refresh_token',
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            'refresh_token': self.refresh_token
        }
        creds = await self._make_request(
            data=data,
        )
        self.update_tokens(creds)

    def update_tokens(self, creds: Dict[str, str]) -> None:
        self.token = creds['access_token']
        refresh_token = creds.get('refresh_token')
        if refresh_token:
            self.refresh_token = refresh_token
            expires_in = int(creds['expires_in'])
            asyncio.ensure_future(self._schedule_refresh(expires_in - 5))

    async def _schedule_refresh(self, wait_time):
        await asyncio.sleep(wait_time)
        await self.refresh_tokens()

    async def _make_request(self, data: Dict[str, str]) -> Dict[str, str]:
        async with aiohttp.ClientSession(raise_for_status=True) as session:
            async with session.post(self.token_url, data=data) as resp:
                return await resp.json()

    async def request(self, method: str, url: str, raise_for_status=False, **kwargs):
        if self.token is None:
            raise MissingTokenError()
        kwargs.update({
            'headers': {
                'Authorization': f'Bearer {self.token}'
            }
        })
        async with aiohttp.ClientSession(raise_for_status=raise_for_status) as session:
            async with session.request(method, url, **kwargs) as resp:
                return resp.status, await resp.json()
