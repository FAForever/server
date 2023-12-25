import asyncio
import logging
from datetime import datetime
from unittest import mock

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from server import GameConnection
from server.db.models import coop_leaderboard, game_stats
from server.games import (
    CoopGame,
    Game,
    GameConnectionState,
    GameState,
    ValidityState,
    Victory
)
from server.players import PlayerState
from server.protocol import DisconnectedError
from tests.utils import exhaust_callbacks


@pytest.fixture
async def real_game(event_loop, database, game_service, game_stats_service):
    return Game(42, database, game_service, game_stats_service)


def assert_message_sent(game_connection: GameConnection, command, args):
    game_connection.protocol.send_message.assert_called_with({
        "command": command,
        "target": "game",
        "args": args
    })


async def test_abort(game_connection: GameConnection, game: Game, players):
    game_connection.player = players.hosting
    game_connection.game = game

    await game_connection.abort()

    game.remove_game_connection.assert_called_with(game_connection)


async def test_disconnect_all_peers(
    game_connection: GameConnection,
    real_game: Game,
    players
):
    real_game.state = GameState.LOBBY
    game_connection.player = players.hosting
    game_connection.game = real_game

    disconnect_done = mock.Mock()

    async def fake_send_dc(player_id):
        await asyncio.sleep(1)  # Take some time
        disconnect_done.success()
        return "OK"

    # Set up a peer that will disconnect without error
    ok_disconnect = mock.create_autospec(GameConnection)
    ok_disconnect.state = GameConnectionState.CONNECTED_TO_HOST
    ok_disconnect.send_DisconnectFromPeer = fake_send_dc

    # Set up a peer that will throw an exception
    fail_disconnect = mock.create_autospec(GameConnection)
    fail_disconnect.send_DisconnectFromPeer.return_value = Exception("Test exception")
    fail_disconnect.state = GameConnectionState.CONNECTED_TO_HOST

    # Add the peers to the game
    real_game.add_game_connection(fail_disconnect)
    real_game.add_game_connection(ok_disconnect)

    await game_connection.disconnect_all_peers()

    disconnect_done.success.assert_called_once()


async def test_connect_to_peer(game_connection):
    peer = mock.create_autospec(GameConnection)

    await game_connection.connect_to_peer(peer)

    peer.send_ConnectToPeer.assert_called_once()


async def test_connect_to_peer_disconnected(game_connection):
    # Weak reference has dissapeared
    await game_connection.connect_to_peer(None)

    peer = mock.create_autospec(GameConnection)
    peer.send_ConnectToPeer.side_effect = DisconnectedError("Test error")

    # The client disconnects right as we send the message
    await game_connection.connect_to_peer(peer)


async def test_handle_action_GameState_idle_adds_connection(
    game: Game,
    game_connection: GameConnection,
    players
):
    players.joining.game = game
    game_connection.player = players.hosting
    game_connection.game = game

    await game_connection.handle_action("GameState", ["Idle"])

    game.add_game_connection.assert_called_with(game_connection)


async def test_handle_action_GameState_idle_sets_player_state(
    game_connection: GameConnection,
    players
):
    game_connection.player = players.hosting
    game_connection.lobby = mock.Mock()
    game_connection.abort = mock.AsyncMock()
    players.hosting.state = PlayerState.IDLE

    await game_connection.handle_action("GameState", ["Idle"])

    assert players.hosting.state == PlayerState.HOSTING

    game_connection.player = players.joining
    players.joining.state = PlayerState.IDLE

    await game_connection.handle_action("GameState", ["Idle"])

    assert players.joining.state == PlayerState.JOINING


async def test_handle_action_GameState_lobby_sends_HostGame(
    game: Game,
    game_connection: GameConnection,
    event_loop,
    players
):
    game_connection.player = players.hosting
    game.map_file_path = "maps/some_map.zip"
    game.map_folder_name = "some_map"

    await game_connection.handle_action("GameState", ["Lobby"])
    await exhaust_callbacks(event_loop)

    assert_message_sent(game_connection, "HostGame", [game.map_folder_name])


