from sqlalchemy import (TIMESTAMP, Boolean, Column, Enum, Float, ForeignKey,
                        Integer, MetaData, String, Table, Text)

from ..games.game import Victory

metadata = MetaData()

friends_and_foes = Table(
    'friends_and_foes', metadata,
    Column('user_id',       Integer, ForeignKey('login.id')),
    Column('subject_id',    Integer, ForeignKey('login.id')),
    Column('status',        Enum('FRIEND', 'FOE'))
)

game_featuredMods = Table(
    'game_featuredMods', metadata,
    Column('id',            Integer,    primary_key=True),
    Column('gamemod',       String,     unique=True),
    Column('descripiton',   Text,       nullable=False),
    Column('name',          String,     nullable=False),
    Column('publish',       Boolean,    nullable=False, server_default='f'),
    Column('order',         Integer,    nullable=False, server_default='0'),
    Column('git_url',       String),
    Column('git_branch',    String),
    Column('file_extension',String),
    Column('allow_override',Boolean)
)

game_player_stats = Table(
    'game_player_stats', metadata,
    Column('id',        Integer, primary_key=True),
    Column('gameId',    Integer, ForeignKey('game_stats.id'), nullable=False),
    Column('playerId',  Integer, nullable=False),
    Column('AI',        Boolean, nullable=False),
    Column('faction',   Integer, nullable=False),
    Column('color',     Integer, nullable=False),
    Column('team',      Integer, nullable=False),
    Column('place',     Integer, nullable=False),
    Column('mean',      Float,   nullable=False),
    Column('deviation', Float,   nullable=False),
    Column('after_mean', Float),
    Column('after_deviation', Float),
    Column('score',     Integer),
    Column('scoreTime', TIMESTAMP),
)

game_stats = Table(
    'game_stats', metadata,
    Column('id',        Integer,    primary_key=True),
    Column('startTime', TIMESTAMP,  nullable=False, server_default="CURRENT_TIMESTAMP"),
    Column('endTime',   TIMESTAMP),
    Column('gameType',  Enum(Victory), nullable=False),
    Column('gameMod',   Integer, ForeignKey('game_featuredMods.id'), nullable=False),
    Column('host',      Integer,                nullable=False),
    Column('mapId',     Integer),
    Column('gameName',  String,                 nullable=False),
    Column('validity',  Integer,                nullable=False),
)
