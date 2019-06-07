# FA Forever - Server

This is the source code for the [Forged Alliance Forever](http://www.faforever.com/) server.

master|develop
 ------------ | -------------
[![Build Status](https://travis-ci.org/FAForever/server.svg?branch=master)](https://travis-ci.org/FAForever/server) | [![Build Status](https://travis-ci.org/FAForever/server.svg?branch=develop)](https://travis-ci.org/FAForever/server)
[![Coveralls Status](https://img.shields.io/coveralls/FAForever/server/master.svg)](https://coveralls.io/github/FAForever/server) | [![Coveralls Status](https://img.shields.io/coveralls/FAForever/server/develop.svg)](https://coveralls.io/github/FAForever/server)
[![Scrutinizer Code Quality](https://scrutinizer-ci.com/g/FAForever/server/badges/quality-score.png?b=master)](https://scrutinizer-ci.com/g/FAForever/server/?branch=master) | [![Scrutinizer Code Quality](https://scrutinizer-ci.com/g/FAForever/server/badges/quality-score.png?b=develop)](https://scrutinizer-ci.com/g/FAForever/server/?branch=develop)

## Installation

Install [docker](https://www.docker.com).

Follow the steps to get [faf-db](https://github.com/FAForever/db) setup, the following assumes the db container is called `faf-db` and the database is called `faf` and the root password ist `banana`.


The server needs an RSA key to decode uniqueid messages, we've provided an example key in the repo as `faf-server.example.pem`. The server expects this to be named `faf-server.pem` at runtime, so first copy this

    cp faf-server.example.pem faf-server.pem

Then use Docker to build and run the server as follows

    docker build -t faf-server .
    docker run --link faf-db:db -p 8001:8001 -p 30351:30351 faf-server

Check if the container is running with

    docker ps

If you cannot find `faf-server`in the list, run `docker run` without `-d` to see what happen.

If you have a different root password, database name then the default (see [config.py](https://github.com/FAForever/server/blob/develop/server/config.py#L43)), you must pass it over the environment parameter of docker, e.g.

    docker run --link faf-db:db -p 8001:8001 -p 30351:30351 -e FAF_DB_PASSWORD=<wanted_password> -e FAF_DB_NAME=<db_name> faf-server

## Running the tests

Some of the tests require the database to be pre-populated with test data. Download
the latest `test-data.sql` from [FAForever/db](https://github.com/FAForever/db
into the root of this project, then run:

    $ pipenv run tests

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

With a few message-types (`UPLOAD_MOD`, `UPLOAD_MAP`), there are more fields.

## Incoming Packages

##### Mod Vault

* `{command: modvault, type: start}`: show the last 100 mods
* `{command: modvault, type: like, uid: <uid>}`: check if user liked the mod, otherwise increase the like counter
* `{command: modvault, type: download, uid: <uid>}`: notify server about an download (for download counter), does not start the download
* `{command: modvault, type: addcomment}`: not implemented

##### Social
Can be combined !, e.g. `{command: social, teaminvite: <...>, friends: <..>}`
* `{command: social, teaminvite: <player_name>}`: Invite a Player to a Team
* `{command: social, friends: <list of ALL friends>}`: Update the friends on the db
* `{command: social, foes: <list of ALL foes>}`: Update the foe (muted players) on the db

##### Avatar
* `{command: avatar, action: upload_avatar, name: <avatar_name>, file: <file_content>, description: <desc>}`: Admin Command to upload an avatar
* `{command: avatar, action: list_avatar}`: Send a list of available avatars
* `{command: avatar, action: select, avatar: <avatar_url>}`: Select a valid avatar for the player

##### ICE Servers

* `{command: ice_servers}`: Send ICE TURN/STUN servers - Returns: `{command: ice_servers, : <ice servers>, date_created: <date token was created in ISO 8601 format>, ttl: <ttl in seconds>}`

##### Misc

* [deprecated] `{command: ask_session}`: response with an welcome command and an valid session (can be delayed)
* `{command: fa_state, state: <on|...>}`: notify the server if the game has launched or closed
* `{command: quit_team}`: Leave a team
* `{command: accept_team_proposal, leader: <leader_name>}`: Accept Team Invitation
* `{command: hello, version: <...>, login: <...>, password: <...>, unique_id: <...>, (session: <...>)}`: Accept Team Invitation

##  Stream

The stream API is deprecated, but currently the following message types are supported:

* `PING`: response with a `PONG`
* `PONG`: internal state changed to ponged
* `UPLOAD_MOD, login, session, zipmap, infos, size, fileDaatas`: Upload a mod
* `UPLOAD_MAP, login, session, zipmap, infos, size, fileDatas`: Upload a map
