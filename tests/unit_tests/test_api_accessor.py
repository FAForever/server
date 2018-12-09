from server.api.api_accessor import ApiAccessor
from server.config import API_BASE_URL


async def test_api_accessor():
    api_accessor = ApiAccessor()
    with api_accessor.api_session as api:
        assert api is None


async def test_api_get(api_accessor):
    result = await api_accessor.api_get('test')
    api_accessor.api_session.session.get.assert_called_once_with(
        API_BASE_URL + 'test'
    )

    assert result == (200, 'test')


async def test_api_patch(api_accessor):
    data = dict()
    result = await api_accessor.api_patch('test', data)
    api_accessor.api_session.session.request.assert_called_once_with(
        "PATCH",
        API_BASE_URL+'test',
        headers={'Content-type': 'application/json'},
        json=data
    )

    assert result == (200, 'test')


async def test_update_achievements(api_accessor):
    achievements = await api_accessor.update_achievements([dict(
        achievement_id='test',
        update_type='test'
    )], 1)
    assert achievements == (200, 'test')


async def test_update_events(api_accessor):
    events = await api_accessor.update_events([dict(
        event_id='test'
    )], 1)
    assert events == (200, 'test')
