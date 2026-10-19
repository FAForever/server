from __future__ import annotations

import asyncio
import contextlib
import datetime
import hashlib
import json
import logging
import textwrap
from collections import defaultdict
from collections.abc import AsyncGenerator
from typing import Any, Callable, Optional
from unittest import mock

import aio_pika
import pytest
from aio_pika.abc import (
    AbstractChannel,
    AbstractIncomingMessage,
    AbstractQueue
)
from aiohttp import web
from sqlalchemy import select

import server.metrics as metrics
from server import (
    BroadcastService,
    GameService,
    LadderService,
    OAuthService,
    PartyService,
    ServerInstance,
    VetoService,
    ViolationService
)
from server.config import config
from server.control import ControlServer
from server.db.models import login
from server.health import HealthServer
from server.message_queue_service import MessageQueueService
from server.protocol import DisconnectedError, Protocol, RabbitMQProtocol
from server.protocol.protocol import json_encoder
from server.servercontext import ServerContext
from tests.utils import exhaust_callbacks


@pytest.fixture
def mock_games():
    return mock.create_autospec(GameService)


@pytest.fixture
async def ladder_service(
        mocker,
        database,
        game_service,
        violation_service,
        veto_service,
):
    mocker.patch("server.matchmaker.pop_timer.config.QUEUE_POP_TIME_MAX", 1)
    ladder_service = LadderService(
        database,
        game_service,
        violation_service,
        veto_service,
    )
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
async def veto_service(player_service):
    service = VetoService(player_service)
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
        veto_service,
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
                "veto_service": veto_service,
            })
        # Set up the back reference
        broadcast_service.server = instance

        # FIXME?: unlike ServerInstance, overriden services have no internal
        # state to reflect that they are running.
        # instance.listen(...) tries to start them if instance is not started yet
        #
        # overriden servivces were started in their corresponding fixtures
        # therefore we manually set instance's flag here so it doesn't
        # trye to start them again
        instance.started = True

        contexts = {
            name: await instance.listen()
            for name, cfg in config.items()
        }

        # This is a dirty workaround to pass the database to the connect_and_sign_in function for tests
        # Ideally that function should be a proper fixture
        for context in contexts.values():
            context.database = database

        all_contexts.extend(contexts.values())
        player_service.is_uniqueid_exempt = lambda id: True

        return instance, contexts

    mock_policy = mock.patch(
        "server.lobbyconnection.config.FAF_POLICY_SERVER_BASE_URL",
        f"http://{policy_server.host}:{policy_server.port}"
    )
    with mock_policy:
        yield make_lobby_server

    for context in all_contexts:
        await context.shutdown()
    await exhaust_callbacks()


