# FA Forever - Server

This is the source code for the [Forged Alliance Forever](http://www.faforever.com/) server.

master|develop
 ------------ | -------------
[![Build Status](https://travis-ci.org/FAForever/server.svg?branch=master)](https://travis-ci.org/FAForever/server) | [![Build Status](https://travis-ci.org/FAForever/server.svg?branch=develop)](https://travis-ci.org/FAForever/server)
[![Coveralls Status](https://img.shields.io/coveralls/FAForever/server/master.svg)](https://coveralls.io/github/FAForever/server) | [![Coveralls Status](https://img.shields.io/coveralls/FAForever/server/develop.svg)](https://coveralls.io/github/FAForever/server)

## Installation

Install [docker](https://www.docker.com).

Follow the steps to get [faf-db](https://github.com/FAForever/db) setup, the following assumes the db container is called `faf-db` and the database is called `faf` and the root password is `banana`.


The server needs an RSA key to decode uniqueid messages, we've provided an example key in the repo as `faf-server.example.pem`. The server expects this to be named `faf-server.pem` at runtime, so first copy this

    cp faf-server.example.pem faf-server.pem

Then use Docker to build and run the server as follows

    docker build -t faf-server .
    docker run --link faf-db:db -p 8001:8001 -p 30351:30351 faf-server

Check if the container is running with

    docker ps

If you cannot find `faf-server` in the list, run `docker run` without `-d` to see what happens.

If you have a different root password or database name than the default
`DB_PASSWORD` and `DB_NAME` entries in
[config.py](https://github.com/FAForever/server/blob/develop/server/config.py),
you should provide a custom configuration file.
This file will be used for all variables that it defines
while the default values of `config.py` still apply for those it doesn't.
To use your custom configuration file, pass its location as an environment
variable to docker:

    docker run --link faf-db:db -p 8001:8001 -p 30351:30351 -e CONFIGURATION_FILE=<path> faf-server

# Contributing

To contribute, please fork this repository and make pull requests to the develop branch.

Use the normal git conventions for commit messages, with the following rules:
 - Subject line shorter than 80 characters
 - Proper capitalized sentence as subject line, with no trailing period
 - For non-trivial commits, always include a commit message body, describing the change in detail
 - If there are related issues, reference them in the commit message footer

## Setting up for development

First make sure you have an instance of `faf-db` running as described in the
installation section. Then install the dependencies to a virtual environment
using pipenv:

    $ pipenv install --dev

You can start the server in development mode with:

    $ pipenv run devserver

**Note** *The pipenv scripts are not meant for production deployment. For
deployment use `faf-stack`*

## Running the tests

Run

    $ pipenv run tests

(or `sudo pipenv run tests`, 
if some tests error with `Permission denied`)
## Other tools

You can check for possible unused code with `vulture` by running:

    $ pipenv run vulture

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

## Incoming Packages

##### Mod Vault

* `{command: modvault, type: start}`: show the last 100 mods
* `{command: modvault, type: like, uid: <uid>}`: check if user liked the mod, otherwise increase the like counter
* `{command: modvault, type: download, uid: <uid>}`: notify server about a download (for download counter), does not start the download

##### Social
* `{command: social_add, friend|foe: <player_id>}`: Add a friend or foe
* `{command: social_remove, friend|foe: <player_id>}`: Remove a friend or foe

##### Avatar
* `{command: avatar, action: list_avatar}`: Send a list of available avatars
* `{command: avatar, action: select, avatar: <avatar_url>}`: Select a valid avatar for the player

##### ICE Servers

* `{command: ice_servers}`: Send ICE TURN/STUN servers - Returns: `{command: ice_servers, : <ice servers>, date_created: <date token was created in ISO 8601 format>, ttl: <ttl in seconds>}`

##### Misc

* [deprecated] `{command: ask_session}`: response with a welcome command and a valid session (can be delayed)
* `{command: hello, version: <...>, login: <...>, password: <...>, unique_id: <...>, (session: <...>)}`: Log in to the server

##  Stream (Deprecated)

The stream API is deprecated, but currently the following message types are supported:

* `PING`: response with a `PONG`
* `PONG`: internal state changed to ponged
