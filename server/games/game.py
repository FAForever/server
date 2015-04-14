# -------------------------------------------------------------------------------
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
from enum import Enum, IntEnum
import string
import logging
import time

from PySide.QtSql import QSqlQuery
import functools
import trueskill
from server.proxy_map import ProxyMap
from server.abc.base_game import GameConnectionState, BaseGame, InitMode
from server.players import Player


class GameState(IntEnum):
    INITIALIZING = 0
    LOBBY = 1
    LIVE = 2
    ENDED = 3


class Victory(IntEnum):
    DEMORALIZATION = 0
    DOMINATION = 1
    ERADICATION = 2
    SANDBOX = 3

    @staticmethod
    def from_gpgnet_string(value):
        if value == "demoralization":
            return Victory.DEMORALIZATION
        elif value == "domination":
            return Victory.DOMINATION
        elif value == "eradication":
            return Victory.ERADICATION
        elif value == "sandbox":
            return Victory.SANDBOX


class GameError(Exception):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)


class Game(BaseGame):
    """
    Object that lasts for the lifetime of a game on FAF.
    """
    init_mode = InitMode.NORMAL_LOBBY

    def __init__(self, uuid, parent, host=None, hostId=0, hostIp=None, hostLocalIp=None, hostPort=6112,
                 name='None', map='SCMP_007', mode=0, minPlayer=1):
        """
        Initializes a new game
        :type uuid int
        :type host: None
        :type hostId: int
        :type hostIp: str
        :type hostLocalIp: str
        :type hostPort: int
        :type state: str
        :type name: str
        :type map: str
        :type mode: int
        :type minPlayer: int
        :return: Game
        """
        self._results = {}
        self.db = parent.db
        self.parent = parent
        self._player_options = {}
        self.createDate = time.time()
        self.receiveUdpHost = False
        self._logger = logging.getLogger("{}.{}".format(self.__class__.__qualname__, uuid))
        self.uuid = uuid
        self.ffa = False
        self.partial = 1
        self.access = "public"
        self.minPlayer = minPlayer
        self.maxPlayer = 12
        self.hostPlayer = host
        self.hostuuid = hostId
        self.hostip = hostIp
        self.hostport = hostPort
        self.name = name
        self.mapName = map
        self.password = None
        self._players = []
        self.size = 0
        self.options = []
        self.valid = True
        self.modsVersion = {}
        self.gameType = 0
        self.AIs = {}
        self.packetReceived = {}
        self.desyncs = 0
        self.invalidReason = None
        self.connecting = 0
        self.teamAssign = {}
        self.playerPosition = {}
        self.finalTeams = []
        self.gameScore = {}
        self.gameResult = {}
        self.gameFaResult = {}
        self.playerFaction = {}
        self.playerColor = {}
        self.state = GameState.INITIALIZING
        self._proxy = ProxyMap()
        self._connections = {}
        self.gameOptions = {'FogOfWar': 'explored',
                            'GameSpeed': 'normal',
                            'Victory': 'demoralization',
                            'CheatsEnabled': 'false',
                            'PrebuiltUnits': 'Off',
                            'NoRushOption': 'Off',
                            'RestrictedCategories': 0}

        self.mods = []
        self._logger.info("{} created".format(self))

    @property
    def armies(self):
        return frozenset({self.get_player_option(player.id, 'Army')
                          for player in self.players})

    @property
    def players(self):
        """
        Players in the game

        Depending on the state, it is either:
          - (LOBBY) The currently connected players
          - (LIVE) Players who participated in the game
          - Empty list
        :return: frozenset
        """
        if self.state == GameState.LIVE:
            result = self._players
        elif self.state == GameState.LOBBY:
            result = self._connections.keys()
        else:
            result = []
        return frozenset(result)

    @property
    def id(self):
        return self.uuid

    @property
    def teams(self):
        return frozenset({self.get_player_option(player.id, 'Team')
                          for player in self.players})

    @property
    def proxy(self):
        return self._proxy

    def add_result(self, reporter, army, result_type, score):
        """
        As computed by the game.
        :param army: army
        :param result: str
        :return:
        """
        assert army in self.armies
        if army not in self._results:
            self._results[army] = []
        self._logger.info("{} reported result for army {}: {} {}".format(reporter, army, result_type, score))
        self._results[army].append((reporter, result_type, score))

    def add_game_connection(self, game_connection):
        """
        Add a game connection to this game
        :param game_connection:
        :return:
        """
        if game_connection.state != GameConnectionState.CONNECTED_TO_HOST:
            raise GameError("Invalid GameConnectionState: {}".format(game_connection.state))
        if self.state != GameState.LOBBY:
            raise GameError("Invalid GameState: {state}".format(state=self.state))
        self._logger.info("Added game connection {}".format(game_connection))
        self._connections[game_connection.player] = game_connection

    def remove_game_connection(self, game_connection):
        """
        Remove a game connection from this game

        Will trigger on_game_end if there are no more active connections to the game
        :param peer:
        :param
        :return: None
        """
        assert game_connection in self._connections.values()
        del self._connections[game_connection.player]
        self._logger.info("Removed game connection {}".format(game_connection))
        if len(self._connections) == 0:
            self.on_game_end()

    def on_game_end(self):
        self.state = GameState.ENDED
        self._logger.info("Game ended")
        if self.desyncs > 20:
            self.setInvalid("Too many desyncs")

        query = QSqlQuery(self.db)
        query.prepare("UPDATE game_stats set `EndTime` = NOW() where `id` = ?")
        query.addBindValue(self.id)
        query.exec_()

        self.persist_results()
        self.rate_game()

    def persist_results(self):
        """
        Persist game results (score) into the game_player_stats table
        :return:
        """
        self._logger.info("Saving game scores")
        results = {}
        for player in self.players:
            army = self.get_player_option(player.id, 'Army')
            try:
                results[player] = self.get_army_result(army)
            except KeyError:
                # Default to -1 if there is no result
                results[player] = -1
        query = QSqlQuery(self.db)
        query.prepare("INSERT INTO game_player_stats (gameId, playerId, score, scoreTime) "
                      "VALUES (?, ?, ?, NOW())")
        game_ids = []
        player_ids = []
        scores = []
        for player, result in results.items():
            game_ids.append(self.id)
            player_ids.append(player.id)
            scores.append(result)
        query.addBindValue(game_ids)
        query.addBindValue(player_ids)
        query.addBindValue(scores)
        if not query.execBatch():
            self._logger.critical("Error persisting scores to database: {}".format(query.lastError()))

    def persist_rating_change_stats(self, rating_groups, rating='global'):
        """
        Persist computed ratings to the respective players' selected rating
        :param rating_groups: of the form returned by Game.compute_rating
        :return: None
        """
        self._logger.info("Saving rating change stats")
        new_ratings = {
            player: new_rating
            for team in rating_groups
            for player, new_rating in team.items()
        }
        game_stats_query = QSqlQuery(self.db)
        game_stats_query.prepare("UPDATE game_player_stats "
                                 "SET after_mean = ?, after_deviation = ?, scoreTime = NOW() "
                                 "WHERE gameId = ? AND playerId = ?")
        rating_query = QSqlQuery(self.db)
        rating_query.prepare("UPDATE {}_rating "
                             "SET mean = ?, is_active=1, deviation = ?, numGames = (numGames + 1) "
                             "WHERE id = ?".format(rating))
        results = [[], [], [], []]
        for player, new_rating in new_ratings.items():
            results[0] += [new_rating.mu]
            results[1] += [new_rating.sigma]
            results[2] += [self.id]
            results[3] += [player.id]
        for col in results:
            game_stats_query.addBindValue(col)

        for col in [results[0], results[1], results[3]]:
            rating_query.addBindValue(col)

        if not game_stats_query.execBatch():
            self._logger.critical("Error persisting ratings to game_player_stats: {}".format(game_stats_query.lastError()))

        if not rating_query.execBatch():
            self._logger.critical("Error persisting ratings to {}_rating: {}".format(rating, game_stats_query.lastError()))

    def set_player_option(self, id, key, value):
        """
        Set game-associative options for given player, by id
        :param id: int
        :type id: int
        :param key: option key string
        :type key: str
        :param value: option value
        :return: None
        """
        if id not in self._player_options:
            self._player_options[id] = {}
        self._player_options[id][key] = value

    def get_player_option(self, id, key):
        """
        Retrieve game-associative options for given player, by their uid
        :param id:
        :type id: int
        :param key:
        :return:
        """
        try:
            return self._player_options[id][key]
        except KeyError:
            return None

    def set_ai_option(self, name, key, value):
        """
        This is a noop for now
        :param name: Name of the AI
        :param key: option key string
        :param value: option value
        :return:
        """
        if not name in self.AIs:
            self.AIs[name] = {}
        self.AIs[name][key] = value

    def clear_slot(self, slot_index):
        """
        A somewhat awkward message while we're still half-slot-associated with a bunch of data.

        Just makes sure that any players associated with this
        slot aren't assigned an army or team, and deletes any AI's.
        :param slot_index:
        :return:
        """
        for player in self.players:
            if self.get_player_option(player.id, 'StartSpot') == slot_index:
                self.set_player_option(player.id, 'Team', -1)
                self.set_player_option(player.id, 'Army', -1)
                self.set_player_option(player.id, 'StartSpot', -1)

        to_remove = []
        for ai in self.AIs:
            if self.AIs[ai]['StartSpot'] == slot_index:
                to_remove.append(ai)
        for item in to_remove:
            del self.AIs[item]

    def validate_game(self):
        """
        General rules for validation of game rankedness
        """
        if self.gameOptions['Victory'] != Victory.DEMORALIZATION and self.getGamemod() != 'coop':
            self.setInvalid("Only assassination mode is ranked")

        elif self.gameOptions["FogOfWar"] != "explored":
            self.setInvalid("Fog of war not activated")

        elif self.gameOptions["CheatsEnabled"] != "false":
            self.setInvalid("Cheats were activated")

        elif self.gameOptions["PrebuiltUnits"] != "Off":
            self.setInvalid("Prebuilt was activated")

        elif self.gameOptions["NoRushOption"] != "Off":
            self.setInvalid("No rush games are not ranked")

        elif self.gameOptions["RestrictedCategories"] != 0:
            self.setInvalid("Restricted games are not ranked")

    def launch(self):
        """
        Mark the game as live.

        Freezes the set of active players so they are remembered if they drop.
        :return: None
        """
        assert self.state == GameState.LOBBY
        self._players = self.players
        self.state = GameState.LIVE
        self._logger.info("Game launched")
        self.validate_game()
        self.on_game_launched()

    def on_game_launched(self):
        for player in self.players:
            player.action = 'PLAYING'
        self.update_ratings()
        self.update_game_stats()
        self.update_game_player_stats()

    def update_game_stats(self):
        mapId = 0
        modId = 0

        # What the actual fucking fuck?
        if "thermo" in self.mapName.lower():
            self.setInvalid("This map is not ranked.")

        query = QSqlQuery(self.parent.db)
        # Everyone loves table sacns!
        queryStr = ("SELECT id FROM table_map WHERE filename LIKE '%/" + self.mapName + ".%'")
        query.exec_(queryStr)
        if query.size() > 0:
            query.first()
            mapId = query.value(0)

        if mapId != 0:
            query.prepare("SELECT * FROM table_map_unranked WHERE id = ?")
            query.addBindValue(mapId)
            query.exec_()
            if query.size() > 0:
                self.setInvalid("This map is not ranked.")

        # Why can't this be rephrased to use equality?
        queryStr = ("SELECT id FROM game_featuredMods WHERE gamemod LIKE '%s'" % self.getGamemod())
        query.exec_(queryStr)

        if query.size() == 1:
            query.first()
            modId = query.value(0)
        query = QSqlQuery(self.parent.db)
        query.prepare("UPDATE game_stats set `startTime` = NOW(),"
                      "gameType = ?,"
                      "gameMod = ?,"
                      "mapId = ?,"
                      "gameName = ? "
                      "WHERE id = ?")
        query.addBindValue(str(self.gameType))
        query.addBindValue(modId)
        query.addBindValue(mapId)
        query.addBindValue(self.name)
        query.addBindValue(self.uuid)
        if not query.exec_():
            self._logger.debug("Error updating game_stats:")
            self._logger.debug(query.lastError())
            self._logger.debug(self.mapName.lower())

        queryStr = ("UPDATE table_map_features set times_played = (times_played +1) WHERE map_id LIKE " + str(mapId))
        query.exec_(queryStr)

    def update_game_player_stats(self):
        queryStr = ""
        for player in self.players:
            player_option = functools.partial(self.get_player_option, player.id)
            options = {key: player_option(key)
                       for key in ['Team', 'StartSpot', 'Color', 'Faction']}
            valid = True
            for key, val in options.items():
                if val is None:
                    self._logger.error("PlayerOption {} not set for {}".format(key, player))
                    valid = False
            if not valid:
                continue

            if options['Team'] > 0 and options['StartSpot'] > 0:
                if self.getGamemod() == 'ladder1v1':
                    mean, dev = player.ladder_rating
                else:
                    mean, dev = player.global_rating
                queryStr += ("INSERT INTO `game_player_stats` "
                             "(`gameId`, `playerId`, `faction`, `color`, `team`, `place`, `mean`, `deviation`) "
                             "VALUES (%s, %s, %s, %s, %s, %i, %f, %f);"
                             .format(str(self.id),
                                     str(player.id),
                                     options['Faction'],
                                     options['Color'],
                                     options['Team'],
                                     options['StartSpot'], mean, dev))

        if queryStr != "":
            query = QSqlQuery(self.parent.db)
            if not query.exec_(queryStr):
                self._logger.error(query.lastError())
                self._logger.error(queryStr)
        else:
            self._logger.error("No player stat :(")

    def setAccess(self, access):
        self.access = access

    def setPassword(self, password):
        self.password = password

    def getGamemodVersion(self):
        return self.parent.getGamemodVersion()

    def setGameType(self, type):
        if type == "demoralization":
            self.gameType = 0
        elif type == "domination":
            self.gameType = 1
        elif type == "eradication":
            self.gameType = 2
        elif type == "sandbox":
            self.gameType = 3

    def getGamemod(self):
        return self.parent.gameTypeName

    def setInvalid(self, reason):
        self._logger.info("marked as invalid because: {}".format(reason))
        self.valid = False
        self.invalidReason = reason

    def get_army_result(self, army):
        """
        Since we log multiple results from multiple sources, we have to pick one.

        We're optimistic and simply choose the highest reported score.

        TODO: Flag games with conflicting scores for manual review.
        :param army index of army
        :raise KeyError
        :return:
        """
        score = 0
        for result in self._results[army]:
            score = max(score, result[2])
        return score

    def compute_rating(self, rating='global'):
        """
        Compute new ratings
        :param rating: 'global' or 'ladder'
        :return: rating groups of the form:
        >>> p1,p2,p3,p4 = Player()
        >>> [{p1: p1.rating, p2: p2.rating}, {p3: p3.rating, p4: p4.rating}]
        """
        assert self.state == GameState.LIVE or self.state == GameState.ENDED
        team_scores = {}
        for player in self.players:
            team = self.get_player_option(player.id, 'Team')
            army = self.get_player_option(player.id, 'Army')
            if not team:
                raise GameError("Missing team for player id: {}".format(player.id))
            if team not in team_scores:
                team_scores[team] = []
            try:
                team_scores[team] += [self.get_army_result(army)]
            except KeyError:
                team_scores[team] += [0]
                self._logger.info("Missing game result for {army}: {player}".format(army=army,
                                                                                    player=player))
        ranks = [score for team, score in sorted(team_scores.items())]
        rating_groups = []
        for team in sorted(self.teams):
            rating_groups += [{player: getattr(player, '{}_rating'.format(rating))
                            for player in self.players if
                            self.get_player_option(player.id, 'Team') == team}]
        return trueskill.rate(rating_groups, ranks)

    def update_ratings(self):
        """ Update all scores from the DB before updating the results"""
        self._logger.debug("updating ratings")
        for player in self.players:
            query = QSqlQuery(self.db)
            query.prepare(
                "SELECT mean, deviation FROM global_rating WHERE id = ?")
            query.addBindValue(player.id)
            query.exec_()
            if query.size() > 0:
                query.first()
                player.global_rating = (query.value(0), query.value(1))
            else:
                self._logger.debug("error updating a player")
                self._logger.debug(player.id)

    @property
    def created_at(self):
        """
        :rtype : time
        """
        return self.createDate

    def setHostIP(self, ip):
        if ip == '':
            return 0
        else:
            self.hostip = ip

    def setGameMap(self, map):
        if map == '':
            return False
        else:
            self.mapName = map

    def setGameHostPort(self, port):
        if port == '':
            return 0
        else:
            self.hostport = port

    def setGameHostName(self, host):
        if host == '':
            return 0
        else:
            self.hostPlayer = host

    def setGameHostUuid(self, uuid):
        if uuid == '':
            return 0
        else:
            self.hostuuid = uuid

    def getGameAddress(self):
        return "%s:%s" % (str(self.hostip), str(self.hostport))

    def __str__(self):
        return "Game({})".format(self.uuid)