async def test_handle_action_GameState_lobby_calls_ConnectToHost(
    game: Game,
    game_connection: GameConnection,
    event_loop,
    players
):
    game_connection.send = mock.AsyncMock()
    game_connection.connect_to_host = mock.AsyncMock()
    game_connection.player = players.joining
    players.joining.game = game
    game.host = players.hosting
    game.map_file_path = "maps/some_map.zip"
    game.map_folder_name = "some_map"

    await game_connection.handle_action("GameState", ["Lobby"])
    await exhaust_callbacks(event_loop)

    game_connection.connect_to_host.assert_called_with(players.hosting.game_connection)


async def test_handle_action_GameState_lobby_calls_ConnectToPeer(
    game: Game,
    game_connection: GameConnection,
    event_loop,
    players
):
    game_connection.send = mock.AsyncMock()
    game_connection.connect_to_host = mock.AsyncMock()
    game_connection.connect_to_peer = mock.AsyncMock()
    game_connection.player = players.joining

    players.joining.game = game

    game.host = players.hosting
    game.map_file_path = "maps/some_map.zip"
    game.map_folder_name = "some_map"
    peer_conn = mock.Mock()
    players.peer.game_connection = peer_conn
    game.connections = [peer_conn]

    await game_connection.handle_action("GameState", ["Lobby"])
    await exhaust_callbacks(event_loop)

    game_connection.connect_to_peer.assert_called_with(peer_conn)


async def test_handle_lobby_state_handles_GameError(
    real_game: Game,
    game_connection: GameConnection,
    event_loop,
    players
):
    game_connection.abort = mock.AsyncMock()
    game_connection.connect_to_host = mock.AsyncMock()
    game_connection.player = players.joining
    game_connection.game = real_game

    players.joining.game = real_game

    real_game.host = players.hosting
    real_game.state = GameState.ENDED

    await game_connection.handle_action("GameState", ["Lobby"])
    await exhaust_callbacks(event_loop)

    game_connection.abort.assert_called_once()


async def test_handle_action_GameState_lobby_calls_abort(
    game: Game,
    game_connection: GameConnection,
    event_loop,
    players
):
    game_connection.send = mock.AsyncMock()
    game_connection.abort = mock.AsyncMock()
    game_connection.player = players.joining
    players.joining.game = game
    game.host = players.hosting
    game.host.state = PlayerState.IDLE
    game.map_file_path = "maps/some_map.zip"
    game.map_folder_name = "some_map"

    await game_connection.handle_action("GameState", ["Lobby"])
    await exhaust_callbacks(event_loop)

    game_connection.abort.assert_called_once()


async def test_handle_action_GameState_launching_calls_launch(
    game: Game,
    game_connection: GameConnection,
    players
):
    game_connection.player = players.hosting
    game_connection.game = game
    game.launch = mock.AsyncMock()
    game.state = GameState.LOBBY

    await game_connection.handle_action("GameState", ["Launching"])

    game.launch.assert_any_call()


async def test_handle_action_GameState_launching_when_ended(
    game: Game,
    game_connection: GameConnection,
    players
):
    game_connection.player = players.hosting
    game_connection.game = game
    game.launch = mock.AsyncMock()
    game.state = GameState.ENDED

    await game_connection.handle_action("GameState", ["Launching"])

    game.launch.assert_not_called()


async def test_handle_action_GameState_ended_calls_on_connection_lost(
    game_connection: GameConnection
):
    game_connection.on_connection_lost = mock.AsyncMock()
    await game_connection.handle_action("GameState", ["Ended"])
    game_connection.on_connection_lost.assert_called_once_with()


async def test_handle_action_PlayerOption(game: Game, game_connection: GameConnection):
    await game_connection.handle_action("PlayerOption", [1, "Color", 2])
    game.set_player_option.assert_called_once_with(1, "Color", 2)


async def test_handle_action_PlayerOption_malformed_no_raise(game_connection: GameConnection):
    await game_connection.handle_action("PlayerOption", [1, "Sheeo", "Color", 2])
    # Shouldn't raise an exception


async def test_handle_action_PlayerOption_not_host(
    game: Game,
    game_connection: GameConnection,
    players
):
    game_connection.player = players.joining
    await game_connection.handle_action("PlayerOption", [1, "Color", 2])
    game.set_player_option.assert_not_called()


async def test_handle_action_GameMods(game: Game, game_connection: GameConnection):
    await game_connection.handle_action("GameMods", ["uids", "foo baz"])
    assert game.mods == {"baz": "test-mod2", "foo": "test-mod"}


