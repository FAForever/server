from typing import Any

from .protocol import Protocol
from .router import RouteError, Router
from .typedefs import Address, Handler, Message


class handler():
    """
    Decorator for adding a handler to a connection
    """
    def __init__(self, key: Any = Router.missing, **filters: Any):
        self.func = None
        self.key = key
        self.filters = filters

    def __call__(self, func: Handler) -> Handler:
        self.func = func
        return self


class ConnectionMeta(type):
    def __new__(cls, name, bases, namespace):
        if "router" not in namespace:
            namespace["router"] = Router("command")

        router = namespace["router"]
        for attrname, value in list(namespace.items()):
            if isinstance(value, handler) and value.func:
                router.register_func(
                    attrname,
                    value.key,
                    **value.filters
                )
                # Unwrap the handler function
                namespace[attrname] = value.func
        return super().__new__(cls, name, bases, namespace)


class Connection(metaclass=ConnectionMeta):
    """
    An object responsible for handling the lifecycle of a connection. Message
    handlers can be added with the `handler` decorator.

    # Example
    ```
    class FooConnection(Connection):
        @handler("bar")
        async def handle_bar(self, message):
            print(message)

    conn = FooConnection(protocol, address)
    await conn.on_message_received({"command": "bar"})
    await conn.handle_bar({"command": "bar"})
    # Both calls print "{'command': 'bar'}"
    ```
    """
    def __init__(self, protocol: Protocol, address: Address):
        self.protocol = protocol
        self.address = address

    def dispatch(self, message: Message) -> Handler:
        """
        Get the function registered to handle a message.

        :raises: RouteError if no handler was found
        """
        try:
            handler_name = self.router.dispatch(message)
        except RouteError:
            # We use type(self) because we want to properly follow the MRO
            handler_name = super(type(self), self).router.dispatch(message)

        return getattr(self, handler_name)

    async def on_message_received(self, message: Message):
        """
        Forward the message to the registered handler function.

        :raises: RouteError if no handler was found
        """
        handler_func = self.dispatch(message)
        return await handler_func(message)

    async def send(self, message):
        """Send a message and wait for it to be sent."""
        self.write(message)
        await self.protocol.drain()

    def write(self, message):
        """Write a message into the send buffer."""
        self.protocol.write_message(message)

    async def on_connection_lost(self):
        pass
