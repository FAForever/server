import os
from base64 import b64encode

import jwt
from jwt import InvalidTokenError

from .config import API_JWT_PUBLIC_KEY
from .core import Module
from .decorators import with_logger
from .exceptions import AuthenticationError


def is_key(s: str):
    if s.startswith("-----BEGIN") or s.startswith("ssh-rsa"):
        return True
    return False


@with_logger
class AuthModule(Module):
    KEY_HEADER = "-----BEGIN PUBLIC KEY-----"

    def __init__(self) -> None:
        super(AuthModule, self).__init__()

        self.pub_key = API_JWT_PUBLIC_KEY

        if not API_JWT_PUBLIC_KEY:
            return

        if not is_key(API_JWT_PUBLIC_KEY):
            with open(API_JWT_PUBLIC_KEY) as f:
                self.pub_key = f.read()


mod = AuthModule()

if mod.pub_key:
    @mod.route("auth")
    async def handle_auth(conn, message):
        assert mod.pub_key
        token = message["token"]
        try:
            token = jwt.decode(token, mod.pub_key, algorithms="RS256")
            user_id = token["user_id"]
        except (InvalidTokenError, KeyError):
            raise AuthenticationError("Token signature was invalid")

        new_irc_password = b64encode(os.urandom(30)).decode()
        conn.send({
            "command": "irc_password",
            "password": new_irc_password
        })
        await conn.on_player_login(user_id, new_irc_password, message)
else:  # pragma: no cover
    # Would need to set up tox in order to test this
    mod._logger.info("API_JWT_PUBLIC_KEY not set. Token authentication will be unavailable")
