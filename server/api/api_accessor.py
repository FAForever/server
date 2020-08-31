from ssl import SSLError
from typing import Optional

from oauthlib.oauth2.rfc6749.errors import (
    InsecureTransportError,
    MissingTokenError
)

from server.config import config
from server.decorators import with_logger

from .oauth_session import OAuth2Session


@with_logger
class SessionManager:
    """
    Garantor for API access
    """
    def __init__(self):
        self.session = None  # Instance of session

    async def get_session(self) -> Optional[OAuth2Session]:
        if not self.session:
            self.session = OAuth2Session(
                client_id=config.API_CLIENT_ID,
                client_secret=config.API_CLIENT_SECRET,
                token_url=config.API_TOKEN_URI
            )
        if not self.session.is_expired():
            return self.session

        try:
            if self.session.has_refresh_token():
                self._logger.info("Refreshing OAuth token")
                await self.session.refresh_tokens()
            else:
                self._logger.info("Fetching new OAuth token")
                await self.session.fetch_token()
            return self.session
        except MissingTokenError:  # pragma: no cover
            self._logger.error("There was an error while connecting the API - token is missing or invalid")
        except InsecureTransportError:  # pragma: no cover
            self._logger.error(
                "API (%s,%s) should be HTTPS, not HTTP. Enable OAUTHLIB_INSECURE_TRANSPORT to avoid this warning.",
                config.API_BASE_URL,
                config.API_TOKEN_URI
            )
        except SSLError:  # pragma: no cover
            self._logger.error("The certificate verification failed while connecting the API")
        except Exception as e:  # pragma: no cover
            self._logger.exception(e)

        # Only reachable if an exception occurred
        self.session = None
        raise ConnectionError


@with_logger
class ApiAccessor:
    def __init__(self):
        self.api_session = SessionManager()

    async def update_achievements(self, achievements_data, player_id):

        # Converting the achievements to a format the jAPI can understand
        for achievement in achievements_data:
            achievement["playerId"] = player_id
            achievement["achievementId"] = achievement.pop("achievement_id")
            achievement["operation"] = achievement.pop("update_type")

        self._logger.debug("Sending achievement data: %s", achievements_data)

        return await self.api_patch("achievements/update", achievements_data)

    async def update_events(self, events_data, player_id):

        # Converting the events to a format the jAPI can understand
        for event in events_data:
            event["playerId"] = player_id
            event["eventId"] = event.pop("event_id")

        self._logger.debug("Sending event data: %s", events_data)

        return await self.api_patch("events/update", events_data)

    async def api_get(self, path):
        api = await self.api_session.get_session()
        return await api.request("GET", config.API_BASE_URL + path)

    async def api_patch(self, path, json_data):
        api = await self.api_session.get_session()
        headers = {"Content-type": "application/json"}
        status, data = await api.request(
            "PATCH",
            config.API_BASE_URL + path,
            headers=headers,
            json=json_data
        )
        if status != 200:
            self._logger.error("API returned error: [%i] %s", status, data)
        return (status, data)
