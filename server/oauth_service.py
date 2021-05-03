import aiocron
import jwt

from jwt import PyJWKClient, InvalidTokenError

from server.config import config
from .core import Service
from .decorators import with_logger
from .exceptions import AuthenticationError


@with_logger
class OauthService(Service):
    """
        Service for managing the OAuth token logins and verification.
    """

    def __init__(self):
        self.jwks_client = None

    async def initialize(self) -> None:
        await self.retrieve_public_keys()
        # crontab: min hour day month day_of_week
        # Run every day to update public keys.
        self._update_cron = aiocron.crontab(
            "0 0 * * *", func=self.retrieve_public_keys
        )

    async def retrieve_public_keys(self) -> None:
        """
            Get the latest jwks from the hydra endpoint
        """
        self.jwks_client = PyJWKClient(config.HYDRA_JWKS_URI)

    async def get_player_id_from_token(self, token: str) -> int:
        """
            Decode the JWT to get the player_id
        """
        try:
            signing_key = self.jwks_client.get_signing_key_from_jwt(token)
            return jwt.decode(token, signing_key.key, algorithms=["RS256"])["user_id"]
        except (InvalidTokenError, KeyError):
            raise AuthenticationError("Token signature was invalid")
