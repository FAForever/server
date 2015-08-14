use faf_test;

-- Login table
delete from login;
insert into login (id, login, password) values (1, 'test', 'test_password');

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
(10, 'scmp_007/scmp_007.scenario_info.lua'),
(12, 'scmp_012/scmp_012.scenario_info.lua');

-- featured mods
delete from game_featuredMods;
insert into game_featuredMods (id, gamemod, name, description, publish)
values (1, 'faf', 'faf', 'Forged ALliance Forever', 1);
