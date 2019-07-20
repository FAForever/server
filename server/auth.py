import jwt
from jwt import InvalidTokenError

from .config import API_JWT_PUBLIC_KEY
from .core import Module
from .exceptions import AuthenticationError
from .decorators import with_logger


@with_logger
class AuthModule(Module):
    KEY_HEADER = "-----BEGIN PUBLIC KEY-----"

    def __init__(self) -> None:
        super(AuthModule, self).__init__()

        self.pub_key = API_JWT_PUBLIC_KEY

        if API_JWT_PUBLIC_KEY and self.KEY_HEADER not in API_JWT_PUBLIC_KEY:
            with open(API_JWT_PUBLIC_KEY) as f:
                self.pub_key = f.read()


mod = AuthModule()

if mod.pub_key:
    @mod.route("auth")
    async def handle_auth(conn, message):
        token = message["token"]
        try:
            token = jwt.decode(token, mod.pub_key, algorithms="RS256")
            user_id = token["user_id"]
        except (InvalidTokenError, KeyError):
            raise AuthenticationError("Token signature was invalid")

        await conn.on_player_login(user_id, message)
else:  # pragma: no cover
    # Would need to set up tox in order to test this
    mod._logger.info("API_JWT_PUBLIC_KEY not set. Token authentication will be unavailable")
