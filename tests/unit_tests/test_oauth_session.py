import pytest
from oauthlib.oauth2.rfc6749.errors import (
    InsecureTransportError,
    MissingTokenError
)

from server.api.oauth_session import OAuth2Session


@pytest.fixture
def oauth_session():
    return OAuth2Session(
        client_id="client_id",
        client_secret="client_secret",
        token_url="http://some_url"
    )


async def test_error_conditions(oauth_session):
    with pytest.raises(InsecureTransportError):
        await oauth_session.fetch_token()

    oauth_session.refresh_token = "asdf"
    with pytest.raises(InsecureTransportError):
        await oauth_session.refresh_tokens()

    with pytest.raises(MissingTokenError):
        await oauth_session.request("GET", "http://some_other_url")


def test_is_expired(oauth_session):
    assert oauth_session.is_expired()
    assert oauth_session.has_refresh_token() is False


def test_is_expired_2(oauth_session):
    oauth_session.update_tokens({
        "access_token": "access_token",
        "expires_in": 120
    })

    assert not oauth_session.is_expired()

    oauth_session.update_tokens({
        "access_token": "access_token",
        "expires_in": 0
    })
    assert oauth_session.is_expired()
