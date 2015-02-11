import functools
import mock
from src.subscribable import Subscribable

def test_subscribe_all():
    subscriber = mock.Mock()
    subscribable = Subscribable()
    subscribable.subscribe(subscriber)
    subscribable.notify({'command_id': 'Some_Command', 'arguments': [1, 'Param']})
    subscribable.notify({'command_id': 'SomeOtherCommand', 'arguments': [2, 'Params']})
    subscriber.handle_Some_Command.assert_called_with([1, 'Param'])
    subscriber.handle_SomeOtherCommand.assert_called_with([2, 'Params'])

def test_subscribe_specific():
    subscriber = mock.Mock()
    subscribable = Subscribable()

    subscribable.subscribe(subscriber, ['SomeOtherCommand'])
    subscribable.notify({'command_id': 'Some_Command', 'arguments': [1, 'Param']})
    subscribable.notify({'command_id': 'SomeOtherCommand', 'arguments': [2, 'Params']})
    assert subscriber.handle_Some_Command.mock_calls == []
    subscriber.handle_SomeOtherCommand.assert_called_with([2, 'Params'])

def test_subscribe_func():
    sub = mock.Mock()
    subscribable = Subscribable()

    subscribable.subscribe(sub, ['SomeCommand'], filter=lambda args: 'x' in args)
    subscribable.notify({'command_id': 'SomeCommand', 'arguments': [1]})
    assert sub.handle_SomeCommand.mock_calls == []
    subscribable.notify({'command_id': 'SomeCommand', 'arguments': ['x']})
    assert sub.handle_SomeCommand.mock_calls == [mock.call(['x'])]

def test_unsubscribe():
    subscriber = mock.Mock()
    subscribable = Subscribable()

    subscribable.subscribe(subscriber)
    subscribable.unsubscribe(subscriber)
    subscribable.notify({'command_id': 'Some_Command', 'arguments': [1, 'Param']})
    assert subscriber.handle_Some_Command.mock_calls == []

