"""
Twilio API NTS token
"""

import asyncio
import twilio
from twilio.rest import TwilioRestClient

from server.config import TWILIO_SID, TWILIO_KEY, TWILIO_TTL

class TwilioNTS:
    """
    Twilio NTS Token Service

    Creates a new twilio NTS token once per hour.
    """
    def __init__(self, sid=None, key=None):
        """
        Constructor

        Creates a Twilio rest client, fetches a token, and creates an aiocron
        cronjob to create a new token every hour

        :param sid str: Twilio Account Sid
        :param key str: Twilio Auth Token
        """
        self.twilio_sid = sid or TWILIO_SID
        self.twilio_key = key or TWILIO_KEY
        self.client = TwilioRestClient(ACCOUNT_SID, AUTH_TOKEN)

    def fetch_token(self, ttl=None):
        """
        Fetches token from Twilio

        :param ttl - ttl in seconds or None for default of 24h
        """
        ttl = ttl or TWILIO_TTL
        if ttl is not None:
            ttl = int(ttl)
        loop = asyncio.get_event_loop()
        token = await loop.run_in_executor(None, client.tokens.create(ttl))
        return token
