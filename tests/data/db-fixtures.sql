use faf_test;

-- Login table
delete from login;
insert into login (id, login, email, password) values (1, 'test', 'test@example.com', 'test_password');
insert into login (id, login, email, password) values (2, 'Dostya', 'dostya@cybran.example.com', 'vodka');
insert into login (id, login, email, password) values (3, 'Rhiza', 'rhiza@aeon.example.com', 'puff_the_magic_dragon');

-- global rating
delete from global_rating;
insert into global_rating (id, mean, deviation, numGames, is_active)
values
(1, 2000, 125, 5, 1),
(2, 1500, 75, 2, 1),
(3, 1650, 62.52, 2, 1);

-- ladder rating
delete from ladder1v1_rating;
insert into ladder1v1_rating (id, mean, deviation, numGames, is_active)
values
  (1, 2000, 125, 5, 1),
  (2, 1500, 75, 2, 1),
  (3, 1650, 62.52, 2, 1);

-- UniqueID_exempt
delete from uniqueid_exempt;
insert into uniqueid_exempt (user_id, reason) values (1, 'Because test');

-- Lobby version table
delete from version_lobby;
insert into version_lobby (id, `file`, version) values (1, 'some-installer.msi', 125);

-- Sample maps
delete from table_map;
insert into table_map (id, filename, `mapuid`)
values
(1, 'scmp_001/scmp_001.scenario_info.lua', 1),
(2, 'scmp_002/scmp_002.scenario_info.lua', 2),
(3, 'scmp_003/scmp_003.scenario_info.lua', 3),
(4, 'scmp_004/scmp_004.scenario_info.lua', 4),
(5, 'scmp_005/scmp_005.scenario_info.lua', 5),
(6, 'scmp_006/scmp_006.scenario_info.lua', 6),
(7, 'scmp_007/scmp_007.scenario_info.lua', 7),
(8, 'scmp_008/scmp_008.scenario_info.lua', 8),
(9, 'scmp_009/scmp_009.scenario_info.lua', 9),
(10, 'scmp_010/scmp_010.scenario_info.lua', 11),
(11, 'scmp_011/scmp_011.scenario_info.lua', 12),
(12, 'scmp_012/scmp_012.scenario_info.lua', 13),
(13, 'scmp_013/scmp_014.scenario_info.lua', 14),
(14, 'scmp_014/scmp_014.scenario_info.lua', 15),
(15, 'scmp_015/scmp_015.scenario_info.lua', 16);

-- game_stats table
delete from game_stats;
insert into game_stats (id, startTime, gameName, gameType, gameMod, `host`, mapId, validity)
values (1, NOW(), 'Test game', '0', 6, 1, 1, 0);

-- featured mods
delete from game_featuredMods;
insert into game_featuredMods (id, gamemod, name, description, publish)
values (1, 'faf', 'FAF', 'Forged Alliance Forever', 1),
       (6, 'ladder1v1', 'FAF', 'Ladder games', 1),
       (25, 'coop', 'Coop', 'Multiplayer campaign games', 1);

delete from friends_and_foes;
insert into friends_and_foes (user_id, subject_id, `status`)
values(42, 56, "FRIEND"),
      (42, 57, "FOE");
