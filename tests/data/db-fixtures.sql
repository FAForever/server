use faf_test;

-- Login table
delete from login;
insert into login (id, login, email, password) values (1, 'test', 'test@example.com', SHA2('test_password', 256));
insert into login (id, login, email, password) values (2, 'Dostya', 'dostya@cybran.example.com', SHA2('vodka', 256));
insert into login (id, login, email, password) values (3, 'Rhiza', 'rhiza@aeon.example.com', SHA2('puff_the_magic_dragon', 256));

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
insert into version_lobby (id, `file`, version) values (1, 'some-installer.msi', '0.10.125');

-- Sample maps
delete from map;
insert into map (id, display_name, map_type, battle_type, author)
values
(1, 'SCMP_001', 'FFA', 'skirmish', 1),
(2, 'SCMP_002', 'FFA', 'skirmish', 1),
(3, 'SCMP_003', 'FFA', 'skirmish', 1),
(4, 'SCMP_004', 'FFA', 'skirmish', 1),
(5, 'SCMP_005', 'FFA', 'skirmish', 1),
(6, 'SCMP_006', 'FFA', 'skirmish', 2),
(7, 'SCMP_007', 'FFA', 'skirmish', 2),
(8, 'SCMP_008', 'FFA', 'skirmish', 2),
(9, 'SCMP_009', 'FFA', 'skirmish', 2),
(10, 'SCMP_010', 'FFA', 'skirmish', 3),
(11, 'SCMP_011', 'FFA', 'skirmish', 3),
(12, 'SCMP_012', 'FFA', 'skirmish', 3),
(13, 'SCMP_013', 'FFA', 'skirmish', 3),
(14, 'SCMP_014', 'FFA', 'skirmish', 3),
(15, 'SCMP_015', 'FFA', 'skirmish', 3);

delete from map_version;
insert into map_version (description, max_players, width, height, version, filename, hidden, map_id)
values
('SCMP 001', 8, 5, 5, 1, 'maps/scmp_001.v0001.zip', 0, 1),
('SCMP 002', 8, 5, 5, 1, 'maps/scmp_002.v0001.zip', 0, 2),
('SCMP 003', 8, 5, 5, 1, 'maps/scmp_003.v0001.zip', 0, 3),
('SCMP 004', 8, 5, 5, 1, 'maps/scmp_004.v0001.zip', 0, 4),
('SCMP 005', 8, 5, 5, 1, 'maps/scmp_005.v0001.zip', 0, 5),
('SCMP 006', 8, 5, 5, 1, 'maps/scmp_006.v0001.zip', 0, 6),
('SCMP 007', 8, 5, 5, 1, 'maps/scmp_007.v0001.zip', 0, 7),
('SCMP 008', 8, 5, 5, 1, 'maps/scmp_008.v0001.zip', 0, 8),
('SCMP 009', 8, 5, 5, 1, 'maps/scmp_009.v0001.zip', 0, 9),
('SCMP 010', 8, 5, 5, 1, 'maps/scmp_010.v0001.zip', 0, 10),
('SCMP 011', 8, 5, 5, 1, 'maps/scmp_011.v0001.zip', 0, 11),
('SCMP 012', 8, 5, 5, 1, 'maps/scmp_012.v0001.zip', 0, 12),
('SCMP 013', 8, 5, 5, 1, 'maps/scmp_013.v0001.zip', 0, 13),
('SCMP 014', 8, 5, 5, 1, 'maps/scmp_014.v0001.zip', 0, 14),
('SCMP 015', 8, 5, 5, 1, 'maps/scmp_015.v0001.zip', 0, 15),
('SCMP 015', 8, 5, 5, 2, 'maps/scmp_015.v0002.zip', 0, 15),
('SCMP 015', 8, 10, 10, 3, 'maps/scmp_015.v0003.zip', 0, 15);

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

-- sample mods
delete from table_mod;
insert into table_mod (uid, `name`,
                       version, author, ui, description, filename, icon, likers, played)
VALUES ('foo', 'test-mod', 1, 'baz', 0, NOW(), 'foobar.zip', 'foobar.png', '', 0),
       ('bar', 'test-mod2', 1, 'baz', 0, NOW(), 'foobar2.zip', 'foobar2.png', '', 0),
       ('EA040F8E-857A-4566-9879-0D37420A5B9D', 'test-mod3', 1, 'baz', 0, NOW(), 'foobar3.zip', 'foobar3.png', '', 1);

-- sample avatars
delete from avatars;
delete from avatars_list;
insert into avatars_list (id, url, tooltip) values (1, "http://content.faforever.com/faf/avatars/qai2.png", "QAI");
insert into avatars (idUser, idAvatar, selected) values (2, 1, 0);
