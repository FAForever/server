from abc import ABCMeta, abstractmethod


class Receiver:
    __metaclass__ = ABCMeta

    @abstractmethod
    def on_message_received(self, message: dict) -> None: ...


class Dispatcher:
    __metaclass__ = ABCMeta

    @abstractmethod
    def send(self, msg: dict) -> None: ...

    @abstractmethod
    def subscribe_to(self, command_id: str, receiver: Receiver) -> None: ...
