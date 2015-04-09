import asyncio

import mock
import pytest

from server.subscribable import Subscribable


@pytest.fixture
def subscribable():
    return Subscribable()

@pytest.fixture
def receiver():
    return mock.Mock()

def test_subscribe_all(receiver, subscribable):
    subscribable.subscribe(receiver)
    subscribable.notify({'command_id': 'Some_Command', 'arguments': [1, 'Param']})
    subscribable.notify({'command_id': 'SomeOtherCommand', 'arguments': [2, 'Params']})
    receiver.handle_Some_Command.assert_called_with([1, 'Param'])
    receiver.handle_SomeOtherCommand.assert_called_with([2, 'Params'])

def test_subscribe_specific(receiver, subscribable):
    subscribable.subscribe(receiver, ['SomeOtherCommand'])
    subscribable.notify({'command_id': 'Some_Command', 'arguments': [1, 'Param']})
    subscribable.notify({'command_id': 'SomeOtherCommand', 'arguments': [2, 'Params']})
    assert receiver.handle_Some_Command.mock_calls == []
    receiver.handle_SomeOtherCommand.assert_called_with([2, 'Params'])

def test_subscribe_func(receiver, subscribable):
    subscribable.subscribe(receiver, ['SomeCommand'], filter=lambda args: 'x' in args)
    subscribable.notify({'command_id': 'SomeCommand', 'arguments': [1]})
    assert receiver.handle_SomeCommand.mock_calls == []
    subscribable.notify({'command_id': 'SomeCommand', 'arguments': ['x']})
    assert receiver.handle_SomeCommand.mock_calls == [mock.call(['x'])]

def test_unsubscribe(receiver, subscribable):
    subscribable.subscribe(receiver)
    subscribable.unsubscribe(receiver)
    subscribable.notify({'command_id': 'Some_Command', 'arguments': [1, 'Param']})
    assert receiver.handle_Some_Command.mock_calls == []

def test_context_manager(receiver, subscribable):
    with subscribable.subscribe(receiver, ['SomeCommand']):
        subscribable.notify({'command_id': 'SomeCommand', 'arguments': []})
        receiver.handle_SomeCommand.assert_called_with([])
    subscribable.notify({'command_id': 'SomeOtherCommand', 'arguments': []})
    assert receiver.handle_SomeOtherCommand.mock_calls == []

def test_context_manager_await(loop, receiver, subscribable):
    @asyncio.coroutine
    def send_delayed(subscribable):
        yield from asyncio.sleep(0.001)
        subscribable.notify({'command_id': 'SomeDelayedCommand',
                             'arguments': []})

    @asyncio.coroutine
    def test():
        with subscribable.subscribe(receiver, ['SomeDelayedCommand']) as sub:
            asyncio.async(send_delayed(subscribable))
            yield from sub.wait_for('SomeDelayedCommand')
            receiver.handle_SomeDelayedCommand.assert_called_with([])
    loop.run_until_complete(asyncio.wait_for(test(), 2))
