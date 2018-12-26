import asyncio
from unittest import mock
import pytest

from server import GameConnection
from server.connectivity import ConnectivityResult, ConnectivityState
from server.games import Game
from server.games.game import Victory
from server.players import PlayerState
from tests import CoroMock

LOCAL_PUBLIC = ConnectivityResult(addr='127.0.0.1:6112', state=ConnectivityState.PUBLIC)
LOCAL_STUN = ConnectivityResult(addr='127.0.0.1:6112', state=ConnectivityState.STUN)
LOCAL_PROXY = ConnectivityResult(addr=None, state=ConnectivityState.BLOCKED)


def assert_message_sent(game_connection, command, args):
    game_connection.lobby_connection.send.assert_called_with({
        'command': command,
        'target': 'game',
        'args': args
    })


def test_abort(game_connection, game, players):
    game_connection.player = players.hosting
    game_connection.game = game

    game_connection.abort()

    game.remove_game_connection.assert_called_with(game_connection)


async def test_handle_action_GameState_idle_adds_connection(game_connection, players, game):
    players.joining.game = game
    game_connection.lobby_connection = mock.Mock()
    game_connection.player = players.hosting
    game_connection.game = game

    await game_connection.handle_action('GameState', ['Idle'])

    game.add_game_connection.assert_called_with(game_connection)


async def test_handle_action_GameState_idle_non_searching_player_aborts(game_connection: GameConnection, players):
    game_connection.player = players.hosting
    game_connection.lobby = mock.Mock()
    game_connection.abort = mock.Mock()
    players.hosting.state = PlayerState.IDLE

    await game_connection.handle_action('GameState', ['Idle'])

    game_connection.abort.assert_any_call()


async def test_handle_action_GameState_lobby_sends_HostGame(game_connection: GameConnection, loop, players, game):
    game_connection.player = players.hosting
    game.map_file_path = 'maps/some_map.zip'
    game.map_folder_name = 'some_map'

    await game_connection.handle_action('GameState', ['Lobby'])
    # Give the connection coro time to run
    await asyncio.sleep(0.1)

    assert_message_sent(game_connection, 'HostGame', [game.map_folder_name])


async def test_handle_action_GameState_lobby_calls_ConnectToHost(game_connection: GameConnection, players, game):
    game_connection.send_message = mock.MagicMock()
    game_connection.ConnectToHost = CoroMock()
    game_connection.player = players.joining
    players.joining.game = game
    game.host = players.hosting
    game.map_file_path = 'maps/some_map.zip'
    game.map_folder_name = 'some_map'

    await game_connection.handle_action('GameState', ['Lobby'])
    # Give the connection coro time to run
    await asyncio.sleep(0.1)

    game_connection.ConnectToHost.assert_called_with(players.hosting.game_connection)


async def test_handle_action_GameState_lobby_calls_ConnectToPeer(game_connection: GameConnection, players, game):
    game_connection.send_message = mock.MagicMock()
    game_connection.ConnectToHost = CoroMock()
    game_connection.ConnectToPeer = CoroMock()
    game_connection.player = players.joining

    players.joining.game = game

    game.host = players.hosting
    game.map_file_path = 'maps/some_map.zip'
    game.map_folder_name = 'some_map'
    game.connections = [players.peer.game_connection]

    await game_connection.handle_action('GameState', ['Lobby'])
    # Give the connection coro time to run
    await asyncio.sleep(0.1)

    game_connection.ConnectToPeer.assert_called_with(players.peer.game_connection)


async def test_handle_action_GameState_launching_calls_launch(game_connection: GameConnection, players, game):
    game_connection.player = players.hosting
    game_connection.game = game
    game.launch = CoroMock()

    await game_connection.handle_action('GameState', ['Launching'])

    game.launch.assert_any_call()


async def test_handle_action_GameState_ended_calls_on_connection_lost(game_connection: GameConnection):
    game_connection.on_connection_lost = CoroMock()
    await game_connection.handle_action('GameState', ['Ended'])
    game_connection.on_connection_lost.assert_called_once_with()


async def test_handle_action_PlayerOption(game: Game, game_connection: GameConnection):
    await game_connection.handle_action('PlayerOption', [1, 'Color', 2])
    game.set_player_option.assert_called_once_with(1, 'Color', 2)


async def test_handle_action_PlayerOption_malformed_no_raise(game_connection: GameConnection):
    await game_connection.handle_action('PlayerOption', [1, 'Sheeo', 'Color', 2])
    # Shouldn't raise an exception


async def test_handle_action_GameMods(game: Game, game_connection: GameConnection):
    await game_connection.handle_action('GameMods', ['uids', 'foo baz'])
    assert game.mods == {'baz': 'test-mod2', 'foo': 'test-mod'}


