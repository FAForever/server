from unittest import mock

from server.proxy_map import ProxyMap


def test_map_dup():
    map = ProxyMap()
    p1 = mock.Mock()
    p2 = mock.Mock()
    mapped_port = map.map(p1, p2)
    assert mapped_port == 0
    map_2 = map.map(p1, p2)
    assert map_2 == 0

def test_map_dup_reverse():
    map = ProxyMap()
    p1 = mock.Mock()
    p2 = mock.Mock()
    assert map.map(p1, p2) == map.map(p2, p1)


def test_map_all():
    map = ProxyMap()
    players = [mock.Mock() for _ in range(8)]
    ports = []
    for p1 in players:
        for p2 in players:
            if p1 != p2:
                ports.append(map.map(p1, p2))
    assert -1 not in ports


def test_contains():
    map = ProxyMap()
    p1 = mock.MagicMock()
    players = (p1, mock.MagicMock())
    map.map(*players)
    assert players in map
    assert p1 in map


def test_unmap():
    map = ProxyMap()
    players = (mock.MagicMock(), mock.MagicMock())
    map.map(*players)
    map.unmap(players[0])
    assert players not in map
