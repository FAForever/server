import aiocron
import aiohttp
import json
import jwt

from jwt import InvalidTokenError
from jwt.algorithms import RSAAlgorithm

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
        self.public_keys = None

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
        self.public_keys = {}
        async with aiohttp.ClientSession(raise_for_status=True) as session:
            async with session.get(config.HYDRA_JWKS_URI) as resp:
                jwks = await resp.json()
                for jwk in jwks['keys']:
                    kid = jwk['kid']
                    self.public_keys[kid] = RSAAlgorithm.from_jwk(json.dumps(jwk))

    async def get_player_id_from_token(self, token: str) -> int:
        """
            Decode the JWT to get the player_id
        """
        try:
            kid = jwt.get_unverified_header(token)['kid']
            key = self.public_keys[kid]
            return int(jwt.decode(token, key=key, algorithms="RS256", options={"verify_aud": False})["sub"])
        except (InvalidTokenError, KeyError, ValueError):
            raise AuthenticationError("Token signature was invalid")
