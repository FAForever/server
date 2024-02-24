import asyncio
import datetime
import hashlib
import json
import logging
import textwrap
from collections import defaultdict
from contextlib import contextmanager
from typing import Any, Callable, ContextManager, Optional
from unittest import mock

import aio_pika
import proxyprotocol.dnsbl
import proxyprotocol.server
import proxyprotocol.server.protocol
import pytest
from aiohttp import web

from server import (
    BroadcastService,
    GameService,
    LadderService,
    OAuthService,
    PartyService,
    ServerInstance,
    ViolationService
)
from server.config import config
from server.control import ControlServer
from server.db.models import login
from server.health import HealthServer
from server.protocol import Protocol, QDataStreamProtocol, SimpleJsonProtocol
from server.servercontext import ServerContext
from tests.utils import exhaust_callbacks


@pytest.fixture
def mock_games():
    return mock.create_autospec(GameService)


@pytest.fixture
async def ladder_service(mocker, database, game_service, violation_service):
    mocker.patch("server.matchmaker.pop_timer.config.QUEUE_POP_TIME_MAX", 1)
    ladder_service = LadderService(database, game_service, violation_service)
    await ladder_service.initialize()
    yield ladder_service
    await ladder_service.shutdown()


@pytest.fixture
async def violation_service():
    service = ViolationService()
    await service.initialize()
    yield service
    await service.shutdown()


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
async def oauth_service(mocker, jwks_server):
    mocker.patch(
        "server.oauth_service.config.HYDRA_JWKS_URI",
        f"http://{jwks_server.host}:{jwks_server.port}/jwks"
    )
    service = OAuthService()
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
def jwk_kid():
    return "L7wdUtrDssMTb57A_TNAI79DQCdp0T2-KUrSUoDJBhk"


@pytest.fixture
async def lobby_server_factory(
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
    violation_service,
    policy_server,
    jwks_server,
):
    all_contexts = []

    async def make_lobby_server(config):
        instance = ServerInstance(
            "UnitTestServer",
            database,
            loop=asyncio.get_running_loop(),
            _override_services={
                "broadcast_service": broadcast_service,
                "geo_ip_service": geoip_service,
                "player_service": player_service,
                "game_service": game_service,
                "ladder_service": ladder_service,
                "rating_service": rating_service,
                "message_queue_service": message_queue_service,
                "party_service": party_service,
                "oauth_service": oauth_service,
                "violation_service": violation_service,
            })
        # Set up the back reference
        broadcast_service.server = instance

        contexts = {
            name: await instance.listen(
                (cfg["ADDRESS"], cfg["PORT"]),
                protocol_class=cfg["PROTOCOL"],
                proxy=cfg.get("PROXY", False)
            )
            for name, cfg in config.items()
        }
        all_contexts.extend(contexts.values())
        for context in contexts.values():
            context.__connected_client_protos = []
        player_service.is_uniqueid_exempt = lambda id: True

        return instance, contexts

    mock_policy = mock.patch(
        "server.lobbyconnection.config.FAF_POLICY_SERVER_BASE_URL",
        f"http://{policy_server.host}:{policy_server.port}"
    )
    with mock_policy:
        yield make_lobby_server

    for context in all_contexts:
        await context.stop()
        await context.shutdown()
        # Close connected protocol objects
        # https://github.com/FAForever/server/issues/717
        for proto in context.__connected_client_protos:
            proto.abort()
    await exhaust_callbacks()


@pytest.fixture
async def lobby_setup(lobby_server_factory):
    return await lobby_server_factory({
        "qstream": {
            "ADDRESS": "127.0.0.1",
            "PORT": None,
            "PROTOCOL": QDataStreamProtocol
        },
        "json": {
            "ADDRESS": "127.0.0.1",
            "PORT": None,
            "PROTOCOL": SimpleJsonProtocol
        }
    })


@pytest.fixture
async def lobby_setup_proxy(lobby_server_factory):
    return await lobby_server_factory({
        "qstream": {
            "ADDRESS": "127.0.0.1",
            "PORT": None,
            "PROTOCOL": QDataStreamProtocol,
            "PROXY": True
        },
        "json": {
            "ADDRESS": "127.0.0.1",
            "PORT": None,
            "PROTOCOL": SimpleJsonProtocol,
            "PROXY": True
        }
    })


@pytest.fixture
def lobby_instance(lobby_setup):
    instance, _ = lobby_setup
    return instance


@pytest.fixture
def lobby_contexts(lobby_setup):
    _, contexts = lobby_setup
    return contexts


@pytest.fixture
def lobby_contexts_proxy(lobby_setup_proxy):
    _, contexts = lobby_setup_proxy
    return contexts


