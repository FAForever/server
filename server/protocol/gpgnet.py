from abc import ABCMeta, abstractmethod
from typing import List, Union


class GpgNetServerProtocol(metaclass=ABCMeta):
    """
    Defines an interface for the server side GPGNet protocol
    """
    async def send_ConnectToPeer(self, player_name: str, player_uid: int, offer: bool):
        """
        Tells a client that has a listening LobbyComm instance to connect to the given peer
        :param player_name: Remote player name
        :param player_uid: Remote player identifier
        """
        await self.send_gpgnet_message('ConnectToPeer', [player_name, player_uid, offer])

    async def send_JoinGame(self, remote_player_name: str, remote_player_uid: int):
        """
        Tells the game to join the given peer by ID
        :param remote_player_name:
        :param remote_player_uid:
        """
        await self.send_gpgnet_message('JoinGame', [remote_player_name, remote_player_uid])

    async def send_HostGame(self, map_path):
        """
        Tells the game to start listening for incoming connections as a host
        :param map_path: Which scenario to use
        """
        await self.send_gpgnet_message('HostGame', [str(map_path)])

    async def send_DisconnectFromPeer(self, id: int):
        """
        Instructs the game to disconnect from the peer given by id

        :param id:
        :return:
        """
        await self.send_gpgnet_message('DisconnectFromPeer', [id])

    async def send_gpgnet_message(self, command_id: str, arguments: List[Union[int, str, bool]]):
        message = {"command": command_id, "args": arguments}
        await self.send(message)

    @abstractmethod
    async def send(self, message):
        pass  # pragma: no cover


class GpgNetClientProtocol(metaclass=ABCMeta):
    def send_GameState(self, arguments: List[Union[int, str, bool]]) -> None:
        """
        Sent by the client when the state of LobbyComm changes
        """
        self.send_gpgnet_message('GameState', arguments)

    @abstractmethod
    def send_gpgnet_message(self, command_id, arguments: List[Union[int, str, bool]]) -> None:
        pass  # pragma: no cover
