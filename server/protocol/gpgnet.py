from abc import ABCMeta, abstractmethod

from typing import List, Union
from server.abc.base_game import InitMode


class GpgNetServerProtocol(metaclass=ABCMeta):
    """
    Defines an interface for the server side GPGNet protocol
    """

    # TODO: Do we need to remove port parameters here?
    def send_CreateLobby(self, init_mode: InitMode, port: int, login: str, uid: int, natTraversalProvider: int):
        """
        Tells the client to create a new LobbyComm instance and have it listen on the given port number
        :type init_mode: Whether to use ranked or ladder mode for the in game lobby
        :type port: The port number for the client to listen on
        :type login: The username of the player
        :type uid: The identifier of the player
        :type natTraversalProvider: A number representing the nat-traversal-provider, typically 1
        """
        self.send_gpgnet_message('CreateLobby', [int(init_mode.value), port, login, uid, natTraversalProvider])

    def send_ConnectToPeer(self, player_name: str, player_uid: int, offer: bool):
        """
        Tells a client that has a listening LobbyComm instance to connect to the given peer
        :param player_name: Remote player name
        :param player_uid: Remote player identifier
        """
        self.send_gpgnet_message('ConnectToPeer', [player_name, player_uid, offer])

    def send_JoinGame(self, remote_player_name: str, remote_player_uid: int):
        """
        Tells the game to join the given peer by ID
        :param remote_player_name:
        :param remote_player_uid:
        """
        self.send_gpgnet_message('JoinGame', [remote_player_name, remote_player_uid])

    def send_HostGame(self, map):
        """
        Tells the game to start listening for incoming connections as a host
        :param map: Which scenario to use
        """
        self.send_gpgnet_message('HostGame', [str(map)])

    def send_DisconnectFromPeer(self, id: int):
        """
        Instructs the game to disconnect from the peer given by id

        :param id:
        :return:
        """
        self.send_gpgnet_message('DisconnectFromPeer', [id])

    def send_Ping(self):
        """
        Heartbeat pinging used between the FAF client and server
        :return:
        """
        self.send_gpgnet_message('ping', [])

    def send_gpgnet_message(self, command_id, arguments):
        message = {"command": command_id, "args": arguments}
        self.send_message(message)

    @abstractmethod
    def send_message(self, message):
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