async def test_handle_action_GameMods_activated(game: Game, game_connection: GameConnection):
    game.mods = {"a": "b"}
    await game_connection.handle_action("GameMods", ["activated", 0])
    assert game.mods == {}
    await game_connection.handle_action("GameMods", ["activated", "0"])
    assert game.mods == {}


async def test_handle_action_GameMods_not_host(
    game: Game,
    game_connection: GameConnection,
    players
):
    game_connection.player = players.joining
    mods = game.mods
    await game_connection.handle_action("GameMods", ["uids", "foo baz"])
    assert game.mods == mods


async def test_handle_action_GameMods_post_launch_updates_played_cache(
    game: Game,
    game_connection: GameConnection,
    database
):
    game.launch = mock.AsyncMock()
    game.state = GameState.LOBBY
    game.remove_game_connection = mock.AsyncMock()

    await game_connection.handle_action("GameMods", ["uids", "foo bar EA040F8E-857A-4566-9879-0D37420A5B9D"])
    await game_connection.handle_action("GameState", ["Launching"])

    async with database.acquire() as conn:
        result = await conn.execute(
            "select `played` from table_mod where uid=:uid",
            {"uid": "EA040F8E-857A-4566-9879-0D37420A5B9D"}
        )
        row = result.fetchone()
        assert row.played == 2


async def test_handle_action_AIOption(
    game: Game,
    game_connection: GameConnection
):
    await game_connection.handle_action("AIOption", ["QAI", "StartSpot", 1])
    game.set_ai_option.assert_called_once_with("QAI", "StartSpot", 1)


async def test_handle_action_AIOption_not_host(
    game: Game,
    game_connection: GameConnection,
    players
):
    game_connection.player = players.joining
    await game_connection.handle_action("AIOption", ["QAI", "StartSpot", 1])
    game.set_ai_option.assert_not_called()


async def test_handle_action_ClearSlot(
    game: Game,
    game_connection: GameConnection
):
    await game_connection.handle_action("ClearSlot", [1])
    game.clear_slot.assert_called_once_with(1)
    await game_connection.handle_action("ClearSlot", ["1"])
    game.clear_slot.assert_called_with(1)


async def test_handle_action_ClearSlot_not_host(
    game: Game,
    game_connection: GameConnection,
    players
):
    game_connection.player = players.joining
    await game_connection.handle_action("ClearSlot", [1])
    game.clear_slot.assert_not_called()


async def test_handle_action_GameResult_calls_add_result(
    game: Game,
    game_connection: GameConnection
):
    game_connection.connect_to_host = mock.AsyncMock()

    await game_connection.handle_action("GameResult", [0, "score -5"])
    game.add_result.assert_called_once_with(game_connection.player.id, 0, "score", -5, frozenset())


async def test_cannot_parse_game_results(
    game: Game,
    game_connection: GameConnection,
    caplog
):
    game_connection.connect_to_host = mock.AsyncMock()

    with caplog.at_level(logging.WARNING):
        await game_connection.handle_action("GameResult", [0, ""])
        game.add_result.assert_not_called()
        assert "Invalid result" in caplog.messages[0]


async def test_handle_action_GameOption(
    game: Game,
    game_connection: GameConnection
):
    game.gameOptions = {"AIReplacement": "Off"}
    await game_connection.handle_action("GameOption", ["Victory", "sandbox"])
    assert game.gameOptions["Victory"] == Victory.SANDBOX
    await game_connection.handle_action("GameOption", ["AIReplacement", "On"])
    assert game.gameOptions["AIReplacement"] == "On"
    await game_connection.handle_action("GameOption", ["Slots", "7"])
    assert game.max_players == 7
    # I don't know what these paths actually look like
    await game_connection.handle_action("GameOption", ["ScenarioFile", "C:\\Maps\\Some_Map"])
    assert game.map_name == "some_map"
    await game_connection.handle_action("GameOption", ["Title", "All welcome"])
    assert game.name == "All welcome"
    await game_connection.handle_action("GameOption", ["ArbitraryKey", "ArbitraryValue"])
    assert game.gameOptions["ArbitraryKey"] == "ArbitraryValue"