@pytest.fixture
async def lobby_setup(lobby_server_factory):
    return await lobby_server_factory({
        "mq": {},
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
@pytest.fixture
def lobby_server(lobby_contexts) -> ServerContext:
    yield lobby_contexts["mq"]


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
    raise RuntimeError("Not implemented")


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


_SENTINEL = object()
_session_counter = 0

class ClientRabbitMQProtocol(Protocol):
    """
    Client-side protocol implementation over RabbitMQ for integration tests.
    Sends client messages wrapped with session over INBOUND_EXCHANGE_NAME.
    Receives server messages from OUTBOUND_EXCHANGE_NAME and unwraps them.
    """

    def __init__(
            self,
            queue: asyncio.Queue,
            server_context: ServerContext,
            session: int,
            player_id: Optional[int] = None,
            consumer_tag: Optional[str] = None,
            consumer_queue: Optional[AbstractQueue] = None,
    ):
        self.queue = queue
        self.server_context = server_context
        self.session = session
        self.player_id = player_id
        self.consumer_tag = consumer_tag
        self.consumer_queue = consumer_queue
        self._pending: set[asyncio.Task] = set()
        self._closed = False

    @staticmethod
    def encode_message(message: dict) -> bytes:
        return json_encoder.encode(message).encode()

    @staticmethod
    def decode_message(data: bytes) -> dict:
        return json.loads(data)

    def is_connected(self) -> bool:
        return not self._closed

    async def read_message(self) -> dict:
        if not self.is_connected():
            raise DisconnectedError("RabbitMQ protocol is not connected!")

        item = await self.queue.get()
        if item is _SENTINEL or not self.is_connected():
            raise DisconnectedError("RabbitMQ connection closed")

        return item

    def write_message(self, message: dict) -> None:
        metrics.sent_messages.labels(self.__class__.__name__).inc()
        if not self.is_connected():
            raise DisconnectedError("Protocol is not connected!")
        if self.server_context is None:
            raise DisconnectedError("No message queue service configured for publishing!")

        task = asyncio.create_task(
            self.server_context.publish(
                exchange_name=config.INBOUND_EXCHANGE_NAME,
                routing="lobby.legacy.client",
                payload=self._wrap_message_with_session(message),
            )
        )
        self._pending.add(task)
        task.add_done_callback(self._pending.discard)

    def write_messages(self, messages: list[dict]) -> None:
        metrics.sent_messages.labels(self.__class__.__name__).inc()
        if not self.is_connected():
            raise DisconnectedError("Protocol is not connected!")
        if self.server_context is None:
            raise DisconnectedError("No message queue service configured for publishing!")

        task = asyncio.create_task(
            self.server_context.publish_many(
                exchange_name=config.INBOUND_EXCHANGE_NAME,
                routing="lobby.legacy.client",
                payloads=[self._wrap_message_with_session(message) for message in messages],
            )
        )
        self._pending.add(task)
        task.add_done_callback(self._pending.discard)

    def write_raw(self, data: bytes) -> None:
        payload = self.decode_message(data)
        self.write_message(payload)

    def _wrap_message_with_session(self, payload: dict) -> dict:
        return {"player_id": self.player_id, "session_id": self.session, "ip_address": "127.0.0.1", "message": payload}

    async def drain(self) -> None:
        if not self._pending:
            return
        try:
            await asyncio.gather(*self._pending)
        except Exception as e:
            await self.close()
            raise DisconnectedError("Protocol connection lost!") from e

    def abort(self) -> None:
        self._closed = True
        for task in self._pending:
            task.cancel()
        if self.queue is not None:
            self.queue.put_nowait(_SENTINEL)

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        for task in self._pending:
            task.cancel()
        if self.server_context is not None and self.player_id is not None:
            with contextlib.suppress(Exception):
                await self.server_context.publish(
                    exchange_name=config.SESSION_EXCHANGE_NAME,
                    routing="",
                    payload={
                        "player_id": self.player_id,
                        "session_id": self.session,
                        "state": {"@type": "gone"},
                    },
                )
        if self.consumer_queue is not None and self.consumer_tag is not None:
            with contextlib.suppress(Exception):
                await self.consumer_queue.cancel(self.consumer_tag)
        if self.queue is not None:
            self.queue.put_nowait(_SENTINEL)


async def _connect_and_sign_in(
        credentials,
        database,
        server_context,
) -> tuple[int, int, Protocol]:
    global _session_counter
    _session_counter += 1
    session_id = _session_counter

    # Resolve player_id
    player_id = None
    username, _ = credentials
    if database is not None:
        async with database.acquire() as conn:
            result = await conn.execute(
                select(login.c.id).where(login.c.login == username)
            )
            row = result.fetchone()
            if row is not None:
                player_id = row.id

    if player_id is None:
        raise ValueError("Player not found")

    queue = asyncio.Queue()
    proto = ClientRabbitMQProtocol(
        queue=queue,
        server_context=server_context,
        session=session_id,
        player_id=player_id,
    )

    async def _on_outbound_message(msg: AbstractIncomingMessage) -> None:
        async with msg.process(requeue=False):
            try:
                payload = json.loads(msg.body)
            except Exception:
                return
            if not isinstance(payload, dict):
                return
            target = payload["target"]
            target_session = target["session_id"]

            if target_session == session_id:
                await queue.put(payload.get("message"))

    res = await server_context.declare_queue_and_consume(
        exchange_name=config.OUTBOUND_EXCHANGE_NAME,
        routing_keys=["#"],
        callback=_on_outbound_message,
        exclusive=True,
        auto_delete=True,
    )
    if res is not None:
        proto.consumer_queue, proto.consumer_tag = res

    await server_context.publish(
        exchange_name=config.SESSION_EXCHANGE_NAME,
        routing="",
        payload={
            "player_id": player_id,
            "session_id": session_id,
            "state": {"@type": "new"},
            "ip_address": "127.0.0.1",
        },
    )

    hello = await read_until_command(proto, "welcome", timeout=120)
    actual_player_id = hello.get("id", player_id)
    return actual_player_id, session_id, proto


async def connect_and_sign_in(credentials, lobby_server) -> tuple[int, int, Protocol]:
    return await _connect_and_sign_in(
        credentials,
        database=lobby_server.database,
        server_context=lobby_server,
    )


@pytest.fixture
async def channel() -> AsyncGenerator[AbstractChannel]:
    connection = await aio_pika.connect(
        f"amqp://{config.MQ_USER}:{config.MQ_PASSWORD}@localhost/{config.MQ_VHOST}"
    )
    async with connection, connection.channel() as channel:
        yield channel


async def connect_mq_consumer(
        server: ServerContext,
        channel: AbstractChannel,
        routing_key: str | None,
) -> AioQueueProtocol:
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

    def __init__(self, queue: AbstractQueue) -> None:
        self.queue = queue
        self.consumer_tag = None
        self.aio_queue = asyncio.Queue()

    async def consume(self) -> None:
        self.consumer_tag = await self.queue.consume(self._callback)

    async def _callback(self, msg: AbstractIncomingMessage) -> None:
        self.aio_queue.put_nowait(json.loads(msg.body.decode()))

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
