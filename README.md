# FA Forever - Server

This is the source code for the [Forged Alliance Forever](http://www.faforever.com/) server.

master|develop
 ------------ | -------------
[![Build Status](https://travis-ci.org/FAForever/server.svg?branch=master)](https://travis-ci.org/FAForever/server) | [![Build Status](https://travis-ci.org/FAForever/server.svg?branch=develop)](https://travis-ci.org/FAForever/server)
[![Coverage Status](https://coveralls.io/repos/FAForever/server/badge.png?branch=master)](https://coveralls.io/r/FAForever/server?branch=master) | [![Coverage Status](https://coveralls.io/repos/FAForever/server/badge.png?branch=develop)](https://coveralls.io/r/FAForever/server?branch=develop)
[![Scrutinizer Code Quality](https://scrutinizer-ci.com/g/FAForever/server/badges/quality-score.png?b=master)](https://scrutinizer-ci.com/g/FAForever/server/?branch=master) | [![Scrutinizer Code Quality](https://scrutinizer-ci.com/g/FAForever/server/badges/quality-score.png?b=develop)](https://scrutinizer-ci.com/g/FAForever/server/?branch=develop)

## Installation

Install [docker](https://www.docker.com).

Follow the steps to get [faf-db](https://github.com/FAForever/db) setup, the following assumes the db container is called `faf-db`.

    docker build -t faf/server .
    docker run --link faf-db:db -p 8001:8001 -p 30351:30351 faf/server

## Running the tests

Run `py.test`

    docker run --link faf-db:db faf/server bash -c py.test

# Contributing

To contribute, please fork this repository and make pull requests to the develop branch.

Use the normal git conventions for commit messages, with the following rules:
 - Subject line shorter than 80 characters
 - Proper capitalized sentence as subject line, with no trailing period
 - For non-trivial commits, always include a commit message body, describing the change in detail
 - If there are related issues, reference them in the commit message footer


# License

GPLv3. See the [license](license.txt) file.

# Network Protocol

The protocol is mainly JSON-encoded maps, containing at minimum a `command` key, representing the command to dispatch.

The wire format uses [QDataStream](http://doc.qt.io/qt-5/qdatastream.html) (UTF-16, BigEndian).

For the lobbyconnection, each message is of the form:

    ACTION: QString

With most carrying a footer containing:

    LOGIN: QString
    SESSION: QString
    
## Message types

There are three types of messages:

  1. A **request** is always initiated by the client and sent to the server 
  1. A **response** is always preceded by a request and is sent from the server to the client
  1. A **push** is always initiated by the server and sent to the client
  

## Session initiation

#### Request

    {
        "command": "ask_session"
    }

#### Response

    {
        "command": "session",
        "session": long
    }

| Parameter | Value | Description              |
|-----------|-------|--------------------------|
| `session` | long  | The assigned session ID. |






## Login

#### Request

Sends a login request.

**TODO*** (Downlord:) I guess `local_ip` is not needed?
**TODO*** (Downlord:) `username` instead of `login`? 
**TODO*** (Downlord:) `password` plaintext in future? 

    {
        "login": string,
        "password": string,
        "session": long,
        "unique_id": string,
        "local_ip": string
    }

| Parameter   | Value  | Description                                                                                |
|-------------|--------|--------------------------------------------------------------------------------------------|
| `login`     | string | The username to log in.                                                                    |
| `password`  | string | The SHA-256 hashed password.                                                               |
| `session`   | long   | The ID of the current session.                                                             |
| `unique_id` | string | The UUID generated by `uid.dll`                                                            |
| `local_ip`  | string | The IP address of the local machine.<br/> *__Deprecated__: this may be removed in future*  |

#### Response

##### On success

**TODO*** (Downlord:) `login` seems pretty useless; the client should know what we logged in with.

    {
        "command": "session",
        "login": string,
        "id": int
    }

| Parameter   | Value   | Description                                                                   |
|-------------|---------|-------------------------------------------------------------------------------|
| `login`     | string  | The logged-in username.<br/> *__Deprecated__: this may be removed in future*  |
| `id`        | integer | The current user's ID.                                                        |

##### On failure

    {
        "command": "authentication_failed",
        "text": string
    }

| Parameter   | Value  | Description     |
|-------------|--------|-----------------|
| `text`      | string | The error text. |





## Initial player list

#### Push

**TODO*** (Downlord:) `username` instead of `login`?

Informs the client about players that are currently logged in.

    {
      "command": "player_info",
      "players": [
        {
          "id": int,
          "login": string,
          "number_of_games": integer,
          "country": string,
          "clan": string,
          "global_rating": {
            "mean": float,
            "deviation": float
          },
          "ladder_rating": {
            "mean": float,
            "deviation": float
          },
          "avatar": {
            "url": string,
            "tooltip": string
          }
        }
      ]
    }

| Parameter                      | Value   | Description                                                                                                                     |
|--------------------------------|-------- |---------------------------------------------------------------------------------------------------------------------------------|
| `players[]`                    | list    | The list of players.                                                                                                            |
| `players[].id`                 | integer | The ID of the player.                                                                                                           |
| `players[].login`              | string  | The username of the player.                                                                                                     |
| `players[].number_of_games`    | integer | The number of games this player has played.                                                                                     |
| `players[].country`            | string  | The two-letter [GeoIP ISO 3166](http://dev.maxmind.com/geoip/legacy/codes/iso3166/) country code of the player.                 |
| `players[].clan`               | string  | The acronym of the clan of the player.                                                                                          |
| `players[].global_rating`      | object  | The global rating of the player as an array with two values. The player rank to display can be calculated as `μ - 3σ`.          |
| `players[].global_rating.mean` | float   | The mean (`μ`) value of the rating.                                                                                             |
| `players[].global_rating.dev`  | float   | The deviation (`σ`) value of the rating.                                                                                        |
| `players[].ladder_rating`      | object  | The 1v1 leaderboard rating of the player as an array with two values. The player rank to display can be calculated as `μ - 3σ`. |
| `players[].global_rating.mean` | float   | The mean (`μ`) value of the rating.                                                                                             |
| `players[].global_rating.dev`  | float   | The deviation (`σ`) value of the rating.                                                                                        |
| `players[].avatar`             | object  | The avatar object of the player.                                                                                                |
| `players[].avatar.url`         | string  | The avatar image URL (40px * 20px).                                                                                             |
| `players[].avatar.tooltip`     | string  | The avatar tooltip text.                                                                                                        |






## Social

**TODO*** (Downlord:) Would it make sense to merge this into the login response?
**TODO*** (Downlord:) `channels` and `autojoin` seem redundant.

#### Push

    {
      "power": integer,
      "autojoin": [
        string
      ],
      "foes": [
        integer
      ],
      "command": string,
      "channels": [
        string
      ],
      "friends": [
        integer
      ]
    }

| Parameter    | Value  | Description                                        |
|--------------|--------|----------------------------------------------------|
| `power`      | string | The administrative power given to the user.        |
| `autojoin[]` | list   | A list of chat channels (`string`) to join.        |
| `foes`       | list   | A list of player IDs (`integer`) that are foes.    |
| `friends`    | list   | A list of player IDs (`integer`) that are friends. |
| `channels[]` | list   | A list of chat channels (`string`) to join.        |






## Hosting game

**TODO*** (Downlord:) Would it make sense to merge this into the login response?
**TODO*** (Downlord:) `channels` and `autojoin` seem redundant.

#### Request

    {
      "command": "game_host",
      "gameport": integer,
      "mapname": string,
      "title": string,
      "mod": string,
      "access": string,
      "visibility": string
    }

| Parameter    | Type    | Description                                                                          |
|--------------|---------|--------------------------------------------------------------------------------------|
| `gameport`   | map     | The technical name of the map.                                                       |
| `mapname`    | string  | The technical name of the map.                                                       |
| `title`      | integer | The title of the game.                                                               |
| `mod`        | integer | The name of the active game modification.                                            |
| `access`     | integer | The accessability of the game, one of `["public", "private"]`. TODO is this correct? |
| `visibility` | string  | The visibility of the game, one of `["public", "private"]`. TODO is this correct?    |

#### Response

**TODO*** (Downlord:) `id` instead of `uid` (and/or: use real UUIDs)

    {
      "args": [
        string
      ],
      "mod": "faf",
      "command": "game_launch",
      "uid": 4088550
    }

| Parameter | Type    | Description                                                                |
|-----------|---------|----------------------------------------------------------------------------|
| `args`    | array   | Additional command line arguments(`string`) to use when starting the game. |
| `mod`     | string  | The name of the game modification to host.                                 |
| `uid`     | integer | The ID of the game.                                                        |







## Game information

**TODO*** (Downlord:) `id` instead of `uid` (and/or: use real UUIDs)
**TODO*** (Downlord:) `mod` instead of `featured_mod`?
**TODO*** (Downlord:) `victory_condition` instead of `game_type` (and string instead of int)?
**TODO*** (Downlord:) Team for observers is `"null"`.

#### Push

    {
      "command": "game_info",
      "featured_mod_versions": {
        string: integer
      },
      "featured_mod": string,
      "state": string,
      "game_type": 0,
      "num_players": 0,
      "visibility": null,
      "teams": {
        string: [
          string
        ]
      },
      "title": "test",
      "sim_mods": [],
      "mapname": string,
      "password_protected": false,
      "options": [],
      "max_players": integer,
      "uid": integer,
      "host": string
    }

| Parameter               | Type    | Description                                                                                                         |
|-------------------------|---------|---------------------------------------------------------------------------------------------------------------------|
| `featured_mod_versions` | map     | Map of some (`string`) to a version (`integer`)                                                                     |
| `featured_mod`          | string  | The name of the active game modification.                                                                           |
| `state`                 | integer | The ID of the game.                                                                                                 |
| `game_type`             | integer | The victory condition. 0: Demoraliztation, 1: Domination, 2: Eradication, 3: Sandbox.                               |
| `num_players`           | integer | The current number of players in the game, including observers. (TODO is that correct?)                             |
| `visibility`            | string  | The visibility of the game, one of `["public", "private"]`.                                                         |
| `teams`                 | map     | Map of team name (`string`) to a list of user names (`string`). Currently, the team name for observers is `"null"`. |
| `title`                 | string  | The title of the game.                                                                                              |
| `sim_mods`              | array   | TODO currently an empty array?                                                                                      |
| `mapname`               | string  | The technical name of the map.                                                                                      |
| `password_protected`    | boolean | Whether or not the game is password protected.                                                                      |
| `max_players`           | integer | The maximum number of players allowed (depends on the map).                                                         |
| `uid`                   | integer | The ID of the game.                                                                                                 |
| `host`                  | string  | The username of the hosting player.                                                                                 |


