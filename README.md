# FA Forever - Server
![python](https://img.shields.io/badge/python-3.7-blue)
[![Build Status](https://travis-ci.org/FAForever/server.svg?branch=develop)](https://travis-ci.org/FAForever/server)
[![Coveralls Status](https://img.shields.io/coveralls/FAForever/server/develop.svg)](https://coveralls.io/github/FAForever/server)
[![semver](https://img.shields.io/badge/license-GPLv3-blue)](license.txt)

This is the source code for the
[Forged Alliance Forever](https://www.faforever.com/) lobby server.

## Support development

Post a bounty on Issue Hunt. You can reward and financially help developers who
work on your issue.

[![Issue hunt](https://github.com/BoostIO/issuehunt-materials/raw/master/v1/issuehunt-button-v1.svg?sanitize=true)](https://issuehunt.io/r/FAForever/server)

# Contributing

Before opening a pull request, please take a moment to look over the
[contributing guidelines](CONTRIBUTING.md).

## Setting up for development

First, follow the instructions on the [faf-db repo](https://github.com/FAForever/db)
to setup an instance of the database. Then install the pinned versions of the
dependencies (and dev dependencies) to a virtual environment using pipenv by
running:

    $ pipenv sync --dev

You can then start the server in development mode with:

    $ pipenv run devserver

You will probably see a number of errors and warnings show up in the log which
is completely normal for a development setup. If you see any of the following,
they can be safely ignored:

    WARNING  Twilio is not set up. You must set TWILIO_ACCOUNT_SID and TWILIO_TOKEN to use the Twilio ICE servers.
    WARNING  GEO_IP_LICENSE_KEY not set! Unable to download GeoIP database!
    WARNING  Unable to connect to RabbitMQ. Is it running?
    ConnectionError: [Errno 111] Connect call failed ('127.0.0.1', 5672)
    WARNING  Not connected to RabbitMQ, unable to declare exchange.
    ERROR    Failure updating NickServ password for test

**Note:** *The pipenv scripts are NOT meant for production deployment. For
deployment use `faf-stack`.*

### Administrator/root privileges

On Linux, root privileges are generally not needed. If you find that a command
will not work unless run as root, it probably means that you have a file
permission issue that you should fix. For instance if you ran the server as a
docker container, it may have created certain files (like the GeoIP database) as
root, and you should `chown` them or delete them before running the unit tests
or the devserver.

On Windows you may also find that some issues go away when running as
administrator. This may be because you have set up your tools to install for the
whole system instead of just the current user. For example if you have issues
with pipenv you can try installing it with the `--user` option:

    $ pip install --user pipenv

## Running the tests

The unit tests are written using [pytest](https://docs.pytest.org/en/latest) and
can be run through the pipenv shortcut:

    $ pipenv run tests

Any arguments passed to the shortcut will be forwarded to pytest, so the usual
pytest options can be used for test selection. For instance, to run all unit
tests containing the keyword "ladder":

    $ pipenv run tests tests/unit_tests -k ladder

If you are running `pytest` by some other means (e.g. with PyCharm) you may need
to provide the database configuration as command line arguments:

    --mysql_host=MYSQL_HOST
                          mysql host to use for test database
    --mysql_username=MYSQL_USERNAME
                          mysql username to use for test database
    --mysql_password=MYSQL_PASSWORD
                          mysql password to use for test database
    --mysql_database=MYSQL_DATABASE
                          mysql database to use for tests
    --mysql_port=MYSQL_PORT
                          mysql port to use for tests

For further information on available command line arguments run `pytest --help`
or see the official
[pytest documentation](https://docs.pytest.org/en/latest/usage.html).

There are also some integration tests which simulate real traffic to the test
server.

    $ pipenv run integration

Some of them may fail depending on the configuration deployed on the test
server.

## Other tools

You can check for possible unused code with `vulture` by running:

    $ pipenv run vulture

It tends to produce a lot of false positives, but it can provide a good place
to start.

## Building with Docker

The recommended way to deploy the server is with
[faf-stack](https://github.com/FAForever/faf-stack). However, you can also
build the docker image manually.

Follow the steps to get [faf-db](https://github.com/FAForever/db) setup, the
following assumes the db container is called `faf-db` and the database is called
`faf` and the root password is `banana`.

Then use Docker to build and run the server as follows

    $ docker build -t faf-server .
    $ docker run --link faf-db:db -p 8001:8001 -d faf-server

Check if the container is running with

    $ docker ps

If you cannot find `faf-server` in the list, run `docker run` without `-d` to
see what happens.

### Configuration

If you have for example a different root password or database name than the default
`DB_PASSWORD` and `DB_NAME` entries in
[config.py](https://github.com/FAForever/server/blob/develop/server/config.py),
you should provide a custom configuration file.
This file will be used for all variables that it defines
while the default values of `config.py` still apply for those it doesn't.
To use your custom configuration file, pass its location as an environment
variable to docker:

    $ docker run --link faf-db:db -p 8001:8001 -e CONFIGURATION_FILE=<path> faf-server

You can find an example configuration file under
[tests/data/test_conf.yaml](https://github.com/FAForever/server/blob/develop/tests/data/test_conf.yaml).

# Network Protocol

The protocol is mainly JSON-encoded maps, containing at minimum a `command` key,
representing the command to dispatch.

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

#### Parties
* `{command: invite_to_party, recipient_id: <...>}`: Invite this player to a party
* `{command: accept_party_invite, sender_id: <...>}`: Accept the party invite from the given player
* `{command: kick_player_from_party, kicked_player_id: <...>}`: Kick a player from a party you own
* `{command: leave_party}`: Leave the party you are currently in

##### Misc

* [deprecated] `{command: ask_session}`: response with a welcome command and a valid session (can be delayed)
* `{command: hello, version: <...>, login: <...>, password: <...>, unique_id: <...>, (session: <...>)}`: Log in to the server

##  Stream (Deprecated)

The stream API is deprecated, but currently the following message types are supported:

* `PING`: response with a `PONG`
* `PONG`: internal state changed to ponged
