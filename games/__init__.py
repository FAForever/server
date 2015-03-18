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



from .gamesContainer import gamesContainerClass
# derived
from .customGamesContainer import customGamesContainerClass # custom games
from .ladderGamesContainer import ladder1v1GamesContainerClass # ladder games
from .customNomadsGamesContainer import customNomadsGamesContainerClass # custom nomads games
from .customLabwarsGamesContainer import customLabwarsGamesContainerClass # custom labwars games
from .customMurderPartyGamesContainer import customMurderPartyGamesContainerClass # custom murder party games
from .customKothGamesContainer import customKothGamesContainerClass # custom king of the hill games
from .customPhantomXGamesContainer import customPhantomXGamesContainerClass # custom phantomX games
from .customBlackopsGamesContainer import customBlackopsGamesContainerClass # custom Blackops games

from .customXtremewarsGamesContainer import customXtremewarsGamesContainerClass # custom Blackops games

# game entity
from .game import Game
# derived
from .ladderGame import ladder1V1Game #ladder 1v1
from .customGame import customGame #custom
from .nomadsGame import nomadsGame #nomads
from .labwarsGame import labwarsGame #labwars

from .murderPartyGame import murderPartyGame # murder party
from .phantomXGame import phantomXGame # phantom X
from .kothGame import kothGame # king of the hill
from .blackopsGame import blackopsGame # exp war
from .xtremewarsGame import xtremewarsGame # exp war
