import logging

from oauthlib.oauth2 import BackendApplicationClient
from oauthlib.oauth2.rfc6749.errors import MissingTokenError, InsecureTransportError
from requests.exceptions import SSLError
from requests_oauthlib import OAuth2Session
import sys

import server.config as config
from server.config import API_TOKEN_URI, API_BASE_URL, API_CLIENT_SECRET, API_CLIENT_ID

"""
Uncomment the following line if your API uses HTTP instead of HTTPS
"""
# os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'


class SessionManager:
    """
    Garantor for API access
    """
    def __init__(self):
        self.session = None  # Instance of session
        self.token = None  # token instance
        self.client = BackendApplicationClient(client_id=API_CLIENT_ID)
        self.logger = logging.getLogger()

    def update_token(self, token):
        self.token = token

    def __enter__(self):
        if not self.session:
            try:
                self.session = OAuth2Session(
                    client=self.client,
                    token=self.token,
                    auto_refresh_url=API_TOKEN_URI,
                    auto_refresh_kwargs={
                        "client_id": API_CLIENT_ID,
                        "client_secret": API_CLIENT_SECRET
                    },
                    token_updater=self.update_token
                )
                self.token = self.session.fetch_token(
                    token_url=API_TOKEN_URI,
                    client_id=API_CLIENT_ID,
                    client_secret=API_CLIENT_SECRET
                )
            except:
                self.__exit__(*sys.exc_info())

        return self.session

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type == MissingTokenError:
            self.logger.error("There was an error while connecting the API - token is missing or invalid")

        elif exc_type == InsecureTransportError:
            self.logger.error(
                "API (%s,%s) should be HTTPS, not HTTP. Enable OAUTHLIB_INSECURE_TRANSPORT to avoid this warning.",
                config.API_BASE_URL,
                config.API_TOKEN_URI
            )

        elif exc_type == SSLError:
            self.logger.error("The certificate verification failed while connecting the API")

        elif exc_type:
            self.logger.error(format(exc_val))
        if exc_type:
            self.session = None


class ApiAccessor:
    def __init__(self):
        self.api_session = SessionManager()

    async def update_achievements(self, achievements_data, player_id):

        # Converting the achievements to a format the jAPI can understand
        for achievement in achievements_data:
            achievement['playerId'] = player_id
            achievement['achievementId'] = achievement.pop('achievement_id')
            achievement['operation'] = achievement.pop('update_type')

        code, text = await self.api_patch("achievements/update", achievements_data)
        return code, text

    async def update_events(self, events_data, player_id):

        # Converting the events to a format the jAPI can understand
        for event in events_data:
            event['playerId'] = player_id
            event['eventId'] = event.pop('event_id')

        code, text = await self.api_patch("events/update", events_data)
        return code, text

    async def api_get(self, path):
        with self.api_session as api:
            result = api.get(API_BASE_URL + path)
        return result.status_code, result.text

    async def api_patch(self, path, json_data):
        headers = {'Content-type': 'application/json'}
        with self.api_session as api:
            result = api.request("PATCH", API_BASE_URL + path, headers=headers, json=json_data)
        return result.status_code, result.text
