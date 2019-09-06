import pytest
from oauthlib.oauth2.rfc6749.errors import (InsecureTransportError,
                                            MissingTokenError)
from server.api.oauth_session import OAuth2Session


@pytest.mark.asyncio
async def test_error_conditions():
    oauth_session = OAuth2Session(
        client_id="client_id",
        client_secret="client_secret",
        token_url='http://some_url'
    )
    with pytest.raises(InsecureTransportError):
        await oauth_session.fetch_token()

    with pytest.raises(MissingTokenError):
        await oauth_session.request('GET', 'http://some_other_url')
