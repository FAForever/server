from .with_logger import with_logger


@with_logger
class Subscribable():
    """
    Mixin for handling subscriptions to messages.

    The standard format of messages is as follows:
    >>> {
    >>>     "command_id": "some_command",
    >>>     "arguments": []
    >>> }

    Subscribable.notify dispatches messages to the subscriber, they are dispatched
    to the handle_{command_id} method on the subscriber, if it is there.
    """
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._subscriptions = {'_all': []}

    def subscribe(self, receiver, command_ids=None, filter=None):
        """
        Subscribe to messages from this GameConnection
        :param receiver: object to receive messages
        :param command_ids: Optional list of command_ids to subscribe to
        :param filter:
            Optional function to invoke with arguments to
            determine whether or not to forward message.
        :return: None
        """
        if not command_ids:
            command_ids = ['_all']
        if not filter:
            filter = lambda args: True
        for i in command_ids:
            if i in self._subscriptions:
                self._subscriptions[i].append((receiver, filter))
            else:
                self._subscriptions[i] = [(receiver, filter)]

    def notify(self, message):
        """
        Notify subscribers that a message of interest arrived
        :param message:
        :return:
        """
        command_id = message.get("command_id")
        arguments = message.get("arguments", [])
        assert isinstance(command_id, str)
        cmd_name = 'handle_{cmd_id}'.format(cmd_id=command_id)
        if command_id in self._subscriptions:
            for sub, fn in self._subscriptions[command_id]:
                if fn(arguments) and hasattr(sub, cmd_name):
                    getattr(sub, cmd_name)(arguments)
                else:
                    self._logger.debug("Subscriber {sub} does not have {cmd_name}".format(
                        sub=sub,
                        cmd_name=cmd_name
                    ))
        for sub, fn in self._subscriptions['_all']:
            if fn(arguments) and hasattr(sub, cmd_name):
                getattr(sub, cmd_name)(arguments)

    def unsubscribe(self, receiver, command_ids=None):
        """
        Unusubscribe a given function from given message ids.

        Be careful to unsubscribe from exactly the messages that the receiver
        has subscribed to.
        :param receiver: function to unsubscribe
        :param command_ids: Command identifiers to unsubscribe from
        :return: None
        """
        self._logger.debug("Unsubscribing {receiver} from {commands} on {self}".format(
            receiver=receiver,
            commands=command_ids,
            self=self
        ))
        if not command_ids:
            command_ids = ['_all']
        for i in command_ids:
            if i in self._subscriptions:
                self._subscriptions[i] = [(recv, fn)
                                          for (recv, fn) in self._subscriptions[i]
                                          if recv != receiver]
