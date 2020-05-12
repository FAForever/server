from sqlalchemy import (
    TIME, TIMESTAMP, Boolean, Column, DateTime, Enum, Float, ForeignKey,
    Integer, MetaData, String, Table, Text
)

from ..games.game import Victory

metadata = MetaData()

avatars = Table(
    'avatars', metadata,
    Column('id',            Integer,    primary_key=True),
    Column('idUser',        Integer,    ForeignKey('login.id')),
    Column('idAvatar',      Integer,    ForeignKey('avatars_list.id')),
    Column('selected',      Boolean,    nullable=False),
    Column('expires_at',    TIMESTAMP),
    Column('create_time',   TIMESTAMP,  nullable=False),
    Column('update_time',   TIMESTAMP,  nullable=False)
)

avatars_list = Table(
    'avatars_list', metadata,
    Column('id',            Integer,    primary_key=True),
    Column('url',           String,     nullable=False),
    Column('tooltip',       String),
    Column('create_time',   TIMESTAMP,  nullable=False),
    Column('update_time',   TIMESTAMP,  nullable=False)
)

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

clan = Table(
    'clan', metadata,
    Column('id',            Integer,    primary_key=True),
    Column('name',          String,     nullable=False),
    Column('tag',           String,     nullable=False),
    Column('founder_id',    Integer,    ForeignKey('login.id')),
    Column('leader_id',     Integer,    ForeignKey('login.id')),
    Column('description',   String),
    Column('tag_color',     String),
    Column('create_time',   TIMESTAMP,  nullable=False),
    Column('update_time',   TIMESTAMP,  nullable=False)
)

clan_membership = Table(
    'clan_membership', metadata,
    Column('id',            Integer,    primary_key=True),
    Column('clan_id',       Integer,    ForeignKey('clan.id'),   nullable=False),
    Column('player_id',     Integer,    ForeignKey('login.id'),  nullable=False),
    Column('create_time',   TIMESTAMP,  nullable=False),
    Column('update_time',   TIMESTAMP,  nullable=False)
)

coop_leaderboard = Table(
    'coop_leaderboard', metadata,
    Column('id',            Integer,    primary_key=True),
    Column('mission',       Integer),
    Column('gameuid',       Integer,    ForeignKey('game_stats')),
    Column('secondary',     Integer),
    Column('time',          TIME),
    Column('player_count',  Integer)
)

coop_map = Table(
    'coop_map', metadata,
    Column('id',            Integer,    primary_key=True),
    Column('type',          Integer,    nullable=False),
    Column('name',          String),
    Column('description',   String),
    Column('filename',      String,     index=True)
)

friends_and_foes = Table(
    'friends_and_foes', metadata,
    Column('user_id',       Integer, ForeignKey('login.id')),
    Column('subject_id',    Integer, ForeignKey('login.id')),
    Column('status',        Enum('FRIEND', 'FOE'))
)

game_featuredMods = Table(
    'game_featuredMods', metadata,
    Column('id',             Integer,    primary_key=True),
    Column('gamemod',        String,     unique=True),
    Column('description',    Text,       nullable=False),
    Column('name',           String,     nullable=False),
    Column('publish',        Boolean,    nullable=False, server_default='f'),
    Column('order',          Integer,    nullable=False, server_default='0'),
    Column('git_url',        String),
    Column('git_branch',     String),
    Column('file_extension', String),
    Column('allow_override', Boolean)
)

game_player_stats = Table(
    'game_player_stats', metadata,
    Column('id',            Integer, primary_key=True),
    Column('gameId',        Integer, ForeignKey('game_stats.id'), nullable=False),
    Column('playerId',      Integer, ForeignKey('login.id'),      nullable=False),
    Column('AI',            Boolean, nullable=False),
    Column('faction',       Integer, nullable=False),
    Column('color',         Integer, nullable=False),
    Column('team',          Integer, nullable=False),
    Column('place',         Integer, nullable=False),
    Column('mean',          Float,   nullable=False),
    Column('deviation',     Float,   nullable=False),
    Column('after_mean',    Float),
    Column('after_deviation', Float),
    Column('score',         Integer),
    Column('scoreTime',     TIMESTAMP),
)

game_stats = Table(
    'game_stats', metadata,
    Column('id',        Integer,        primary_key=True),
    Column('startTime', TIMESTAMP,      nullable=False, server_default="CURRENT_TIMESTAMP"),
    Column('endTime',   TIMESTAMP),
    Column('gameType',  Enum(Victory),  nullable=False),
    Column('gameMod',   Integer,        ForeignKey('game_featuredMods.id'), nullable=False),
    Column('host',      Integer,        nullable=False),
    Column('mapId',     Integer),
    Column('gameName',  String,         nullable=False),
    Column('validity',  Integer,        nullable=False),
)

global_rating = Table(
    'global_rating', metadata,
    Column('id',        Integer,    ForeignKey('login.id'), primary_key=True),
    Column('mean',      Float),
    Column('deviation', Float),
    Column('numGames',  Integer,    nullable=False),
    Column('is_active', Boolean,    nullable=False),
)

