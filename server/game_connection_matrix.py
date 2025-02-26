from collections import defaultdict


class ConnectionMatrix:
    def __init__(self, established_peers: dict[int, set[int]]):
        self.established_peers = established_peers

    def get_unconnected_peer_ids(self) -> set[int]:
        unconnected_peer_ids: set[int] = set()

        # Group players by number of connected peers
        players_by_num_peers = defaultdict(list)
        for player_id, peer_ids in self.established_peers.items():
            players_by_num_peers[len(peer_ids)].append((player_id, peer_ids))

        # Mark players with least number of connections as unconnected if they
        # don't meet the connection threshold. Each time a player is marked as
        # 'unconnected', remaining players need 1 less connection to be
        # considered connected.
        connected_peers = dict(self.established_peers)
        for num_connected, peers in sorted(players_by_num_peers.items()):
            if num_connected < len(connected_peers) - 1:
                for player_id, peer_ids in peers:
                    unconnected_peer_ids.add(player_id)
                    del connected_peers[player_id]

        return unconnected_peer_ids
