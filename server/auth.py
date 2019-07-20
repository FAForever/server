import jwt
from jwt import InvalidTokenError

from .config import API_JWT_PUBLIC_KEY
from .core import Module
from .exceptions import AuthenticationError


class AuthModule(Module):
    KEY_HEADER = '-----BEGIN PUBLIC KEY-----'

    def __init__(self) -> None:
        super(AuthModule, self).__init__()

        if not API_JWT_PUBLIC_KEY:
            raise RuntimeError("API_JWT_PUBLIC_KEY must be set to use token authentication!")
        self.pub_key = API_JWT_PUBLIC_KEY

        if API_JWT_PUBLIC_KEY and self.KEY_HEADER not in API_JWT_PUBLIC_KEY:
            with open(API_JWT_PUBLIC_KEY) as f:
                self.pub_key = f.read()


mod = AuthModule()


@mod.route("auth")
async def handle_auth(conn, message):
    token = message['token']
    try:
        token = jwt.decode(token, mod.pub_key, algorithms="RS256")
    except jwt.InvalidTokenError:
        raise AuthenticationError("Token signature was invalid")
    user_id = token['user_id']
    await conn.on_player_login(user_id, message)


def valid_token(token: str) -> bool:
    assert API_JWT_PUBLIC_KEY, "Pub key must be set to use oauth login"
    try:
        jwt.decode(token, API_JWT_PUBLIC_KEY, algorithms='RS256')
        return True
    except InvalidTokenError:
        return False
