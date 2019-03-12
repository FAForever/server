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

delete from matchmaker_ban;
insert into matchmaker_ban (id, userid) values (102, 102);
