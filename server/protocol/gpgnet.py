from abc import ABCMeta, abstractmethod

from server.abc.base_game import InitMode


class GpgNetServerProtocol():
    __metaclass__ = ABCMeta

    @property
    @abstractmethod
    def connectivity_state(self):
        """
        The connectivity state of the peer this connection represents
        :rtype Connectivity
        """
        pass  # pragma: no cover

    @property
    @abstractmethod
    def player(self):
        """
        The connectivity state of the peer this connection represents
        :rtype Player
        """
        pass  # pragma: no cover

    @player.setter
    def player(self, val):
        pass  # pragma: no cover

    def send_CreateLobby(self, init_mode, port, login, uid, natTraversalProvider):
        """
        :type init_mode: InitMode
        :type port: int
        :type login: str
        :type uid: int
        :type natTraversalProvider: int
        :return:
        """
        self.send_gpgnet_message('CreateLobby', [int(init_mode.value), port, login, uid, natTraversalProvider])

    def send_ConnectToPeer(self, address_and_port: str, player_name: str, player_uid: int):
        self.send_gpgnet_message('ConnectToPeer', [address_and_port, player_name, player_uid])

    def send_ConnectToProxy(self, local_proxy_port: int, ip: str, player_name: str, player_uid: int):
        self.send_gpgnet_message('ConnectToProxy', [local_proxy_port, ip, player_name, player_uid])

    def send_JoinGame(self, address_and_port: str, as_observer: bool, remote_player_name: str, remote_player_uid: int):
        self.send_gpgnet_message('JoinGame', [address_and_port, as_observer, remote_player_name, remote_player_uid])

    def send_HostGame(self, map):
        self.send_gpgnet_message('HostGame', [str(map)])

    def send_SendNatPacket(self, address_and_port: str, message: str):
        self.send_gpgnet_message('SendNatPacket', [address_and_port, message])

    def send_Ping(self):
        self.send_gpgnet_message('ping', [])

    def handle_ProcessNatPacket(self, arguments):
        self.on_ProcessNatPacket(arguments[0], arguments[1])

    @abstractmethod
    def on_ProcessNatPacket(self, address_and_port, message):
        pass  # pragma: no cover

    @abstractmethod
    def send_gpgnet_message(self, command_id, arguments):
        pass  # pragma: no cover


class GpgNetClientProtocol(metaclass=ABCMeta):
    def send_GameState(self, arguments):
        self.send_gpgnet_message('GameState', arguments)

    def send_ProcessNatPacket(self, arguments):
        self.send_gpgnet_message('ProcessNatPacket', arguments)

    @abstractmethod
    def send_gpgnet_message(self, command_id, arguments):
        pass  # pragma: no cover
