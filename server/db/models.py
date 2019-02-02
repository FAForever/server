from sqlalchemy import (TIMESTAMP, Boolean, Column, Float, ForeignKey, Integer,
                        MetaData, String, Table)
from sqlalchemy.dialects.mysql import BIGINT, ENUM, FLOAT, INTEGER

metadata = MetaData()

game_player_stats = Table(
    'game_player_stats', metadata,
    Column('id',        BIGINT(unsigned=True), primary_key=True),
    Column('gameId',    INTEGER(unsigned=True), ForeignKey('game_stats.id'), nullable=False),
    Column('playerId',  INTEGER(unsigned=True), nullable=False),
    Column('AI',        Boolean,                nullable=False),
    Column('faction',   INTEGER(unsigned=True), nullable=False),
    Column('color',     Integer,                nullable=False),
    Column('team',      Integer,                nullable=False),
    Column('place',     INTEGER(unsigned=True), nullable=False),
    Column('mean',      FLOAT(unsigned=True),   nullable=False),
    Column('deviation', FLOAT(unsigned=True),   nullable=False),
    Column('after_mean', Float),
    Column('after_deviation', Float),
    Column('score',     Integer),
    Column('scoreTime', TIMESTAMP),
)

game_stats = Table(
    'game_stats', metadata,
    Column('id',        INTEGER(unsigned=True), primary_key=True),
    Column('startTime', TIMESTAMP, nullable=False, server_default="CURRENT_TIMESTAMP"),
    Column('endTime',   TIMESTAMP),
    Column('gameType',  ENUM('0', '1', '2', '3'), nullable=False),
    Column('gameMod',   INTEGER(unsigned=True), nullable=False),
    Column('host',      INTEGER(unsigned=True), nullable=False),
    Column('mapId',     INTEGER(unsigned=True)),
    Column('gameName',  String,                 nullable=False),
    Column('validity',  INTEGER(unsigned=True), nullable=False),
)
