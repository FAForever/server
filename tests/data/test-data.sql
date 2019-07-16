insert into login (id, login, email, password, create_time) values
    (50,  'player_service1', 'ps1@example.com', SHA2('player_service1', 256), '2000-01-01 00:00:00'),
    (51,  'player_service2', 'ps2@example.com', SHA2('player_service2', 256), '2000-01-01 00:00:00'),
    (52,  'player_service3', 'ps3@example.com', SHA2('player_service3', 256), '2000-01-01 00:00:00'),
    (100, 'ladder1', 'ladder1@example.com', SHA2('ladder1', 256), '2000-01-01 00:00:00'),
    (101, 'ladder2', 'ladder2@example.com', SHA2('ladder2', 256), '2000-01-01 00:00:00'),
    (102, 'ladder_ban', 'ladder_ban@example.com', SHA2('ladder_ban', 256), '2000-01-01 00:00:00'),
    (200, 'banme', 'banme@example.com', SHA2('banme', 256), '2000-01-01 00:00:00')
;

delete from clan_membership where player_id = 50;
insert into clan_membership (clan_id, player_id) values
    (1, 50);

insert into global_rating (id, mean, deviation, numGames, is_active) values
    (50,  1200, 250, 42, 1),
    (51,  1200, 250, 42, 1),
    (52,  1200, 250, 42, 1),
    (100, 1500, 500, 0, 1),
    (101, 1500, 500, 0, 1),
    (102, 1500, 500, 0, 1)
;

insert into ladder1v1_rating (id, mean, deviation, numGames, is_active) values
    (50,  1300, 400, 12, 1),
    (51,  1300, 400, 12, 1),
    (52,  1300, 400, 12, 1),
    (100, 1500, 500, 0, 1),
    (101, 1500, 500, 0, 1),
    (102, 1500, 500, 0, 1)
;

insert into avatars (idUser, idAvatar, selected) values
    (50, 2, 1),
    (51, 1, 0),
    (51, 2, 1),
    (52, 1, 1),
    (52, 2, 0);

delete from ban where player_id = 200;

insert into game_stats (id, startTime, gameType, gameMod, host, mapId, gameName, validity) values
    (41935, NOW(), '0', 6, 1, 0, 'MapRepetition', 0),
    (41936, NOW() + interval 1 minute, '0', 6, 1, 1, 'MapRepetition', 0),
    (41937, NOW() + interval 2 minute, '0', 6, 1, 2, 'MapRepetition', 0),
    (41938, NOW() + interval 3 minute, '0', 6, 1, 3, 'MapRepetition', 0),
    (41939, NOW() + interval 4 minute, '0', 6, 1, 4, 'MapRepetition', 0),
    (41940, NOW() + interval 5 minute, '0', 6, 1, 5, 'MapRepetition', 0),
    (41941, NOW() + interval 6 minute, '0', 6, 1, 6, 'MapRepetition', 0);

insert into game_player_stats (gameId, playerId, AI, faction, color, team, place, mean, deviation, scoreTime) values
    (1, 1, 0, 0, 0, 2, 0, 1500, 500, NOW()),
    (41935, 1, 0, 0, 0, 2, 0, 1500, 500, NOW()),
    (41936, 1, 0, 0, 0, 2, 0, 1500, 500, NOW() + interval 1 minute),
    (41937, 1, 0, 0, 0, 2, 0, 1500, 500, NOW() + interval 2 minute),
    (41938, 1, 0, 0, 0, 2, 0, 1500, 500, NOW() + interval 3 minute),
    (41939, 1, 0, 0, 0, 2, 0, 1500, 500, NOW() + interval 4 minute),
    (41940, 1, 0, 0, 0, 2, 0, 1500, 500, NOW() + interval 5 minute),
    (41941, 1, 0, 0, 0, 2, 0, 1500, 500, NOW() + interval 6 minute);

delete from friends_and_foes where user_id = 1 and subject_id = 2;
insert into friends_and_foes (user_id, subject_id, status) values
    (2, 1, 'FRIEND'),
    (50, 1, 'FRIEND'),
    (50, 51, 'FRIEND'),
    (50, 52, 'FOE');


insert into `mod` (id, display_name, author) values
    (100, 'Mod without icon', 'askaholic');

insert into mod_version (mod_id, uid, version, description, type, filename, icon) VALUES
        (100, 'FFF', 1, 'The best version so far', 'UI', 'noicon.zip', null);
