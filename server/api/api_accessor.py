import logging
from ssl import SSLError
from typing import Optional

from oauthlib.oauth2.rfc6749.errors import (InsecureTransportError,
                                            MissingTokenError)
from server.config import (API_BASE_URL, API_CLIENT_ID, API_CLIENT_SECRET,
                           API_TOKEN_URI)

from .oauth_session import OAuth2Session

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
        self.logger = logging.getLogger()

    async def get_session(self) -> Optional[OAuth2Session]:
        if self.session:
            return self.session

        try:
            self.session = OAuth2Session(
                client_id=API_CLIENT_ID,
                client_secret=API_CLIENT_SECRET,
                token_url=API_TOKEN_URI
            )
            await self.session.fetch_token()
            return self.session
        except MissingTokenError:  # pragma: no cover
            self.logger.error("There was an error while connecting the API - token is missing or invalid")
        except InsecureTransportError:  # pragma: no cover
            self.logger.error(
                "API (%s,%s) should be HTTPS, not HTTP. Enable OAUTHLIB_INSECURE_TRANSPORT to avoid this warning.",
                API_BASE_URL,
                API_TOKEN_URI
            )
        except SSLError:  # pragma: no cover
            self.logger.error("The certificate verification failed while connecting the API")
        except Exception as e:  # pragma: no cover
            self.logger.exception(e)

        # Only reachable if an exception occurred
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

        return await self.api_patch("achievements/update", achievements_data)

    async def update_events(self, events_data, player_id):

        # Converting the events to a format the jAPI can understand
        for event in events_data:
            event['playerId'] = player_id
            event['eventId'] = event.pop('event_id')

        return await self.api_patch("events/update", events_data)

    async def api_get(self, path):
        api = await self.api_session.get_session()
        return await api.request('GET', API_BASE_URL + path)

    async def api_patch(self, path, json_data):
        api = await self.api_session.get_session()
        headers = {'Content-type': 'application/json'}
        return await api.request("PATCH", API_BASE_URL + path, headers=headers, json=json_data)
