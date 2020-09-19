import asyncio
import subprocess
from hashlib import sha256

from server.protocol import QDataStreamProtocol
from tests.integration_tests.conftest import read_until, read_until_command


class FAFClient(object):
    """docstring for FAFClient."""

    def __init__(self, user_agent="faf-client", version="1.0.0-dev"):
        self.proto = None
        self.user_agent = user_agent
        self.version = version
        # Name of the faf-uid binary to call
        # TODO: make this configurable via a command line arg?
        self.faf_uid_path = "faf-uid"
        self.player_id = None
        self.player_name = None

    def is_connected(self):
        return self.proto and self.proto.is_connected()

    async def close(self):
        if not self.is_connected():
            return

        await self.proto.close()

    async def connect(self, host, port):
        self.proto = QDataStreamProtocol(
            *(await asyncio.open_connection(host, port))
        )

    async def send_message(self, message):
        """Send a message to the server"""
        if not self.is_connected():
            raise RuntimeError("Not connected to a server!")

        await self.proto.send_message(message)

    async def send_command(self, command, **kwargs):
        """Convenience for sending commands"""
        await self.send_message({"command": command, **kwargs})

    async def read_until(self, predicate, timeout=5):
        return await asyncio.wait_for(
            read_until(self.proto, predicate),
            timeout=timeout
        )

    async def read_until_command(self, command, timeout=5):
        return await read_until_command(self.proto, command, timeout=timeout)

    async def read_until_game_launch(self, uid):
        return await self.read_until(
            lambda msg: (
                msg.get("command") == "game_info" and
                msg["launched_at"] is not None
                and msg["uid"] == uid
            )
        )

    # Commonly used functionality here
    async def ping(self):
        await self.send_command("ping")

    async def pong(self):
        await self.send_command("pong")

    async def login(self, username, password):
        """Perform the entire login sequence including fetching a session
        and calling `faf-uid`"""
        await self.proto.send_message({
            "command": "ask_session",
            "user_agent": self.user_agent,
            "version": self.version
        })
        msg = await self.read_until_command("session")
        session = msg["session"]
        unique_id = self.get_unique_id(session)

        pw_hash = sha256(password.encode("utf-8"))
        await self.proto.send_message({
            "command": "hello",
            "version": self.version,
            "user_agent": self.user_agent,
            "login": username,
            "password": pw_hash.hexdigest(),
            "unique_id": unique_id
        })
        msg = await self.read_until_command("welcome")
        self.player_id = msg["id"]
        self.player_name = msg["login"]
        return msg

    def get_unique_id(self, session):
        try:
            process = subprocess.run(
                [self.faf_uid_path, str(session)],
                stdout=subprocess.PIPE
            )
            return process.stdout.decode()
        except OSError:
            return "some_fake_uid"

    async def host_game(self, **kwargs):
        await self.send_message({
            "command": "game_host",
            "mod": "faf",
            "visibility": "public",
            **kwargs
        })
        msg = await self.read_until_command("game_launch")
        game_id = int(msg["uid"])

        await self.open_fa()
        return game_id

    async def join_game(self, game_id, **kwargs):
        await self.send_message({
            "command": "game_join",
            "uid": game_id
        })
        await self.read_until_command("game_launch")

        await self.open_fa()

        # HACK: Yield long enough for the server to process our message
        await asyncio.sleep(0.5)

    async def join_queue(self, queue_name, faction="uef"):
        await self.send_message({
            "command": "game_matchmaking",
            "state": "start",
            "queue_name": queue_name,
            "faction": faction
        })
        await self.read_until(lambda msg: msg == {
            "command": "search_info",
            "state": "start",
            "queue_name": queue_name
        })

    async def open_fa(self):
        """Simulate FA opening"""
        await self.send_message({
            "target": "game",
            "command": "GameState",
            "args": ["Idle"]
        })
        await self.send_message({
            "target": "game",
            "command": "GameState",
            "args": ["Lobby"]
        })

    async def configure_joining_player(self, player_id, army):
        await self.send_player_options(
            player_id,
            Army=army,
            Color=army,
            Faction=1,
            StartSpot=army,
            Team=1,
        )

    async def send_player_options(self, player_id, **options):
        for option, value in options.items():
            await self.send_message({
                "target": "game",
                "command": "PlayerOption",
                "args": [player_id, option, value]
            })

    async def get_player_ratings(
        self,
        *names,
        rating_type="global",
        timeout=30
    ):
        """
        Wait for `player_info` messages until all player names have been found.
        Then return a dictionary containing all those players ratings
        """
        ratings = {}
        while set(ratings.keys()) != set(names):
            msg = await self.read_until_command("player_info", timeout=timeout)
            ratings.update({
                player_info["login"]: player_info["ratings"][rating_type]["rating"]
                for player_info in msg["players"]
            })
        return ratings

    async def send_gpg_command(self, command, *args):
        await self.send_message({
            "target": "game",
            "command": command,
            "args": args
        })
