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

import logging
logger = logging.getLogger(__name__)

from src.games.gamesContainer import gamesContainerClass
# derived
from src.games.ladderGamesContainer import ladder1v1GamesContainerClass # ladder games

# game entity
from src.games.game import Game
# derived
from src.games.ladderGame import ladder1V1Game #ladder 1v1
from src.games.custom_game import CustomGame #custom
