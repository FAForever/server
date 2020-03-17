from abc import abstractmethod


class Service(object):
    """
    All services should inherit from this class.

    Services are singleton objects which manage some server task.
    """

    @abstractmethod
    async def initialize(self) -> None:
        """
        Called once while the server is starting.
        """
        pass
