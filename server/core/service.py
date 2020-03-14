from abc import abstractmethod


class Service(object):
    @abstractmethod
    async def initialize(self) -> None:
        """
        Called once before the service is used to run initial asynchronus tasks
        such as loading data from the database.
        """
        pass
