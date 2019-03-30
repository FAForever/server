"""
Twilio API NTS token
"""

import asyncio
from functools import partial
from typing import Dict, List

from server.config import TWILIO_ACCOUNT_SID, TWILIO_TOKEN, TWILIO_TTL
from twilio.rest import Client as TwilioRestClient


class TwilioNTS():
    """
    Twilio NTS Token Service

    Creates new twilio NTS tokens
    """
    def __init__(self, sid=TWILIO_ACCOUNT_SID, token=TWILIO_TOKEN):
        """
        Constructor

        Creates a Twilio rest client

        :param sid str: Twilio Account Sid
        :param key str: Twilio Auth Token
        """
        self.twilio_account_sid = sid
        self.twilio_token = token
        self.client = TwilioRestClient(self.twilio_account_sid, self.twilio_token)

    async def server_tokens(self, ttl=TWILIO_TTL) -> List[Dict]:
        """
        Fetches token from Twilio

        :param ttl - ttl in seconds
        """
        loop = asyncio.get_event_loop()
        token = await loop.run_in_executor(None, partial(self.client.tokens.create, ttl))
        return token.ice_servers
