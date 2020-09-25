import asyncio
from unittest import mock

import asynctest
import pytest
from asynctest import CoroutineMock, exhaust_callbacks

from server import GameConnection
from server.abc.base_game import GameConnectionState
from server.games import Game
from server.games.game import GameState, ValidityState, Victory
from server.players import PlayerState
from server.protocol import DisconnectedError

pytestmark = pytest.mark.asyncio


@pytest.fixture
def real_game(event_loop, database, game_service, game_stats_service):
    game = Game(42, database, game_service, game_stats_service)
    yield game


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

    async def fake_send_dc(command, *args):
        await asyncio.sleep(1)  # Take some time
        disconnect_done.success()
        return "OK"

    # Set up a peer that will disconnect without error
    ok_disconnect = asynctest.create_autospec(GameConnection)
    ok_disconnect.state = GameConnectionState.CONNECTED_TO_HOST
    ok_disconnect.send_gpgnet_message = fake_send_dc

    # Set up a peer that will throw an exception
    fail_disconnect = asynctest.create_autospec(GameConnection)
    fail_disconnect.send_gpgnet_message.side_effect = Exception("Test exception")
    fail_disconnect.state = GameConnectionState.CONNECTED_TO_HOST

    # Add the peers to the game
    real_game.add_game_connection(fail_disconnect)
    real_game.add_game_connection(ok_disconnect)

    await game_connection.disconnect_all_peers()

    disconnect_done.success.assert_called_once()


async def test_connect_to_peer(game_connection):
    peer = asynctest.create_autospec(GameConnection)

    await game_connection.connect_to_peer(peer)

    peer.send_gpgnet_message.assert_called_with(
        "ConnectToPeer", "Paula_Bean", 1, False
    )


async def test_connect_to_peer_disconnected(game_connection):
    # Weak reference has dissapeared
    await game_connection.connect_to_peer(None)

    peer = asynctest.create_autospec(GameConnection)
    peer.send_gpgnet_message.side_effect = DisconnectedError("Test error")

    # The client disconnects right as we send the message
    await game_connection.connect_to_peer(peer)


async def test_on_message_received_GameState_idle_adds_connection(
    game: Game,
    game_connection: GameConnection,
    players
):
    players.joining.game = game
    game_connection.player = players.hosting
    game_connection.game = game

    await game_connection.on_message_received({
        "command": "GameState",
        "args": ["Idle"]
    })

    game.add_game_connection.assert_called_with(game_connection)


async def test_on_message_received_GameState_idle_non_searching_player_aborts(
    game_connection: GameConnection,
    players
):
    game_connection.player = players.hosting
    game_connection.lobby = mock.Mock()
    game_connection.abort = CoroutineMock()
    players.hosting.state = PlayerState.IDLE

    await game_connection.on_message_received({
        "command": "GameState",
        "args": ["Idle"]
    })

    game_connection.abort.assert_any_call()


async def test_on_message_received_GameState_lobby_sends_HostGame(
    game: Game,
    game_connection: GameConnection,
    event_loop,
    players
):
    game_connection.player = players.hosting
    game.map_file_path = "maps/some_map.zip"
    game.map_folder_name = "some_map"

    await game_connection.on_message_received({
        "command": "GameState",
        "args": ["Lobby"]
    })
    await exhaust_callbacks(event_loop)

    assert_message_sent(game_connection, "HostGame", (game.map_folder_name,))


async def test_on_message_received_GameState_lobby_calls_ConnectToHost(
    game: Game,
    game_connection: GameConnection,
    event_loop,
    players
):
    game_connection.send = CoroutineMock()
    game_connection.connect_to_host = CoroutineMock()
    game_connection.player = players.joining
    players.joining.game = game
    game.host = players.hosting
    game.map_file_path = "maps/some_map.zip"
    game.map_folder_name = "some_map"

    await game_connection.on_message_received({
        "command": "GameState",
        "args": ["Lobby"]
    })
    await exhaust_callbacks(event_loop)

    game_connection.connect_to_host.assert_called_with(players.hosting.game_connection)


