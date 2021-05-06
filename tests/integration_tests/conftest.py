import asyncio
import hashlib
import json
import logging
import textwrap
from collections import defaultdict
from typing import Any, Callable, Dict, Tuple
from unittest import mock

import aio_pika
import asynctest
import pytest
from aiohttp import web
from asynctest import exhaust_callbacks

from server import (
    BroadcastService,
    GameService,
    LadderService,
    PartyService,
    ServerInstance
)
from server.config import config
from server.control import ControlServer
from server.db.models import login
from server.protocol import Protocol
from server.servercontext import ServerContext


@pytest.fixture
def mock_games():
    return asynctest.create_autospec(GameService)


@pytest.fixture
async def ladder_service(mocker, database, game_service):
    mocker.patch("server.matchmaker.pop_timer.config.QUEUE_POP_TIME_MAX", 1)
    ladder_service = LadderService(database, game_service)
    await ladder_service.initialize()
    yield ladder_service
    await ladder_service.shutdown()


@pytest.fixture
async def party_service(game_service):
    service = PartyService(game_service)
    await service.initialize()

    yield service

    await service.shutdown()


@pytest.fixture
async def broadcast_service(
    message_queue_service,
    game_service,
    player_service,
):
    # The reference to the ServerInstance needs to be established later
    service = BroadcastService(
        None,
        message_queue_service,
        game_service,
        player_service,
    )
    await service.initialize()

    yield service

    await service.shutdown()


@pytest.fixture
def jwk_priv_key():
    return textwrap.dedent("""
    -----BEGIN RSA PRIVATE KEY-----
    MIIBOgIBAAJBAKia//Uh/0nwtCI2QEaorc4voP5Xx+68M/AHLsvzxe7qLut64+O3
    vHlYp9B9wClxxp3unphCZDe+JIzRieCz14UCAwEAAQJAWh5G0uox/n5meabPojTE
    eWFhxrB6j7MOe6wLKj4IvJKWxoxLuMoOWmqWcWLiFw4pXKFtjv6bOGW8uUyDZDQt
    vQIhANt1HM3WPoFsvdnnqLH6PILfDRzal5Kjv1Ua97b7q2qLAiEAxK4zrououc6a
    I+uVxvsTnU88DeydN2sTroc36YfC2C8CIQCuZg4i4ZxAnBrvfPKJpXPLCNjR0kDb
    7rcROeIbjzp06wIgcZfXG5lnwqDTn6lh4QGEC5gGrFgbWTWLsYJBRax2WVsCIFeL
    KtHOf7sc9jf0k73eooPK8b+g4pssztR4GObEThZh
    -----END RSA PRIVATE KEY-----
    """)

@pytest.fixture
def jwk_header():
    return {"kid": "L7wdUtrDssMTb57A_TNAI79DQCdp0T2-KUrSUoDJBhk"}


@pytest.fixture
async def lobby_server(
    event_loop,
    database,
    broadcast_service,
    player_service,
    game_service,
    geoip_service,
    ladder_service,
    rating_service,
    message_queue_service,
    party_service,
    oauth_service,
    policy_server,
    jwks_server
):
    mock_policy = mock.patch("server.lobbyconnection.config.FAF_POLICY_SERVER_BASE_URL",
                    f"http://{policy_server.host}:{policy_server.port}")
    mock_jwk = mock.patch("server.oauth_service.config.HYDRA_JWKS_URI",
                    f"http://{jwks_server.host}:{jwks_server.port}/jwks")
    with mock_policy, mock_jwk:
        instance = ServerInstance(
            "UnitTestServer",
            database,
            api_accessor=None,
            twilio_nts=None,
            loop=event_loop,
            _override_services={
                "broadcast_service": broadcast_service,
                "geo_ip_service": geoip_service,
                "player_service": player_service,
                "game_service": game_service,
                "ladder_service": ladder_service,
                "rating_service": rating_service,
                "message_queue_service": message_queue_service,
                "party_service": party_service,
                "oauth_service": oauth_service
            })
        # Set up the back reference
        broadcast_service.server = instance

        ctx = await instance.listen(("127.0.0.1", None))
        ctx.__connected_client_protos = []
        player_service.is_uniqueid_exempt = lambda id: True

        yield ctx

        ctx.close()
        # Close connected protocol objects
        # https://github.com/FAForever/server/issues/717
        for proto in ctx.__connected_client_protos:
            proto.writer.close()
        await ctx.wait_closed()
        await exhaust_callbacks(event_loop)


@pytest.fixture
async def control_server(player_service, game_service):
    server = ControlServer(
        game_service,
        player_service,
        "127.0.0.1",
        config.CONTROL_SERVER_PORT
    )
    await server.start()

    yield server

    await server.shutdown()


@pytest.fixture
async def policy_server():
    host = "localhost"
    port = 6080

    app = web.Application()
    routes = web.RouteTableDef()

    class Handle(object):
        def __init__(self):
            self.host = host
            self.port = port
            self.result = "honest"
            self.verify = mock.Mock()

    handle = Handle()

    @routes.post("/verify")
    async def token(request):
        # Register that the endpoint was called using a Mock
        handle.verify()

        await request.json()
        return web.json_response({"result": handle.result})

    app.add_routes(routes)

    runner = web.AppRunner(app)

    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()

    yield handle

    await runner.cleanup()