async def test_handle_action_GameOption_not_host(
    game: Game,
    game_connection: GameConnection,
    players
):
    game_connection.player = players.joining
    game.gameOptions = {"Victory": "asdf"}
    await game_connection.handle_action("GameOption", ["Victory", "sandbox"])
    assert game.gameOptions == {"Victory": "asdf"}


async def test_json_stats(
    real_game: Game,
    game_connection: GameConnection,
):
    game_connection.game = real_game
    await game_connection.handle_action("JsonStats", ['{"stats": {}}'])


async def test_json_stats_malformed(
    real_game: Game,
    game_connection: GameConnection,
):
    game_connection.game = real_game
    await game_connection.handle_action("JsonStats", ['{"stats": {}'])


async def test_handle_action_EnforceRating(
    game: Game,
    game_connection: GameConnection
):
    await game_connection.handle_action("EnforceRating", [])
    assert game.enforce_rating is True


async def test_handle_action_TeamkillReport(
    game: Game,
    game_connection: GameConnection,
    database
):
    game.launch = mock.AsyncMock()
    await game_connection.handle_action("TeamkillReport", ["200", "2", "Dostya", "3", "Rhiza"])

    async with database.acquire() as conn:
        result = await conn.execute(
            "select game_id,id from moderation_report where reporter_id=2 and "
            "game_id=:id and game_incident_timecode=200",
            {"id": game.id}
        )
        report = result.fetchone()
        assert report is None


async def test_handle_action_TeamkillHappened(
    game: Game,
    game_connection: GameConnection, database
):
    game.launch = mock.AsyncMock()
    await game_connection.handle_action("TeamkillHappened", ["200", "2", "Dostya", "3", "Rhiza"])

    async with database.acquire() as conn:
        result = await conn.execute(
            "select game_id from teamkills where victim=2 and teamkiller=3 and "
            "game_id=:id and gametime=200",
            {"id": game.id}
        )
        row = result.fetchone()
        assert game.id == row.game_id


async def test_handle_action_TeamkillHappened_AI(
    game: Game,
    game_connection: GameConnection,
    database
):
    # Should fail with a sql constraint error if this isn't handled correctly
    game_connection.abort = mock.AsyncMock()
    await game_connection.handle_action("TeamkillHappened", ["200", 0, "Dostya", "0", "Rhiza"])
    game_connection.abort.assert_not_called()


async def test_handle_action_GameEnded_ends_sim(
    game: Game,
    game_connection: GameConnection
):
    await game_connection.handle_action("GameEnded", [])

    assert game_connection.finished_sim
    game.check_game_finish.assert_called_once()


@pytest.mark.parametrize(
    "primary,secondary",
    [(1, 1), (True, True), ("True", "True"), ("true", "true")],
)
async def test_handle_action_OperationComplete(
    primary,
    secondary,
    coop_game: CoopGame,
    game_connection: GameConnection,
    database,
):
    coop_game.id = 1  # reuse existing corresponding game_stats row
    coop_game.map_file_path = "maps/prothyon16.v0005.zip"
    game_connection.game = coop_game
    time_taken = "09:08:07.654321"

    await game_connection.handle_action(
        "OperationComplete", [primary, secondary, time_taken]
    )

    async with database.acquire() as conn:
        result = await conn.execute(
            select(
                coop_leaderboard.c.secondary,
                coop_leaderboard.c.gameuid
            ).where(coop_leaderboard.c.gameuid == coop_game.id),
        )

        row = result.fetchone()
        assert (row.secondary, row.gameuid) == (1, coop_game.id)


@pytest.mark.parametrize("primary", [0, False, "False", "false"])
async def test_handle_action_OperationComplete_primary_incomplete(
    primary, coop_game: CoopGame, game_connection: GameConnection, database
):
    coop_game.map_file_path = "maps/prothyon16.v0005.zip"
    game_connection.game = coop_game
    time_taken = "09:08:07.654321"

    await game_connection.handle_action(
        "OperationComplete", [primary, 1, time_taken]
    )

    async with database.acquire() as conn:
        result = await conn.execute(
            select(
                coop_leaderboard.c.secondary,
                coop_leaderboard.c.gameuid
            ).where(coop_leaderboard.c.gameuid == coop_game.id),
        )

        row = result.fetchone()
        assert row is None


