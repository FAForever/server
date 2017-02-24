"""
Twilio API NTS token
"""

import asyncio
from functools import partial
from twilio.rest import Client as TwilioRestClient

from server.config import TWILIO_ACCOUNT_SID, TWILIO_TOKEN, TWILIO_TTL

class TwilioNTS:
    """
    Twilio NTS Token Service

    Creates a new twilio NTS token once per hour.
    """
    def __init__(self, sid=None, token=None):
        """
        Constructor

        Creates a Twilio rest client

        :param sid str: Twilio Account Sid
        :param key str: Twilio Auth Token
        """
        self.twilio_account_sid = sid or TWILIO_ACCOUNT_SID
        self.twilio_token = token or TWILIO_TOKEN
        self.client = TwilioRestClient(self.twilio_account_sid, self.twilio_token)

    async def fetch_token(self, ttl=None):
        """
        Fetches token from Twilio

        :param ttl - ttl in seconds or None for default of 24h
        """
        ttl = ttl or TWILIO_TTL
        if ttl is not None:
            ttl = int(ttl)
        loop = asyncio.get_event_loop()
        token = await loop.run_in_executor(None, partial(self.client.tokens.create, ttl))
        return dict(ice_servers=token.ice_servers,
                    date_created=token.date_created.isoformat(),
                    ttl=token.ttl)
