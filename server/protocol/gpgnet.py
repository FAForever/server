from abc import ABCMeta, abstractmethod


from typing import List, Union
from server.abc.base_game import InitMode


class GpgNetServerProtocol(metaclass=ABCMeta):
    """
    Defines an interface for the server side GPGNet protocol
    """
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

    def send_ConnectToPeer(self, address_and_port: str, player_name: str, player_uid: int):
        """
        Tells a client that has a listening LobbyComm instance to connect to the given peer
        :param address_and_port: String of the form "adress:port"
        :param player_name: Remote player name
        :param player_uid: Remote player identifier
        """
        self.send_gpgnet_message('ConnectToPeer', [address_and_port, player_name, player_uid])

    def send_ConnectToProxy(self, local_proxy_port: int, ip: str, player_name: str, player_uid: int):
        """
        Tells the FAF client to connect to the given peer by proxy
        :param local_proxy_port: Which local proxy port to use
        :param ip: remote address
        :param player_name: Remote player name
        :param player_uid: Remote player identifier
        """
        self.send_gpgnet_message('ConnectToProxy', [local_proxy_port, ip, player_name, player_uid])

    def send_JoinProxy(self, local_proxy_port: int, ip: str, player_name: str, player_uid: int):
        """
        Tells the FAF client to join the given game by proxy
        :param local_proxy_port: Which local proxy port to use
        :param ip: remote address
        :param player_name: Remote player name
        :param player_uid: Remote player identifier
        """
        self.send_gpgnet_message('JoinProxy', [local_proxy_port, ip, player_name, player_uid])

    def send_JoinGame(self, address_and_port: str, remote_player_name: str, remote_player_uid: int):
        """
        Tells the game to join the given peer by address_and_port
        :param address_and_port:
        :param remote_player_name:
        :param remote_player_uid:
        """
        self.send_gpgnet_message('JoinGame', [address_and_port, remote_player_name, remote_player_uid])

    def send_HostGame(self, map):
        """
        Tells the game to start listening for incoming connections as a host
        :param map: Which scenario to use
        """
        self.send_gpgnet_message('HostGame', [str(map)])

    def send_SendNatPacket(self, address_and_port: str, message: str):
        """
        Instructs the game to send a nat-traversal UDP packet to the given remote address and port.

        The game will send the message verbatim as UDP-datagram prefixed with a \0x08 byte.
        :param address_and_port:
        :param message:
        """
        self.send_gpgnet_message('SendNatPacket', [address_and_port, message])

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

    def send_ProcessNatPacket(self, arguments: List[Union[int, str, bool]]) -> None:
        """
        Sent by the client when it received a nat packet
        :param arguments:
        :return:
        """
        self.send_gpgnet_message('ProcessNatPacket', arguments)

    @abstractmethod
    def send_gpgnet_message(self, command_id, arguments: List[Union[int, str, bool]]) -> None:
        pass  # pragma: no cover
