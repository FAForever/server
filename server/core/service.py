class Service(object):
    """
    All services should inherit from this class.

    Services are singleton objects which manage some server task.
    """

    async def initialize(self) -> None:
        """
        Called once while the server is starting.
        """
        pass  # pragma: no cover

    async def shutdown(self) -> None:
        """
        Called once after the server received the shutdown signal.
        """
        pass  # pragma: no cover
