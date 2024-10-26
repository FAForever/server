from server.game_connection_matrix import ConnectionMatrix


def test_all_connected():
    # One by hand example
    matrix = ConnectionMatrix(
        established_peers={
            0: {1, 2, 3},
            1: {0, 2, 3},
            2: {0, 1, 3},
            3: {0, 1, 2},
        },
    )
    assert matrix.get_unconnected_peer_ids() == set()

    # Check every fully connected grid, including the empty grid
    for num_players in range(0, 16 + 1):
        matrix = ConnectionMatrix(
            established_peers={
                player_id: {
                    peer_id
                    for peer_id in range(num_players)
                    if peer_id != player_id
                }
                for player_id in range(num_players)
            },
        )
        assert matrix.get_unconnected_peer_ids() == set()


def test_1v1_not_connected():
    matrix = ConnectionMatrix(
        established_peers={
            0: set(),
            1: set(),
        },
    )
    assert matrix.get_unconnected_peer_ids() == {0, 1}


def test_2v2_one_player_not_connected():
    # 0 is not connected to anyone
    matrix = ConnectionMatrix(
        established_peers={
            0: set(),
            1: {2, 3},
            2: {1, 3},
            3: {1, 2},
        },
    )
    assert matrix.get_unconnected_peer_ids() == {0}


def test_2v2_two_players_not_connected():
    # 0 is not connected to anyone
    # 1 is not connected to anyone
    matrix = ConnectionMatrix(
        established_peers={
            0: set(),
            1: set(),
            2: {3},
            3: {2},
        },
    )
    assert matrix.get_unconnected_peer_ids() == {0, 1}


def test_2v2_not_connected():
    # Not possible for only 3 players to be completely disconnected in a 4
    # player game. Either 1, 2, or all can be disconnected.
    matrix = ConnectionMatrix(
        established_peers={
            0: set(),
            1: set(),
            2: set(),
            3: set(),
        },
    )
    assert matrix.get_unconnected_peer_ids() == {0, 1, 2, 3}


def test_2v2_one_pair_not_connected():
    # 0 and 1 are not connected to each other
    matrix = ConnectionMatrix(
        established_peers={
            0: {2, 3},
            1: {2, 3},
            2: {0, 1, 3},
            3: {0, 1, 2},
        },
    )
    assert matrix.get_unconnected_peer_ids() == {0, 1}


def test_2v2_two_pairs_not_connected():
    # 0 and 1 are not connected to each other
    # 1 and 2 are not connected to each other
    matrix = ConnectionMatrix(
        established_peers={
            0: {2, 3},
            1: {3},
            2: {0, 3},
            3: {0, 1, 2},
        },
    )
    assert matrix.get_unconnected_peer_ids() == {1}


def test_2v2_two_disjoint_pairs_not_connected():
    # 0 and 1 are not connected to each other
    # 2 and 3 are not connected to each other
    matrix = ConnectionMatrix(
        established_peers={
            0: {2, 3},
            1: {2, 3},
            2: {0, 1},
            3: {0, 1},
        },
    )
    assert matrix.get_unconnected_peer_ids() == {0, 1, 2, 3}


def test_2v2_three_pairs_not_connected():
    # 0 and 1 are not connected to each other
    # 1 and 2 are not connected to each other
    # 2 and 3 are not connected to each other
    matrix = ConnectionMatrix(
        established_peers={
            0: {2, 3},
            1: {3},
            2: {0},
            3: {0, 1},
        },
    )
    assert matrix.get_unconnected_peer_ids() == {1, 2}


def test_3v3_one_player_not_connected():
    # 0 is not connected to anyone
    matrix = ConnectionMatrix(
        established_peers={
            0: set(),
            1: {2, 3, 4, 5},
            2: {1, 3, 4, 5},
            3: {1, 2, 4, 5},
            4: {1, 2, 3, 5},
            5: {1, 2, 3, 4},
        },
    )
    assert matrix.get_unconnected_peer_ids() == {0}


def test_3v3_two_players_not_connected():
    # 0 is not connected to anyone
    # 1 is not connected to anyone
    matrix = ConnectionMatrix(
        established_peers={
            0: set(),
            1: set(),
            2: {3, 4, 5},
            3: {2, 4, 5},
            4: {2, 3, 5},
            5: {2, 3, 4},
        },
    )
    assert matrix.get_unconnected_peer_ids() == {0, 1}


def test_3v3_three_players_not_connected():
    # 0 is not connected to anyone
    # 1 is not connected to anyone
    # 2 is not connected to anyone
    matrix = ConnectionMatrix(
        established_peers={
            0: set(),
            1: set(),
            2: set(),
            3: {4, 5},
            4: {3, 5},
            5: {3, 4},
        },
    )
    assert matrix.get_unconnected_peer_ids() == {0, 1, 2}


def test_3v3_four_players_not_connected():
    # 0 is not connected to anyone
    # 1 is not connected to anyone
    # 2 is not connected to anyone
    # 3 is not connected to anyone
    matrix = ConnectionMatrix(
        established_peers={
            0: set(),
            1: set(),
            2: set(),
            3: set(),
            4: {5},
            5: {4},
        },
    )
    assert matrix.get_unconnected_peer_ids() == {0, 1, 2, 3}


def test_3v3_not_connected():
    matrix = ConnectionMatrix(
        established_peers={
            0: set(),
            1: set(),
            2: set(),
            3: set(),
            4: set(),
            5: set(),
        },
    )
    assert matrix.get_unconnected_peer_ids() == {0, 1, 2, 3, 4, 5}


def test_3v3_one_pair_not_connected():
    # 0 and 1 are not connected to each other
    matrix = ConnectionMatrix(
        established_peers={
            0: {2, 3, 4, 5},
            1: {2, 3, 4, 5},
            2: {0, 1, 3, 4, 5},
            3: {0, 1, 2, 4, 5},
            4: {0, 1, 2, 3, 5},
            5: {0, 1, 2, 3, 4},
        },
    )
    assert matrix.get_unconnected_peer_ids() == {0, 1}


def test_3v3_one_player_and_one_pair_not_connected():
    # 0 is not connected to anyone
    # 1 and 2 are not connected to each other
    matrix = ConnectionMatrix(
        established_peers={
            0: set(),
            1: {3, 4, 5},
            2: {3, 4, 5},
            3: {1, 2, 4, 5},
            4: {1, 2, 3, 5},
            5: {1, 2, 3, 4},
        },
    )
    assert matrix.get_unconnected_peer_ids() == {0, 1, 2}
