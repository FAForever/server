from abc import ABCMeta, abstractmethod
from typing import List


class Protocol(metaclass=ABCMeta):
    @abstractmethod
    async def read_message(self: 'Protocol') -> dict:
        """
        Asynchronously read a message from the stream

        :raises: IncompleteReadError
        :return dict: Parsed message
        """
        pass  # pragma: no cover

    @abstractmethod
    def send_message(self, message: dict) -> None:
        """
        Send a single message in the form of a dictionary

        :param message: Message to send
        """
        pass  # pragma: no cover

    @abstractmethod
    def send_messages(self, messages: List[dict]) -> None:
        """
        Send multiple messages in the form of a list of dictionaries.

        May be more optimal than sending a single message.

        :param messages:
        """
        pass  # pragma: no cover

    @abstractmethod
    def send_raw(self, data: bytes) -> None:
        """
        Send raw bytes. Should generally not be used.

        :param data: bytes to send
        """
        pass  # pragma: no cover

    @abstractmethod
    async def drain(self) -> None:
        """
        Await the write buffer to empty
        """
        pass  # pragma: no cover

    @abstractmethod
    def close(self) -> None:
        """
        Close the stream
        """
        pass  # pragma: no cover