async def test_on_message_received_GameState_lobby_calls_ConnectToPeer(
    game: Game,
    game_connection: GameConnection,
    event_loop,
    players
):
    game_connection.send = CoroutineMock()
    game_connection.connect_to_host = CoroutineMock()
    game_connection.connect_to_peer = CoroutineMock()
    game_connection.player = players.joining

    players.joining.game = game

    game.host = players.hosting
    game.map_file_path = "maps/some_map.zip"
    game.map_folder_name = "some_map"
    peer_conn = mock.Mock()
    players.peer.game_connection = peer_conn
    game.connections = [peer_conn]

    await game_connection.on_message_received({
        "command": "GameState",
        "args": ["Lobby"]
    })
    await exhaust_callbacks(event_loop)

    game_connection.connect_to_peer.assert_called_with(peer_conn)


async def test_handle_lobby_state_handles_GameError(
    real_game: Game,
    game_connection: GameConnection,
    event_loop,
    players
):
    game_connection.abort = CoroutineMock()
    game_connection.connect_to_host = CoroutineMock()
    game_connection.player = players.joining
    game_connection.game = real_game

    players.joining.game = real_game

    real_game.host = players.hosting
    real_game.state = GameState.ENDED

    await game_connection.on_message_received({
        "command": "GameState",
        "args": ["Lobby"]
    })
    await exhaust_callbacks(event_loop)

    game_connection.abort.assert_called_once()


async def test_on_message_received_GameState_lobby_calls_abort(
    game: Game,
    game_connection: GameConnection,
    event_loop,
    players
):
    game_connection.send = CoroutineMock()
    game_connection.abort = CoroutineMock()
    game_connection.player = players.joining
    players.joining.game = game
    game.host = players.hosting
    game.host.state = PlayerState.IDLE
    game.map_file_path = "maps/some_map.zip"
    game.map_folder_name = "some_map"

    await game_connection.on_message_received({
        "command": "GameState",
        "args": ["Lobby"]
    })
    await exhaust_callbacks(event_loop)

    game_connection.abort.assert_called_once()


async def test_on_message_received_GameState_launching_calls_launch(
    game: Game,
    game_connection: GameConnection,
    players
):
    game_connection.player = players.hosting
    game_connection.game = game
    game.launch = CoroutineMock()

    await game_connection.on_message_received({
        "command": "GameState",
        "args": ["Launching"]
    })

    game.launch.assert_any_call()


async def test_on_message_received_GameState_ended_calls_on_connection_lost(
    game_connection: GameConnection
):
    game_connection.on_connection_lost = CoroutineMock()
    await game_connection.on_message_received({
        "command": "GameState",
        "args": ["Ended"]
    })
    game_connection.on_connection_lost.assert_called_once_with()


async def test_on_message_received_PlayerOption(game: Game, game_connection: GameConnection):
    await game_connection.on_message_received({
        "command": "PlayerOption",
        "args": [1, "Color", 2]
    })
    game.set_player_option.assert_called_once_with(1, "Color", 2)


async def test_on_message_received_PlayerOption_malformed_no_raise(game_connection: GameConnection):
    await game_connection.on_message_received({
        "command": "PlayerOption",
        "args": [1, "Sheeo", "Color", 2]
    })
    # Shouldn't raise an exception


async def test_on_message_received_PlayerOption_not_host(
    game: Game,
    game_connection: GameConnection,
    players
):
    game_connection.player = players.joining
    await game_connection.on_message_received({
        "command": "PlayerOption",
        "args": [1, "Color", 2]
    })
    game.set_player_option.assert_not_called()


async def test_on_message_received_GameMods(game: Game, game_connection: GameConnection):
    await game_connection.on_message_received({
        "command": "GameMods",
        "args": ["uids", "foo baz"]
    })
    assert game.mods == {"baz": "test-mod2", "foo": "test-mod"}


