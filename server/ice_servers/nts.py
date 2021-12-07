"""
Twilio API NTS token
"""

import asyncio
from functools import partial

from twilio.rest import Client as TwilioRestClient

from server.config import config


class TwilioNTS:
    """
    Twilio NTS Token Service

    Creates new twilio NTS tokens
    """
    def __init__(self, sid=None, token=None):
        if sid is None:
            sid = config.TWILIO_ACCOUNT_SID  # pragma: no cover
        if token is None:
            token = config.TWILIO_TOKEN  # pragma: no cover

        self.twilio_account_sid = sid
        self.twilio_token = token
        self.client = TwilioRestClient(self.twilio_account_sid, self.twilio_token)

    async def server_tokens(self, ttl=None) -> list[dict[str]]:
        """
        Fetches token from Twilio

        # Params
        - `ttl`: ttl in seconds
        """
        if ttl is None:
            ttl = config.TWILIO_TTL  # pragma: no cover

        loop = asyncio.get_running_loop()
        token = await loop.run_in_executor(None, partial(self.client.tokens.create, ttl))
        return token.ice_servers
