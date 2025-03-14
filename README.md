# FA Forever - Server
![Build Status](https://github.com/FAForever/server/actions/workflows/test.yml/badge.svg?branch=develop)
[![codecov](https://codecov.io/gh/FAForever/server/branch/develop/graph/badge.svg?token=55ndgNQdUv)](https://codecov.io/gh/FAForever/server)
[![Codacy Badge](https://app.codacy.com/project/badge/Grade/ada42f6e09a341a88f3dae262a43e86e)](https://www.codacy.com/gh/FAForever/server/dashboard?utm_source=github.com&amp;utm_medium=referral&amp;utm_content=FAForever/server&amp;utm_campaign=Badge_Grade)
[![docs](https://img.shields.io/badge/docs-latest-purple)](https://faforever.github.io/server/)
[![license](https://img.shields.io/badge/license-GPLv3-blue)](license.txt)
![python](https://img.shields.io/badge/python-3.10-3776AB)

This is the source code for the
[Forged Alliance Forever](https://www.faforever.com/) lobby server.
Click here to go to the
[Server Python API Documentation](https://faforever.github.io/server/).

-   For the Lua game mod see
[faforever/fa](https://github.com/FAForever/fa).
-   For the official FAF client see
[faforever/downlords-faf-client](https://github.com/FAForever/downlords-faf-client)

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

In production, the lobby server is deployed behind a websocket bridge
[faforever/ws_bridge_rs](https://github.com/FAForever/ws_bridge_rs).

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

# For Client Developers
The official FAF client code is available at
[faforever/downlords-faf-client](https://github.com/FAForever/downlords-faf-client).
This can be used as a reference when implementing your own custom client.

## Important Notes
In order to avoid having your client break unexpectedly with a new server
release, your server <-> client communication code must adhere to the following
rules:
-   Unrecognized server messages are ignored.
-   Unrecognized fields in messages are ignored.

This ensures that your client continues to function when new features are
implemented on the server side. A new feature might mean that the server will
include a new field in an existing message, or start sending an entirely new
message all together. Such changes are considered to be backwards compatible
additions to the server protocol.

You can read more about the protocol API versioning
[here](CONTRIBUTING.md#version-numbers).

## Server Protocol
There are two layers to the server protocol:
1. **The wire format.**
This is how messages are serialized to bytes and sent over the network stream.

  *NOTE: in production, the client connects to the server via the websocket
  bridge [faforever/ws_bridge_rs](https://github.com/FAForever/ws_bridge_rs)
  rather than connecting directly to the TCP port.*

2. **Application level messages.**
Also sometimes called 'commands', messages are used to exchange state between
the client and server. The client will need to implement appropriate logic for
interpreting each message and reacting to it by sometimes updating UI elements,
internal state, or launching or terminating external processes.

### Wire Format
Each message is serialized to a [JSON](https://www.json.org/) object followed
by an ASCII newline byte (`b"\n"` or `b"\x0a"`). For additional information see
the server API documentation:
[SimpleJsonProtocol](https://faforever.github.io/server/protocol/simple_json.html)

### Application messages
1. **Request / response type commands.**
  Most messages that are sent from the client to the server will be acknowledged
  with a response message. The naming for these messages varies by command. For
  instance the `ask_session` command will respond with a `session` command
  containing the session id.
2. **Asynchronous commands.**
  Many messages are generated by activity of other users, or asynchronous
  processes running on the server. These can generate 'broadcast' messages sent
  out to many connected clients, or direct messages to a specific client without
  being triggered by a request. Generally 'broadcast' messages are name `*_info`
  and are used to synchronize the internal states of the server and client, and
  often signal the need to update some UI elements. For instance the `game_info`
  message sends updated information about a game that can either be in the lobby
  state, be actively playing, or have ended.


Work is ongoing to document these messages in a comprehensive way. For now, all
commands that can be sent from the client -> server can be found via the server
API documentation:
[LobbyConnection](https://faforever.github.io/server/lobbyconnection.html)
under the `command_*` methods. Check the source code for what fields the message
is expected to have and any possible responses.

It may also be useful to look at the definitions in the
[faf-java-commons](https://github.com/FAForever/faf-java-commons/tree/develop/lobby/src/main/kotlin/com/faforever/commons/lobby)
to see how the official client is deserializing messages from the server.

### Deprecations
Some fields or entire message classes may become deprecated and marked for
removal over time. Actual removal is very rare as it can cause potential
breakages of outdated clients. Currently, deprecated fields and messages will
be marked with a `# DEPRECATED` comment in the server code and an explanation of
how to migrate to the new functionality that is replacing the deprecated field
or message.
