from textwrap import dedent

import mock
import pytest

from server.core.routing import RouteError, Router, SearchTree


@pytest.fixture
def router():
    return Router("command")


def test_router_basic(router):
    async def handle_foo(*args):
        pass

    router.register_func(handle_foo, "foo")

    @router.register("bar")
    def handle_bar(a):
        pass

    @router.register("baz")
    async def handle_baz(b, c):
        pass

    assert router.dispatch({"command": "foo"}) is handle_foo
    assert router.dispatch({"command": "bar"}) is handle_bar
    assert router.dispatch({"command": "baz"}) is handle_baz

    with pytest.raises(RouteError):
        router.dispatch({"command": "qux"})


def test_router_filters(router):
    @router.register("foo")
    async def handle_foo():
        pass

    @router.register("foo", bar="hello")
    async def handle_foo_hello():
        pass

    @router.register(bar="hello")
    async def handle_bar():
        pass

    assert router.dispatch({"command": "foo"}) is handle_foo
    assert router.dispatch({"command": "foo", "bar": "hello"}) is handle_foo_hello
    assert router.dispatch({"bar": "hello"}) is handle_bar


def test_router_error():
    router = Router()

    with pytest.raises(RuntimeError):
        router.register_func(mock.Mock(), "foo")


def test_filters(router):
    @router.register("foo", filter="hello")
    def handle_hello():
        pass

    @router.register("foo", filter=10)
    def handle_ten():
        pass

    @router.register("foo")
    def handle_foo():
        pass

    assert router.dispatch({"command": "foo", "filter": "hello"}) is handle_hello
    assert router.dispatch({"command": "foo", "filter": 10}) is handle_ten
    assert router.dispatch({"command": "foo", "filter": "world"}) is handle_foo


def test_search_tree():
    tree = SearchTree()

    target_game_mock = mock.Mock()
    command_foo_mock = mock.Mock()
    foo_hello_mock = mock.Mock()
    foo_ten_mock = mock.Mock()
    command_bar_mock = mock.Mock()

    tree.insert(target_game_mock, {"target": "game"})
    tree.insert(command_foo_mock, {"command": "foo"})
    tree.insert(foo_hello_mock, {"command": "foo", "filter": "hello"})
    tree.insert(foo_ten_mock, {"command": "foo", "filter": 10})
    tree.insert(command_bar_mock, {"command": "bar"})

    assert tree[{"target": "game"}] is target_game_mock
    assert tree[{"target": "game", "command": "foo"}] is target_game_mock
    assert tree[{"command": "foo"}] is command_foo_mock
    assert tree[{"command": "foo", "filter": "hello"}] is foo_hello_mock
    assert tree[{"command": "foo", "filter": 10}] is foo_ten_mock
    assert tree[{"command": "foo", "filter": "world"}] is command_foo_mock
    assert tree[{"command": "bar"}] is command_bar_mock
    assert tree.get({}) is None
    assert tree.get({"unknown": "message"}) is None

    with pytest.raises(KeyError):
        tree[{}]

    with pytest.raises(KeyError):
        tree[{"unknown": "message"}]


def test_search_tree_repr():
    tree = SearchTree()

    tree.insert("game_handler", {"target": "game"})
    tree.insert("foo_handler", {"command": "foo"})
    tree.insert("foo_hello_handler", {"command": "foo", "filter": "hello"})
    tree.insert("bar_handler", {"command": "bar"})

    assert repr(tree) == dedent("""
    handler: None
    nodes:
        key: target
        values:
        value: game
            handler: game_handler
            nodes:

        key: command
        values:
        value: foo
            handler: foo_handler
            nodes:
                key: filter
                values:
                value: hello
                    handler: foo_hello_handler
                    nodes:

        value: bar
            handler: bar_handler
            nodes:
    """.strip("\n"))