async def test_on_message_received_GameMods_activated(game: Game, game_connection: GameConnection):
    game.mods = {"a": "b"}
    await game_connection.on_message_received({
        "command": "GameMods",
        "args": ["activated", 0]
    })
    assert game.mods == {}
    await game_connection.on_message_received({
        "command": "GameMods",
        "args": ["activated", "0"]
    })
    assert game.mods == {}


async def test_on_message_received_GameMods_unknown(game_connection: GameConnection):
    # No exceptions raised
    await game_connection.on_message_received({
        "command": "GameMods",
        "args": ["unknown", 0]
    })


async def test_on_message_received_GameMods_not_host(
    game: Game,
    game_connection: GameConnection,
    players
):
    game_connection.player = players.joining
    mods = game.mods
    await game_connection.on_message_received({
        "command": "GameMods",
        "args": ["uids", "foo baz"]
    })
    assert game.mods == mods


async def test_on_message_received_GameMods_post_launch_updates_played_cache(
    game: Game,
    game_connection: GameConnection,
    database
):
    game.launch = CoroutineMock()
    game.remove_game_connection = CoroutineMock()

    await game_connection.on_message_received({
        "command": "GameMods",
        "args": ["uids", "foo bar EA040F8E-857A-4566-9879-0D37420A5B9D"]
    })
    await game_connection.on_message_received({
        "command": "GameState",
        "args": ["Launching"]
    })

    async with database.acquire() as conn:
        result = await conn.execute("select `played` from table_mod where uid=%s", ("EA040F8E-857A-4566-9879-0D37420A5B9D", ))
        row = await result.fetchone()
        assert 2 == row[0]


async def test_on_message_received_AIOption(game: Game, game_connection: GameConnection):
    await game_connection.on_message_received({
        "command": "AIOption",
        "args": ["QAI", "StartSpot", 1]
    })
    game.set_ai_option.assert_called_once_with("QAI", "StartSpot", 1)


async def test_on_message_received_AIOption_not_host(
    game: Game,
    game_connection: GameConnection,
    players
):
    game_connection.player = players.joining
    await game_connection.on_message_received({
        "command": "AIOption",
        "args": ["QAI", "StartSpot", 1]
    })
    game.set_ai_option.assert_not_called()


async def test_on_message_received_ClearSlot(game: Game, game_connection: GameConnection):
    await game_connection.on_message_received({
        "command": "ClearSlot",
        "args": [1]
    })
    game.clear_slot.assert_called_once_with(1)
    await game_connection.on_message_received({
        "command": "ClearSlot",
        "args": ["1"]
    })
    game.clear_slot.assert_called_with(1)


async def test_on_message_received_ClearSlot_not_host(
    game: Game,
    game_connection: GameConnection,
    players
):
    game_connection.player = players.joining
    await game_connection.on_message_received({
        "command": "ClearSlot",
        "args": [1]
    })
    game.clear_slot.assert_not_called()


async def test_on_message_received_GameResult_calls_add_result(game: Game, game_connection: GameConnection):
    game_connection.connect_to_host = CoroutineMock()

    await game_connection.on_message_received({
        "command": "GameResult",
        "args": [0, "score -5"]
    })
    game.add_result.assert_called_once_with(game_connection.player.id, 0, "score", -5)


