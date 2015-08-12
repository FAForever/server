from .gamesContainer import GamesContainer
from .ladderGamesContainer import Ladder1V1GamesContainer
from .coop import CoopGamesContainer
from .game import Game
from .ladderGame import Ladder1V1Game
from .custom_game import CustomGame

game_modes = [
    ('faf', 'FAF', GamesContainer),
    ('balancetesting', 'FAF (beta)', GamesContainer),
    ('ladder1v1', 'Ladder 1 vs 1', Ladder1V1GamesContainer),
    ('labwars', 'LABwars', GamesContainer),
    ('murderparty', 'Murder Party', GamesContainer),
    ('blackops', 'blackops', GamesContainer),
    ('xtremewars', 'Xtreme Wars', GamesContainer),
    ('diamond', 'Diamond', GamesContainer),
    ('vanilla', 'Vanilla', GamesContainer),
    ('civilians', 'Civilians Defense', GamesContainer),
    ('koth', 'King of the Hill', GamesContainer),
    ('claustrophobia', 'Claustrophobia', GamesContainer),
    ('supremedestruction', 'Supreme Destruction', GamesContainer),
    ('coop', 'coop', CoopGamesContainer),
]
