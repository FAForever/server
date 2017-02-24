"""
Twilio API NTS token
"""

import asyncio
import twilio
from twilio.rest import TwilioRestClient

from server.config import TWILIO_SID, TWILIO_KEY

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
        self.token = None
        loop = asyncio.get_event_loop()
        loop.run_until_complete(loop.create_task(self._fetch_token))
        self._update_cron = aiocron.crontab('0 * * * *', func=self.f_etch_token)

    def _fetch_token(self):
        """
        Fetches token from Twilio and saves it
        """
        loop = asyncio.get_event_loop()
        token = await loop.run_in_executor(None, client.tokens.create())
        self.token = token

    def get_token(self):
        """
        Gets the current token
        """
        return self.token
