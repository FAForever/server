from unittest import mock

import pytest

from server import OAuthService


@pytest.fixture
def oauth_service():
    return OAuthService()


async def test_get_public_keys(oauth_service):
    def set_public_keys():
        oauth_service.public_keys = {"any": "value"}

    oauth_service.retrieve_public_keys = mock.AsyncMock(
        side_effect=set_public_keys
    )

    public_keys = await oauth_service.get_public_keys()

    assert public_keys == {"any": "value"}
    oauth_service.retrieve_public_keys.assert_called_once()


async def test_get_public_keys_cached(oauth_service):
    oauth_service.public_keys = {"any": "value"}
    oauth_service.retrieve_public_keys = mock.AsyncMock()

    public_keys = await oauth_service.get_public_keys()

    assert public_keys == {"any": "value"}
    oauth_service.retrieve_public_keys.assert_not_called()
