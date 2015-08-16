use faf_test;

-- Login table
delete from login;
insert into login (id, login, password) values (1, 'test', 'test_password');

-- global rating
delete from global_rating;
insert into global_rating (id, mean, deviation, numGames, is_active)
values (1, 2000, 125, 5, 1);

-- UniqueID_exempt
delete from uniqueid_exempt;
insert into uniqueid_exempt (user_id) values (1);

-- Lobby version table
delete from version_lobby;
insert into version_lobby (id, file, version) values (1, 'some-installer.msi', 125);

-- game_stats table
delete from game_stats;
insert into game_stats (id, startTime, gameName, gameType, gameMod)
values (1, NOW(), 'Test game', 0, 6);

-- Sample maps
delete from table_map;
insert into table_map (id, filename)
values
(1, 'scmp_001/scmp_001.scenario_info.lua'),
(2, 'scmp_002/scmp_002.scenario_info.lua'),
(3, 'scmp_003/scmp_003.scenario_info.lua'),
(4, 'scmp_004/scmp_004.scenario_info.lua'),
(5, 'scmp_005/scmp_005.scenario_info.lua'),
(6, 'scmp_006/scmp_006.scenario_info.lua'),
(7, 'scmp_007/scmp_007.scenario_info.lua'),
(8, 'scmp_008/scmp_008.scenario_info.lua'),
(9, 'scmp_009/scmp_009.scenario_info.lua'),
(10, 'scmp_010/scmp_010.scenario_info.lua'),
(11, 'scmp_011/scmp_011.scenario_info.lua'),
(12, 'scmp_012/scmp_012.scenario_info.lua'),
(13, 'scmp_013/scmp_014.scenario_info.lua'),
(14, 'scmp_014/scmp_014.scenario_info.lua'),
(15, 'scmp_015/scmp_015.scenario_info.lua');

-- featured mods
delete from game_featuredMods;
insert into game_featuredMods (id, gamemod, name, description, publish)
values (1, 'faf', 'FAF', 'Forged Alliance Forever', 1);

delete from friends;
insert into friends (idUser, idFriend)
values(42, 56);

delete from foes;
insert into foes (idUser, idFoe)
values(42, 57);