async def test_handle_action_OperationComplete_non_coop_game(
    ugame: Game, game_connection: GameConnection, database
):
    ugame.map_file_path = "maps/prothyon16.v0005.zip"
    game_connection.game = ugame
    time_taken = "09:08:07.654321"

    await game_connection.handle_action(
        "OperationComplete", [1, 1, time_taken]
    )

    async with database.acquire() as conn:
        result = await conn.execute(
            select(
                coop_leaderboard.c.secondary,
                coop_leaderboard.c.gameuid
            ).where(coop_leaderboard.c.gameuid == ugame.id),
        )

        row = result.fetchone()
        assert row is None


async def test_handle_action_OperationComplete_invalid(
    coop_game: CoopGame, game_connection: GameConnection, database
):
    coop_game.map_file_path = "maps/prothyon16.v0005.zip"
    coop_game.validity = ValidityState.OTHER_UNRANK
    game_connection.game = coop_game
    time_taken = "09:08:07.654321"

    await game_connection.handle_action(
        "OperationComplete", [1, 1, time_taken]
    )

    async with database.acquire() as conn:
        result = await conn.execute(
            select(
                coop_leaderboard.c.secondary,
                coop_leaderboard.c.gameuid
            ).where(coop_leaderboard.c.gameuid == coop_game.id),
        )

        row = result.fetchone()
        assert row is None


async def test_handle_action_OperationComplete_duplicate(
    coop_game: CoopGame, game_connection: GameConnection, database, caplog
):
    coop_game.map_file_path = "maps/prothyon16.v0005.zip"
    game_connection.game = coop_game
    time_taken = "09:08:07.654321"

    async with database.acquire() as conn:
        # OperationComplete expects an existing corresponding game_stats row,
        # we automatically add such a row for coop_game.id == 1 in
        # test-data.sql
        await conn.execute(
            game_stats.insert().values(
                id=coop_game.id,
                startTime=datetime.utcnow(),
                gameName="Another test game",
                gameType="0",
                gameMod=6,
                host=1,
                mapId=1,
                validity=0,
            )
        )

    with caplog.at_level(logging.ERROR):
        await game_connection.handle_action(
            "OperationComplete", [1, 1, time_taken]
        )
        caplog.clear()
        await game_connection.handle_action(
            "OperationComplete", [1, 1, time_taken]
        )

        assert not any(
            record.exc_info
            and isinstance(record.exc_info[1], IntegrityError)
            for record in caplog.records
        )


async def test_handle_action_IceMsg(
    game_connection: GameConnection,
    player_service,
    player_factory
):
    peer = player_factory(player_id=2)
    peer.game_connection = mock.create_autospec(GameConnection)
    player_service[peer.id] = peer
    await game_connection.handle_action("IceMsg", [2, "the message"])

    peer.game_connection.send.assert_called_once_with({
        "command": "IceMsg",
        "args": [game_connection.player.id, "the message"]
    })


async def test_handle_action_IceMsg_for_non_existent_player(
    game_connection: GameConnection,
):
    # No exceptions raised
    await game_connection.handle_action("IceMsg", [3826, "the message"])


async def test_handle_action_IceMsg_for_non_connected(
    game_connection: GameConnection,
    player_service,
    player_factory
):
    peer = player_factory(player_id=2)
    del peer.game_connection
    player_service[peer.id] = peer
    # No exceptions raised
    await game_connection.handle_action("IceMsg", [2, "the message"])


@pytest.mark.parametrize("action", (
    "Rehost",
    "Bottleneck",
    "BottleneckCleared",
    "Disconnected",
    "Chat",
    "GameFull"
))
async def test_handle_action_ignored(game_connection: GameConnection, action):
    # No exceptions raised
    await game_connection.handle_action(action, [])


async def test_handle_action_invalid(game_connection: GameConnection):
    game_connection.abort = mock.AsyncMock()

    await game_connection.handle_action("ThisDoesntExist", [1, 2, 3])

    game_connection.abort.assert_not_called()
    game_connection.protocol.send_message.assert_not_called()


async def test_result_format_phantom(game: Game, game_connection: GameConnection):
    await game_connection.handle_action("GameResult", [0, "phantom score -5"])
    game.add_result.assert_called_once_with(
        game_connection.player.id, 0, "score", -5, frozenset(["phantom"])
    )