async def test_on_message_received_GameOption(game: Game, game_connection: GameConnection):
    game.gameOptions = {"AIReplacement": "Off"}
    await game_connection.on_message_received({
        "command": "GameOption",
        "args": ["Victory", "sandbox"]
    })
    assert game.gameOptions["Victory"] == Victory.SANDBOX
    await game_connection.on_message_received({
        "command": "GameOption",
        "args": ["AIReplacement", "On"]
    })
    assert game.gameOptions["AIReplacement"] == "On"
    await game_connection.on_message_received({
        "command": "GameOption",
        "args": ["Slots", "7"]
    })
    assert game.max_players == 7
    # I don't know what these paths actually look like
    await game_connection.on_message_received({
        "command": "GameOption",
        "args": ["ScenarioFile", "C:\\Maps\\Some_Map"]
    })
    assert game.map_file_path == "maps/some_map.zip"
    await game_connection.on_message_received({
        "command": "GameOption",
        "args": ["Title", "All welcome"]
    })
    assert game.name == game.sanitize_name("All welcome")
    await game_connection.on_message_received({
        "command": "GameOption",
        "args": ["ArbitraryKey", "ArbitraryValue"]
    })
    assert game.gameOptions["ArbitraryKey"] == "ArbitraryValue"


async def test_on_message_received_GameOption_not_host(
    game: Game,
    game_connection: GameConnection,
    players
):
    game_connection.player = players.joining
    game.gameOptions = {"Victory": "asdf"}
    await game_connection.on_message_received({
        "command": "GameOption",
        "args": ["Victory", "sandbox"]
    })
    assert game.gameOptions == {"Victory": "asdf"}


async def test_json_stats(game_connection: GameConnection, game_stats_service, players, game):
    game_stats_service.process_game_stats = mock.Mock()
    await game_connection.on_message_received({
        "command": "JsonStats",
        "args": ['{"stats": {}}']
    })
    game.report_army_stats.assert_called_once_with('{"stats": {}}')


async def test_on_message_received_EnforceRating(game: Game, game_connection: GameConnection):
    await game_connection.on_message_received({
        "command": "EnforceRating",
        "args": []
    })
    assert game.enforce_rating is True


async def test_on_message_received_TeamkillReport(game: Game, game_connection: GameConnection, database):
    game.launch = CoroutineMock()
    await game_connection.on_message_received({
        "command": "TeamkillReport",
        "args": ["200", "2", "Dostya", "3", "Rhiza"]
    })

    async with database.acquire() as conn:
        result = await conn.execute(
            "select game_id,id from moderation_report where reporter_id=2 and game_id=%s and game_incident_timecode=200",
            game.id
        )
        report = await result.fetchone()
        assert report is None


async def test_on_message_received_TeamkillHappened(game: Game, game_connection: GameConnection, database):
    game.launch = CoroutineMock()
    await game_connection.on_message_received({
        "command": "TeamkillHappened",
        "args": ["200", "2", "Dostya", "3", "Rhiza"]
    })

    async with database.acquire() as conn:
        result = await conn.execute("select game_id from teamkills where victim=2 and teamkiller=3 and game_id=%s and gametime=200",
                                    game.id)
        row = await result.fetchone()
        assert game.id == row[0]


async def test_on_message_received_TeamkillHappened_AI(game: Game, game_connection: GameConnection, database):
    # Should fail with a sql constraint error if this isn't handled correctly
    game_connection.abort = CoroutineMock()
    await game_connection.on_message_received({
        "command": "TeamkillHappened",
        "args": ["200", 0, "Dostya", "0", "Rhiza"]
    })
    game_connection.abort.assert_not_called()


async def test_on_message_received_GameEnded_ends_sim(
    game: Game,
    game_connection: GameConnection
):
    game.ended = False
    await game_connection.on_message_received({
        "command": "GameEnded",
        "args": []
    })

    assert game_connection.finished_sim
    game.check_sim_end.assert_called_once()
    game.on_game_end.assert_not_called()


async def test_on_message_received_GameEnded_ends_game(
    game: Game,
    game_connection: GameConnection
):
    game.ended = True
    await game_connection.on_message_received({
        "command": "GameEnded",
        "args": []
    })

    assert game_connection.finished_sim
    game.check_sim_end.assert_called_once()
    game.on_game_end.assert_called_once()


