from unittest import mock

from sqlalchemy import select

from server.db.models import avatars, login
from server.rating import RatingType


async def test_fetch_player_data(player_factory, player_service):
    player = player_factory(player_id=50)

    await player_service.fetch_player_data(player)
    assert player.ratings[RatingType.GLOBAL] == (1200, 250)
    assert player.game_count[RatingType.GLOBAL] == 42
    assert player.ratings[RatingType.LADDER_1V1] == (1300, 400)
    assert player.clan == "123"
    assert player.avatar == {"url": "https://content.faforever.com/faf/avatars/UEF.png", "tooltip": "UEF"}


async def test_fetch_ratings_nonexistent(player_factory, player_service):
    player = player_factory(player_id=-1)
    player_service._logger = mock.Mock()

    async with player_service._db.acquire() as conn:
        await player_service._fetch_player_ratings(player, conn)

    assert player.ratings[RatingType.GLOBAL] == (1500, 500)


async def test_fetch_ratings_partially_nonexistent(player_factory, player_service):
    # Player 52 should not have leaderboard_rating entries
    # and no ladder1v1_rating entry, but a global_rating entry
    player = player_factory(player_id=52)
    player_service._logger = mock.Mock()

    async with player_service._db.acquire() as conn:
        await player_service._fetch_player_ratings(player, conn)

    assert player.ratings[RatingType.LADDER_1V1] == (1500, 500)


async def test_fetch_player_data_multiple_avatar(player_factory, player_service):
    player1 = player_factory(player_id=51)
    player2 = player_factory(player_id=52)

    await player_service.fetch_player_data(player1)
    assert player1.avatar == {"url": "https://content.faforever.com/faf/avatars/UEF.png", "tooltip": "UEF"}

    await player_service.fetch_player_data(player2)
    assert player2.avatar == {"url": "https://content.faforever.com/faf/avatars/qai2.png", "tooltip": "QAI"}


async def test_fetch_player_data_no_avatar_or_clan(player_factory, player_service):
    player = player_factory(player_id=100)

    await player_service.fetch_player_data(player)
    assert player.ratings[RatingType.GLOBAL] == (1500, 500)
    assert player.game_count[RatingType.GLOBAL] == 0
    assert player.ratings[RatingType.LADDER_1V1] == (1500, 500)
    assert player.clan is None
    assert player.avatar is None


async def test_fetch_player_data_non_existent(player_factory, player_service):
    player = player_factory(player_id=-1)

    await player_service.fetch_player_data(player)


async def test_refresh_player_avatar_connected(
    player_factory, player_service
):
    # Player 51 owns avatars 1 (QAI) and 2 (UEF); make 1 the authoritative
    # selection via login.avatar_id while the legacy flag still points at 2.
    player = player_factory(player_id=51)
    player.avatar = None  # simulate stale (e.g. just connected)
    player_service[51] = player
    async with player_service._db.acquire() as conn:
        await conn.execute(login.update().where(login.c.id == 51).values(avatar_id=1))

    refreshed = await player_service.refresh_player_avatar(51)

    assert refreshed is True
    assert player.avatar == {
        "url": "https://content.faforever.com/faf/avatars/qai2.png",
        "tooltip": "QAI",
    }
    assert player in player_service._dirty_players
    # the legacy `selected` flag is reconciled to the authoritative avatar
    async with player_service._db.acquire() as conn:
        result = await conn.execute(
            select(avatars.c.idAvatar, avatars.c.selected).where(avatars.c.idUser == 51)
        )
        selected = {row.idAvatar: bool(row.selected) for row in result}
    assert selected == {1: True, 2: False}


async def test_refresh_player_avatar_clears_legacy_fallback(
    player_factory, player_service
):
    # Player 50 has a legacy selected avatar but no authoritative login.avatar_id,
    # which represents an explicit clear via the API. The refresh must not let the
    # legacy fallback resurrect it, and must clean the flag up.
    player = player_factory(player_id=50)
    player_service[50] = player

    refreshed = await player_service.refresh_player_avatar(50)

    assert refreshed is True
    assert player.avatar is None
    async with player_service._db.acquire() as conn:
        result = await conn.execute(
            select(avatars.c.selected).where(avatars.c.idUser == 50)
        )
        assert all(not row.selected for row in result)


async def test_refresh_player_avatar_not_connected(player_service):
    refreshed = await player_service.refresh_player_avatar(999)

    assert refreshed is False
    assert not player_service._dirty_players


async def test_magic_methods(player_factory, player_service):
    player = player_factory(player_id=0)
    player_service[0] = player

    assert len(player_service) == 1
    assert list(iter(player_service)) == [player]
    assert player_service[0] is player
    assert player_service.get_player(0) is player

    player_service.remove_player(player)

    assert len(player_service) == 0
    assert list(iter(player_service)) == []
    assert player_service[0] is None
    assert player_service.get_player(0) is None


async def test_mark_dirty(player_factory, player_service):
    player = player_factory()
    player_service[0] = player

    # Marking the same player as dirty multiple times should not matter
    player_service.mark_dirty(player)
    assert player_service._dirty_players == {player}
    player_service.mark_dirty(player)
    assert player_service._dirty_players == {player}

    assert player_service.pop_dirty_players() == {player}
    assert player_service._dirty_players == set()


async def test_update_data(player_service):
    await player_service.update_data()
    assert player_service.is_uniqueid_exempt(1) is True
