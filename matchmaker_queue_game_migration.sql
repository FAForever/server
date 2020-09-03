DROP TABLE IF EXISTS matchmaker_queue_game;

CREATE TABLE matchmaker_queue_game
(
  id                  INT(10) UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
  matchmaker_queue_id INT(10) UNSIGNED NOT NULL,
  game_stats_id       INT(10) UNSIGNED NOT NULL,
  FOREIGN KEY (matchmaker_queue_id) REFERENCES matchmaker_queue (id),
  FOREIGN KEY (game_stats_id) REFERENCES game_stats (id),
  UNIQUE INDEX (game_stats_id, matchmaker_queue_id)
);
