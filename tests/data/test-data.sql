insert into login (id, login, email, password, create_time) values
    (100, 'ladder1', 'ladder1@example.com', SHA2('ladder1', 256), '2000-01-01 00:00:00'),
    (101, 'ladder2', 'ladder2@example.com', SHA2('ladder2', 256), '2000-01-01 00:00:00'),
    (102, 'ladder_ban', 'ladder_ban@example.com', SHA2('ladder_ban', 256), '2000-01-01 00:00:00')
;


insert into global_rating (id, mean, deviation, numGames, is_active) values
    (100, 1500, 500, 0, 1),
    (101, 1500, 500, 0, 1),
    (102, 1500, 500, 0, 1)
;

insert into ladder1v1_rating (id, mean, deviation, numGames, is_active) values
    (100, 1500, 500, 0, 1),
    (101, 1500, 500, 0, 1),
    (102, 1500, 500, 0, 1)
;

delete from matchmaker_ban where id = 102 and userid = 102;
insert into matchmaker_ban (id, userid) values (102, 102);

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
    (2, 1, 'FRIEND');
