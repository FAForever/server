"""
The team matchmaking system

Used to keep track of current player parties, manage players joining/leaving and matching them against each other
used for matchmaking in the global rating system
"""
from .player_party import PlayerParty
from .party_member import PartyMember

__all__ = [
    'PlayerParty',
    'PartyMember'
]