@pytest.fixture
async def jwks_server():
    host = "localhost"
    port = 4080

    app = web.Application()
    routes = web.RouteTableDef()

    class Handle(object):
        def __init__(self):
            self.host = host
            self.port = port
            self.result = {
                "keys": [{
                    "kty": "RSA",
                    "e": "AQAB",
                    "use": "sig",
                    "kid": "L7wdUtrDssMTb57A_TNAI79DQCdp0T2-KUrSUoDJBhk",
                    "alg": "RS256",
                    "n": "qJr_9SH_SfC0IjZARqitzi-g_lfH7rwz8Acuy_PF7uou63rj47e8eVin0H3AKXHGne6emEJkN74kjNGJ4LPXhQ"
                }]
            }
            self.verify = mock.Mock()

    handle = Handle()

    @routes.get("/jwks")
    async def get(request):
        # Register that the endpoint was called using a Mock
        handle.verify()

        return web.json_response(handle.result)

    app.add_routes(routes)

    runner = web.AppRunner(app)

    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()

    yield handle

    await runner.cleanup()


@pytest.fixture
async def tmp_user(database):
    user_ids = defaultdict(lambda: 1)
    password_plain = "foo"
    password = hashlib.sha256(password_plain.encode()).hexdigest()

    async def make_user(name="TempUser"):
        user_id = user_ids[name]
        login_name = f"{name}{user_id}"
        async with database.acquire() as conn:
            await conn.execute(login.insert().values(
                login=login_name,
                email=f"{login_name}@example.com",
                password=password,
            ))
        user_ids[name] += 1
        return login_name, password_plain

    return make_user


async def connect_client(server: ServerContext) -> Protocol:
    proto = server.protocol_class(
        *(await asyncio.open_connection(*server.sockets[0].getsockname()))
    )
    if hasattr(server, "__connected_client_protos"):
        server.__connected_client_protos.append(proto)
    return proto


async def perform_login(
    proto: Protocol, credentials: Tuple[str, str]
) -> None:
    login, pw = credentials
    pw_hash = hashlib.sha256(pw.encode("utf-8"))
    await proto.send_message({
        "command": "hello",
        "version": "1.0.0-dev",
        "user_agent": "faf-client",
        "login": login,
        "password": pw_hash.hexdigest(),
        "unique_id": "some_id"
    })


async def _read_until(
    proto: Protocol,
    pred: Callable[[Dict[str, Any]], bool]
) -> Dict[str, Any]:
    while True:
        msg = await proto.read_message()
        try:
            if pred(msg):
                return msg
        except KeyError:
            pass
        except Exception:
            logging.getLogger().warning(
                "read_until predicate raised during message: %s",
                msg,
                exc_info=True
            )


async def read_until(
    proto: Protocol,
    pred: Callable[[Dict[str, Any]], bool],
    timeout: float = 60
) -> Dict[str, Any]:
    return await asyncio.wait_for(_read_until(proto, pred), timeout=timeout)


async def read_until_command(
    proto: Protocol,
    command: str,
    timeout: float = 60,
    **kwargs
) -> Dict[str, Any]:
    kwargs["command"] = command
    return await asyncio.wait_for(
        _read_until(
            proto,
            lambda msg: all(msg[k] == v for k, v in kwargs.items())
        ),
        timeout=timeout
    )


async def get_session(proto):
    await proto.send_message({
        "command": "ask_session",
        "user_agent": "faf-client",
        "version": "0.11.16"
    })
    msg = await read_until_command(proto, "session")

    return msg["session"]


async def connect_and_sign_in(
    credentials,
    lobby_server: ServerContext,
):
    proto = await connect_client(lobby_server)
    session = await get_session(proto)
    await perform_login(proto, credentials)
    hello = await read_until_command(proto, "welcome", timeout=120)
    player_id = hello["id"]
    return player_id, session, proto


@pytest.fixture
async def channel():
    connection = await aio_pika.connect(
        "amqp://{user}:{password}@localhost/{vhost}".format(
            user=config.MQ_USER,
            password=config.MQ_PASSWORD,
            vhost=config.MQ_VHOST
        )
    )
    channel = await connection.channel()

    yield channel

    await connection.close()


async def connect_mq_consumer(server, channel, routing_key):
    """
    Returns a subclass of Protocol that yields messages read from a rabbitmq
    exchange.
    """
    exchange = await channel.declare_exchange(
        config.MQ_EXCHANGE_NAME,
        aio_pika.ExchangeType.TOPIC
    )
    queue = await channel.declare_queue("", exclusive=True)
    await queue.bind(exchange, routing_key=routing_key)
    proto = AioQueueProtocol(queue)
    await proto.consume()

    return proto


class AioQueueProtocol(Protocol):
    """
    A wrapper around an asyncio `Queue` that exposes the `Protocol` interface.
    """

    def __init__(self, queue):
        self.queue = queue
        self.consumer_tag = None
        self.aio_queue = asyncio.Queue()

    async def consume(self):
        self.consumer_tag = await self.queue.consume(
            lambda msg: self.aio_queue.put_nowait(
                json.loads(msg.body.decode())
            )
        )

    @staticmethod
    def encode_message(message: dict) -> bytes:
        raise NotImplementedError("AioQueueProtocol is read-only")

    async def read_message(self) -> dict:
        return await self.aio_queue.get()

    async def send_message(self, message):
        raise NotImplementedError("AioQueueProtocol is read-only")

    async def close(self):
        await self.queue.cancel(self.consumer_tag)