async def test_on_message_received_OperationComplete(ugame: Game, game_connection: GameConnection, database):
    """
        Sends an OperationComplete action to handle action and verifies that
    the `coop_leaderboard` table is updated accordingly.

    Requires that the map from `game.map_file_path` exists in the database.
    """

    ugame.map_file_path = "maps/prothyon16.v0005.zip"
    ugame.validity = ValidityState.COOP_NOT_RANKED
    game_connection.game = ugame

    secondary = 1
    time_taken = "09:08:07.654321"
    await game_connection.on_message_received({
        "command": "OperationComplete",
        "args": ["1", secondary, time_taken]
    })

    async with database.acquire() as conn:
        result = await conn.execute(
            "SELECT secondary, gameuid from `coop_leaderboard` where gameuid=%s",
            ugame.id
        )
        row = await result.fetchone()

    assert (secondary, ugame.id) == (row[0], row[1])


async def test_on_message_received_OperationComplete_invalid(ugame: Game, game_connection: GameConnection, database):
    """
        Sends an OperationComplete action to handle action and verifies that
    the `coop_leaderboard` table is updated accordingly.

    Requires that the map from `game.map_file_path` exists in the database.
    """

    ugame.map_file_path = "maps/prothyon16.v0005.zip"
    ugame.validity = ValidityState.OTHER_UNRANK
    game_connection.game = ugame

    secondary = 1
    time_taken = "09:08:07.654321"
    await game_connection.on_message_received({
        "command": "OperationComplete",
        "args": ["1", secondary, time_taken]
    })

    async with database.acquire() as conn:
        result = await conn.execute(
            "SELECT secondary, gameuid from `coop_leaderboard` where gameuid=%s",
            ugame.id
        )
        row = await result.fetchone()

    assert row is None


async def test_on_message_received_IceMsg(
    game_connection: GameConnection,
    player_service,
    player_factory
):
    peer = player_factory(player_id=2)
    peer.game_connection = asynctest.create_autospec(GameConnection)
    player_service[peer.id] = peer
    await game_connection.on_message_received({
        "command": "IceMsg",
        "args": [2, "the message"]
    })

    peer.game_connection.send.assert_called_once_with({
        "command": "IceMsg",
        "args": [game_connection.player.id, "the message"]
    })


async def test_on_message_received_IceMsg_for_non_existent_player(
    game_connection: GameConnection,
):
    # No exceptions raised
    await game_connection.on_message_received({
        "command": "IceMsg",
        "args": [3826, "the message"]
    })


async def test_on_message_received_IceMsg_for_non_connected(
    game_connection: GameConnection,
    player_service,
    player_factory
):
    peer = player_factory(player_id=2)
    del peer.game_connection
    player_service[peer.id] = peer
    # No exceptions raised
    await game_connection.on_message_received({
        "command": "IceMsg",
        "args": [2, "the message"]
    })


async def test_on_message_received_desync(game_connection: GameConnection):
    game_connection.game.desyncs = 0
    await game_connection.on_message_received({
        "command": "Desync",
        "args": []
    })
    assert game_connection.game.desyncs == 1


@pytest.mark.parametrize("action", (
    "Rehost",
    "Bottleneck",
    "BottleneckCleared",
    "Disconnected",
    "GameFull"
))
async def test_on_message_received_ignored(game_connection: GameConnection, action):
    # No exceptions raised
    await game_connection.on_message_received({"command": action, "args": []})


async def test_on_message_received_Chat_ignored(game_connection: GameConnection):
    # No exceptions raised
    await game_connection.on_message_received({"command": "Chat", "args": ["Test"]})


async def test_on_message_received_invalid(game_connection: GameConnection):
    game_connection.abort = CoroutineMock()

    await game_connection.on_message_received({
        "command": "ThisDoesntExist",
        "args": [1, 2, 3]
    })

    game_connection.abort.assert_not_called()
    game_connection.protocol.send_message.assert_not_called()