login = Table(
    'login', metadata,
    Column('id',            Integer,    primary_key=True),
    Column('login',         String,     nullable=False, unique=True),
    Column('password',      String,     nullable=False),
    Column('email',         String,     nullable=False, unique=True),
    Column('ip',            String),
    Column('steamid',       Integer,    unique=True),
    Column('create_time',   TIMESTAMP,  nullable=False),
    Column('update_time',   TIMESTAMP,  nullable=False),
    Column('user_agent',    String),
    Column('last_login',    TIMESTAMP)
)

ladder1v1_rating = Table(
    'ladder1v1_rating', metadata,
    Column('id',            Integer,    ForeignKey('login.id'), primary_key=True),
    Column('mean',          Float),
    Column('deviation',     Float),
    Column('numGames',      Integer,    nullable=False),
    Column('winGames',      Integer,    nullable=False),
    Column('is_active',     Boolean,    nullable=False)
)

# This is actually a view into the `ban` table with proper handling of ban
# expiration and revocation
lobby_ban = Table(
    'lobby_ban', metadata,
    Column('idUser',        Integer,    ForeignKey('login.id'), primary_key=True),
    Column('reason',        Text,       nullable=False),
    Column('expires_at',    DateTime)
)


map = Table(
    'map', metadata,
    Column('id',            Integer,        primary_key=True),
    Column('display_name',  String(100),    nullable=False),
    Column('map_type',      String(15),     nullable=False),
    Column('battle_type',   String(15),     nullable=False),
    Column('author',        Integer,        ForeignKey('login.id')),
    Column('average_review_score', Float,   nullable=False),
    Column('reviews',       Integer,        nullable=False),
    Column('create_time',   TIMESTAMP,      nullable=False),
    Column('update_time',   TIMESTAMP,      nullable=False)
)

map_pool = Table(
    'map_pool', metadata,
    Column('id',            Integer,        primary_key=True),
    Column('name',          String(255),    nullable=False),
    Column('create_time',   TIMESTAMP,      nullable=False),
    Column('update_time',   TIMESTAMP,      nullable=False)
)

map_pool_map_version = Table(
    'map_pool_map_version', metadata,
    Column('map_pool_id',       Integer, ForeignKey('map_pool.id'),     nullable=False),
    Column('map_version_id',    Integer, ForeignKey('map_version.id'),  nullable=False),
)

map_version = Table(
    'map_version', metadata,
    Column('id',            Integer,        primary_key=True),
    Column('description',   Text),
    Column('max_players',   Integer,        nullable=False),
    Column('width',         Integer,        nullable=False),
    Column('height',        Integer,        nullable=False),
    Column('version',       Integer,        nullable=False),
    Column('filename',      String(200),    nullable=False),
    Column('ranked',        Boolean,        nullable=False),
    Column('hidden',        Boolean,        nullable=False),
    Column('map_id',        ForeignKey('map.id'), nullable=False),
    Column('create_time', TIMESTAMP,        nullable=False),
    Column('update_time', TIMESTAMP,        nullable=False),
)

matchmaker_queue = Table(
    'matchmaker_queue', metadata,
    Column('id',                Integer,        primary_key=True),
    Column('technical_name',    String(255),    nullable=False, unique=True),
    Column('featured_mod_id',   Integer,        ForeignKey('game_featuredMods.id'), nullable=False),
    Column('leaderboard_id',    Integer,        ForeignKey('leaderboard.id'),       nullable=False),
    Column('name_key',          String(255),    nullable=False),
    Column('create_time',   TIMESTAMP,      nullable=False),
    Column('update_time',   TIMESTAMP,      nullable=False)
)

matchmaker_queue_map_pool = Table(
    'matchmaker_queue_map_pool', metadata,
    Column('matchmaker_queue_id',   Integer,    ForeignKey('matchmaker_queue.id'),  nullable=False),
    Column('map_pool_id',           Integer,    ForeignKey('map_pool.id'),          nullable=False),
    Column('min_rating',            Integer),
    Column('max_rating',            Integer),
)

moderation_report = Table(
   'moderation_report', metadata,
   Column('id',                     Integer,                        primary_key=True),
   Column('reporter_id',            ForeignKey('login.id'),         nullable=False),
   Column('report_description',     Text),
   Column('report_status',          Enum('AWAITING', 'PROCESSING', 'COMPLETED', 'DISCARDED'), nullable=False),
   Column('game_id',                ForeignKey('game_stats.id'),    index=True),
   Column('game_incident_timecode', String(100)),
   Column('moderator_notice',       Text),
   Column('moderator_private_note', Text),
   Column('last_moderator',         ForeignKey('login.id'),         index=True),
   Column('create_time',            TIMESTAMP,                      nullable=False),
   Column('update_time',            TIMESTAMP,                      nullable=False),
)

reported_user = Table(
   'reported_user', metadata,
   Column('id',             Integer,                            primary_key=True),
   Column('player_id',      ForeignKey('login.id'),             nullable=False),
   Column('report_id',      ForeignKey('moderation_report.id'), nullable=False),
   Column('create_time',    TIMESTAMP,                          nullable=False),
   Column('update_time',    TIMESTAMP,                          nullable=False)
)

teamkills = Table(
    'teamkills', metadata,
    Column('id',            Integer, primary_key=True),
    Column('teamkiller',    Integer, ForeignKey('login.id')),
    Column('victim',        Integer, ForeignKey('login.id')),
    Column('game_id',       Integer, ForeignKey('game_stats.id')),
    Column('gametime',      Integer),
)
