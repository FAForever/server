import time

import aiocron
import aiohttp
import jwt
from jwt import InvalidTokenError
from jwt.algorithms import RSAAlgorithm

from server.config import config

from .asyncio_extensions import synchronizedmethod
from .core import Service
from .decorators import with_logger
from .exceptions import AuthenticationError


@with_logger
class OAuthService(Service, name="oauth_service"):
    """
    Service for managing the OAuth token logins and verification.
    """

    def __init__(self):
        self.public_keys = {}
        self._last_key_fetch_time = None

    async def initialize(self) -> None:
        await self.retrieve_public_keys()
        # crontab: min hour day month day_of_week
        # Run every 10 minutes to update public keys.
        self._update_cron = aiocron.crontab(
            "*/10 * * * *", func=self.retrieve_public_keys
        )

    @synchronizedmethod
    async def get_public_keys(self) -> dict:
        """
        Return cached keys, or fetch them if they're missing
        """
        if not self.public_keys:
            # Rate limit requests so we don't spam the endpoint when it's down
            if (
                not self._last_key_fetch_time or
                time.monotonic() - self._last_key_fetch_time > 5
            ):
                await self.retrieve_public_keys()

            if not self.public_keys:
                raise RuntimeError("jwks could not be retrieved")

        return self.public_keys

    async def retrieve_public_keys(self) -> None:
        """
        Get the latest jwks from the hydra endpoint
        """
        self._last_key_fetch_time = time.monotonic()
        try:
            async with aiohttp.ClientSession(raise_for_status=True) as session:
                async with session.get(config.HYDRA_JWKS_URI) as resp:
                    jwks = await resp.json()
                    self.public_keys = {
                        jwk["kid"]: RSAAlgorithm.from_jwk(jwk)
                        for jwk in jwks["keys"]
                    }
        except Exception:
            self._logger.exception(
                "Unable to retrieve jwks, token login will be unavailable!"
            )

    async def get_player_id_from_token(self, token: str) -> int:
        """
        Decode the JWT to get the player_id
        """
        # Ensures that if we're missing the jwks we will try to fetch them on
        # each new login request. This way our login functionality will be
        # restored as soon as possible
        keys = await self.get_public_keys()
        try:
            kid = jwt.get_unverified_header(token)["kid"]
            key = keys[kid]
            decoded = jwt.decode(
                token,
                key=key,
                algorithms="RS256",
                options={"verify_aud": False}
            )

            if "lobby" not in decoded["scp"]:
                raise AuthenticationError("Token does not have permission to login to the lobby server", "token")

            return int(decoded["sub"])
        except (InvalidTokenError, KeyError, ValueError):
            raise AuthenticationError("Token signature was invalid", "token")
