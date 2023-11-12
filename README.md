# FA Forever - Server
![Build Status](https://github.com/FAForever/server/actions/workflows/test.yml/badge.svg?branch=develop)
[![codecov](https://codecov.io/gh/FAForever/server/branch/develop/graph/badge.svg?token=55ndgNQdUv)](https://codecov.io/gh/FAForever/server)
[![Codacy Badge](https://app.codacy.com/project/badge/Grade/ada42f6e09a341a88f3dae262a43e86e)](https://www.codacy.com/gh/FAForever/server/dashboard?utm_source=github.com&amp;utm_medium=referral&amp;utm_content=FAForever/server&amp;utm_campaign=Badge_Grade)
[![docs](https://img.shields.io/badge/docs-latest-purple)](https://faforever.github.io/server/)
[![license](https://img.shields.io/badge/license-GPLv3-blue)](license.txt)
![python](https://img.shields.io/badge/python-3.10-3776AB)

This is the source code for the
[Forged Alliance Forever](https://www.faforever.com/) lobby server.

## Overview
The lobby server is the piece of software sitting at the very core of FAF,
enabling players to discover and play games with each other. It is a stateful
TCP server written in `asyncio` and implements a custom TCP protocol for
communicating with [clients](https://github.com/FAForever/downlords-faf-client).
The main responsibilities of the lobby server are:
-   To manage the lifecycle of joining games

    *(Note that Forged Alliance uses a distributed peer-to-peer networking model,
    so the simulation happens entirely on the player's machines, and **NOT** on
    any server)*

-   To facilitate initial connection establishment when players join a game

-   To maintain a list of online players

-   To perform rating calculations and updates

## Support development

Post a bounty on Issue Hunt. You can reward and financially help developers who
work on your issue.

[![Issue hunt](https://github.com/BoostIO/issuehunt-materials/raw/master/v1/issuehunt-button-v1.svg?sanitize=true)](https://issuehunt.io/r/FAForever/server)

## Major Software Dependencies

The lobby server integrates with a few external services and has been tested
with the following versions:

-   MariaDB 10.6
-   (optional) RabbitMQ 3.9

# Contributing

Before opening a pull request, please take a moment to look over the
[contributing guidelines](CONTRIBUTING.md).

## Setting up for development
For detailed instructions see the [development guide](DEVELOPMENT.md).

### Quickstart
*This section assumes you have the necessary system dependencies installed. For
a list of what those are see the [development guide](DEVELOPMENT.md).*

1.  Start up an instance of the FAF database. This is required to run the unit tests
and development server.
```
$ git clone https://github.com/FAForever/faf-stack.git
$ cd faf-stack
$ ./scripts/init-db.sh
```

2.  Install the project dependencies with pipenv
```
$ pipenv sync --dev
```

3.  Run the unit tests or development server
```
$ pipenv run tests
$ pipenv run devserver
```

# Network Protocol
**NOTE: This section of the README is outdated. The QString based message
format has been deprectaed and will be replaced by a UTF-8 json + newline
format in version 2. Many commands are missing from here. For a more complete
list see [https://faforever.github.io/server/](https://faforever.github.io/server/).**

The protocol is mainly JSON-encoded maps, containing at minimum a `command` key,
representing the command to dispatch.

The wire format uses [QDataStream](http://doc.qt.io/qt-5/qdatastream.html) (UTF-16, BigEndian).

For the lobbyconnection, each message is of the form:
```
ACTION: QString
```
With most carrying a footer containing:
```
LOGIN: QString
SESSION: QString
```

## Incoming Packages

##### Mod Vault

-   (deprecated) `{command: modvault, type: start}`: show the last 100 mods
-   (deprecated) `{command: modvault, type: like, uid: <uid>}`: check if user liked the mod, otherwise increase the like counter
-   (deprecated) `{command: modvault, type: download, uid: <uid>}`: notify server about a download (for download counter), does not start the download

##### Social
-   `{command: social_add, friend|foe: <player_id>}`: Add a friend or foe
-   `{command: social_remove, friend|foe: <player_id>}`: Remove a friend or foe

##### Avatar
-   `{command: avatar, action: list_avatar}`: Send a list of available avatars
-   `{command: avatar, action: select, avatar: <avatar_url>}`: Select a valid avatar for the player

##### ICE Servers

-   (deprecated) `{command: ice_servers}`: Send ICE TURN/STUN servers - Returns: `{command: ice_servers, : <ice servers>, date_created: <date token was created in ISO 8601 format>, ttl: <ttl in seconds>}`

#### Parties
-   `{command: invite_to_party, recipient_id: <...>}`: Invite this player to a party
-   `{command: accept_party_invite, sender_id: <...>}`: Accept the party invite from the given player
-   `{command: kick_player_from_party, kicked_player_id: <...>}`: Kick a player from a party you own
-   `{command: leave_party}`: Leave the party you are currently in

##### Misc

-   (deprecated) `{command: ask_session}`: response with a welcome command and a valid session (can be delayed)
-   `{command: hello, version: <...>, login: <...>, password: <...>, unique_id: <...>, (session: <...>)}`: Log in to the server

##  Stream (Deprecated)

The stream API is deprecated, but currently the following message types are supported:

-   `PING`: response with a `PONG`
-   `PONG`: internal state changed to ponged
