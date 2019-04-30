from sqlalchemy import (TIMESTAMP, Boolean, Column, DateTime, Enum, Float,
                        ForeignKey, Integer, MetaData, String, Table, Text)

from ..games.game import Victory

metadata = MetaData()

ban = Table(
    'ban', metadata,
    Column('id',            Integer,    primary_key=True),
    Column('player_id',     Integer,    ForeignKey('login.id'), nullable=False),
    Column('author_id',     Integer,    ForeignKey('login.id'), nullable=False),
    Column('reason',        Text,       nullable=False),
    Column('expires_at',    DateTime),
    Column('level',         Enum('CHAT', 'GLOBAL'), nullable=False),
    Column('create_time',   TIMESTAMP,  nullable=False),
    Column('update_time',   TIMESTAMP,  nullable=False),
    Column('report_id',     Integer,    ForeignKey('moderation_report.id'))
)

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
