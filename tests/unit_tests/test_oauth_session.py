import pytest
from oauthlib.oauth2.rfc6749.errors import InsecureTransportError
from server.api.oauth_session import OAuth2Session


async def test_insecure_raises():
    oauth_session = OAuth2Session(
        client_id="client_id",
        client_secret="client_secret",
        token_url='http://some_url'
    )
    with pytest.raises(InsecureTransportError):
        await oauth_session.fetch_token()