async def test_handle_action_GameMods_activated(game: Game, game_connection: GameConnection):
    await game_connection.handle_action('GameMods', ['activated', 0])
    assert game.mods == {}
    await game_connection.handle_action('GameMods', ['activated', '0'])
    assert game.mods == {}


async def test_handle_action_GameMods_post_launch_updates_played_cache(game, game_connection, db_pool):
    game.launch = CoroMock()
    game.remove_game_connection = CoroMock()

    await game_connection.handle_action('GameMods', ['uids', 'foo bar EA040F8E-857A-4566-9879-0D37420A5B9D'])
    await game_connection.handle_action('GameState', ['Launching'])

    async with db_pool.get() as conn:
        cursor = await conn.cursor()
        await cursor.execute("select `played` from table_mod where uid=%s", ('EA040F8E-857A-4566-9879-0D37420A5B9D', ))
        assert (2,) == await cursor.fetchone()


async def test_handle_action_AIOption(game: Game, game_connection: GameConnection):
    await game_connection.handle_action('AIOption', ['QAI', 'StartSpot', 1])
    game.set_ai_option.assert_called_once_with('QAI', 'StartSpot', 1)


async def test_handle_action_ClearSlot(game: Game, game_connection: GameConnection):
    await game_connection.handle_action('ClearSlot', [1])
    game.clear_slot.assert_called_once_with(1)
    await game_connection.handle_action('ClearSlot', ['1'])
    game.clear_slot.assert_called_with(1)


async def test_handle_action_GameResult_calls_add_result(game, game_connection):
    game_connection.ConnectToHost = CoroMock()

    await game_connection.handle_action('GameResult', [0, 'score -5'])
    game.add_result.assert_called_once_with(game_connection.player, 0, 'score', -5)

async def test_handle_action_GameOption(game, game_connection):
    game.gameOptions = {"AIReplacement": "Off"}
    await game_connection.handle_action('GameOption', ['Victory', 'sandbox'])
    assert game.gameOptions['Victory'] == Victory.SANDBOX
    await game_connection.handle_action('GameOption', ['AIReplacement', 'AIReplacementOn'])
    assert game.gameOptions['AIReplacement'] == 'On'
    await game_connection.handle_action('GameOption', ['Slots', '7'])
    assert game.max_players == 7
    # I don't know what these paths actually look like
    await game_connection.handle_action('GameOption', ['ScenarioFile', 'C:\\Maps\\Some_Map'])
    assert game.map_file_path == "maps/some_map.zip"
    await game_connection.handle_action('GameOption', ['Title', 'All welcome'])
    assert game.name == game.sanitize_name('All welcome')


async def test_json_stats(game_connection, game_stats_service, players, game):
    game_stats_service.process_game_stats = mock.Mock()
    await game_connection.handle_action('JsonStats', ['{"stats": {}}'])
    game.report_army_stats.assert_called_once_with('{"stats": {}}')


async def test_handle_action_EnforceRating(game: Game, game_connection: GameConnection):
    await game_connection.handle_action('EnforceRating', [])
    assert game.enforce_rating is True


async def test_handle_action_TeamkillReport(game, game_connection, db_pool):
    game.launch = CoroMock()
    await game_connection.handle_action('TeamkillReport', ['200', '2', 'Dostya', '3', 'Rhiza'])

    async with db_pool.get() as conn:
        cursor = await conn.cursor()
        await cursor.execute("select game_id from teamkills where victim=2 and teamkiller=3 and game_id=%s and gametime=200", (game.id))

        assert (game.id,) == await cursor.fetchone()


async def test_handle_action_GameResult_victory_ends_sim(game, game_connection):
    game_connection.ConnectToHost = CoroMock()
    await game_connection.handle_action('GameResult', [0, 'victory'])

    assert game_connection.finished_sim
    assert game.check_sim_end.called


async def test_handle_action_GameResult_draw_ends_sim(game, game_connection):
    game_connection.ConnectToHost = CoroMock()
    await game_connection.handle_action('GameResult', [0, 'draw'])

    assert game_connection.finished_sim
    assert game.check_sim_end.called


async def test_handle_action_OperationComplete(game, game_connection, db_pool):
    """
        Sends an OperationComplete action to handle action and verifies that
    the `coop_leaderboard` table is updated accordingly.

    Requires that the map from `game.map_file_path` exists in the database.
    """
    pytest.skip("requires test data from faf-db:v63 which doesn't exist yet")

    game.map_file_path = "maps/prothyon16.v0005.zip"
    secondary = 1
    time_taken = '09:08:07.654321'
    await game_connection.handle_action('OperationComplete', ['1', secondary, time_taken])

    async with db_pool.get() as conn:
        cursor = await conn.cursor()
        await cursor.execute("SELECT secondary, gameuid from `coop_leaderboard` where gameuid=%s",
                             (game.id))

        assert (secondary, game.id) == await cursor.fetchone()