@pytest.fuxture
def fixed_time(monkeypatch):
    """
    Fixture to fix server.timing value. By default, fixes all timings at 1970-01-01T00:00:00+00:00. Additionally, returned function can be called unbound times to change timing value, e.g.:

    def test_time(fixed_time):
        assert server.lobbyconnection.datetime_now().timestamp == 0.
        fixed_time(1)
        assert server.lobbyconnection.datetime_now().timestamp == 1.
    """

    def fix_time(iso_utc_time: str | float | int | datetime.datetime = 0):
        """
        Fix server.timing value.

        :param iso_utc_time: UTC time to use. Can be isoformat, timestamp or native object.
        """
        if isinstance(iso_utc_time, str):
            iso_utc_time = datetime.datetime.fromisoformat(iso_utc_time)
        elif isinstance(iso_utc_time, (float, int)):
            iso_utc_time = datetime.datetime.fromtimestamp(iso_utc_time, datetime.timezone.utc)

        def mock_datetime_now() -> datetime:
            return iso_utc_time

        monkeypatch.setattr("server.lobbyconnection.datetime_now", mock_datetime_now)

    fix_time()
    return fix_time


# TODO: This fixture is poorly named since it returns a ServerContext, however,
# it is used in almost every tests, so renaming it is a large task.
@pytest.fixture(params=("qstream", "json"))
def lobby_server(request, lobby_contexts) -> ServerContext:
    yield lobby_contexts[request.param]


@pytest.fixture(params=("qstream", "json"))
def lobby_server_proxy(request, lobby_contexts_proxy):
    yield lobby_contexts_proxy[request.param]


@pytest.fixture
async def control_server(lobby_instance):
    server = ControlServer(lobby_instance)
    await server.start(
        "127.0.0.1",
        config.CONTROL_SERVER_PORT
    )

    yield server

    await server.shutdown()


@pytest.fixture
async def health_server(lobby_instance):
    server = HealthServer(lobby_instance)
    await server.start(
        "127.0.0.1",
        config.HEALTH_SERVER_PORT
    )

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
async def jwks_server(jwk_kid):
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
                    "kid": jwk_kid,
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
async def proxy_server(lobby_server_proxy):
    buf_len = 262144
    dnsbl = proxyprotocol.dnsbl.NoopDnsbl()

    host, port = lobby_server_proxy.sockets[0].getsockname()
    dest = proxyprotocol.server.Address(f"{host}:{port}")

    loop = asyncio.get_running_loop()
    server = await loop.create_server(
        lambda: proxyprotocol.server.protocol.DownstreamProtocol(
            proxyprotocol.server.protocol.UpstreamProtocol,
            loop,
            buf_len,
            dnsbl,
            dest
        ),
        "127.0.0.1",
        None,
    )
    await server.start_serving()

    yield server

    server.close()
    await server.wait_closed()


@pytest.fixture
def tmp_user(database):
    user_ids = defaultdict(lambda: 1)
    password_plain = "foo"
    password = hashlib.sha256(password_plain.encode()).hexdigest()

    async def make_user(name="TempUser"):
        user_id = user_ids[name]
        user_ids[name] += 1
        login_name = f"{name}{user_id}"
        async with database.acquire() as conn:
            await conn.execute(login.insert().values(
                login=login_name,
                email=f"{login_name}@example.com",
                password=password,
            ))
        return login_name, password_plain

    return make_user


async def connect_client(
    server: ServerContext,
    address: Optional[tuple[str, int]] = None
) -> Protocol:
    address = address or server.sockets[0].getsockname()
    proto = server.protocol_class(
        *(await asyncio.open_connection(*address))
    )
    if hasattr(server, "__connected_client_protos"):
        server.__connected_client_protos.append(proto)
    return proto


async def perform_login(
    proto: Protocol, credentials: tuple[str, str]
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
    pred: Callable[[dict[str, Any]], bool]
) -> dict[str, Any]:
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
    pred: Callable[[dict[str, Any]], bool],
    timeout: float = 60
) -> dict[str, Any]:
    return await asyncio.wait_for(_read_until(proto, pred), timeout=timeout)


async def read_until_command(
    proto: Protocol,
    command: str,
    timeout: float = 60,
    **kwargs
) -> dict[str, Any]:
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
    address: Optional[tuple[str, int]] = None
) -> tuple[int, int, Protocol]:
    proto = await connect_client(lobby_server, address)
    session = await get_session(proto)
    await perform_login(proto, credentials)
    hello = await read_until_command(proto, "welcome", timeout=120)
    player_id = hello["id"]
    return player_id, session, proto


@pytest.fixture
async def channel():
    connection = await aio_pika.connect(
        f"amqp://{config.MQ_USER}:{config.MQ_PASSWORD}@localhost/{config.MQ_VHOST}"
    )
    async with connection, connection.channel() as channel:
        yield channel


async def connect_mq_consumer(server, channel, routing_key):
    """
    Returns a subclass of Protocol that yields messages read from a rabbitmq
    exchange.
    """
    exchange = await channel.declare_exchange(
        config.MQ_EXCHANGE_NAME,
        aio_pika.ExchangeType.TOPIC,
        durable=True
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

    @staticmethod
    def decode_message(data: bytes) -> dict:
        raise NotImplementedError("AioQueueProtocol doesn't user bytes")

    async def read_message(self) -> dict:
        return await self.aio_queue.get()

    async def send_message(self, message):
        raise NotImplementedError("AioQueueProtocol is read-only")

    async def close(self):
        await self.queue.cancel(self.consumer_tag)
