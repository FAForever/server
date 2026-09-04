# Meta tests for test utilities

from contextlib import asynccontextmanager, contextmanager

import pytest

from tests.utils import autocontext


@pytest.fixture
def context_fixture():
    @contextmanager
    def make_thing():
        yield "foo"

    return make_thing


@pytest.fixture
async def async_context_fixture():
    @asynccontextmanager
    async def make_thing():
        yield "bar"

    return make_thing


@pytest.fixture
def normal_fixture():
    return 100


@autocontext("context_fixture")
def test_autocontext_sync(thing):
    assert thing == "foo"


@autocontext("context_fixture")
def test_autocontext_sync_with_normal(thing, normal_fixture):
    assert thing == "foo"
    assert normal_fixture == 100


@autocontext("async_context_fixture")
async def test_autocontext_async(thing):
    assert thing == "bar"


@autocontext("async_context_fixture")
async def test_autocontext_async_with_normal(thing, normal_fixture):
    assert thing == "bar"
    assert normal_fixture == 100


@autocontext("context_fixture", "async_context_fixture")
async def test_autocontext_both(thing1, thing2):
    assert thing1 == "foo"
    assert thing2 == "bar"


@autocontext("context_fixture", "async_context_fixture")
async def test_autocontext_all(thing1, thing2, normal_fixture):
    assert thing1 == "foo"
    assert thing2 == "bar"
    assert normal_fixture == 100
