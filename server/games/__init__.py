#-------------------------------------------------------------------------------
# Copyright (c) 2014 Gael Honorez.
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the GNU Public License v3.0
# which accompanies this distribution, and is available at
# http://www.gnu.org/licenses/gpl.html
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#-------------------------------------------------------------------------------
from server.games.gamesContainer import GamesContainer
# derived
from server.games.ladderGamesContainer import Ladder1V1GamesContainer  # ladder games
from server.games.coopGamesContainer import CoopGamesContainer  # ladder games
# game entity
from server.games.game import Game
# derived
from server.games.ladderGame import Ladder1V1Game
from server.games.custom_game import CustomGame
