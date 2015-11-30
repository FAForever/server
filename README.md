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

## Connectivity

Before the client is able to host/join games, the client must perform a
connection test with the server. This test serves to categorize the peer into one of
three `ConnectivityState` categories:

* `PUBLIC`: The client is capable of receiving UDP messages a priori on the advertised game port
* `STUN`: The client is able to exchange UDP messages after having punched a hole through it's nat
* `PROXY`: The client is incapable of sending/receiving UDP messages

The messages currently mimick the GPGNet protocol, as to remain relatively compatible with the
game, this explains the use of CamelCase in the command names. A client that is `PUBLIC` may choose
to let the game listen directly on the game port for game sessions.

The procedure is initiated by the client, with the following request:

#### TestConnectivity Request

    {
        "command": "InitiateTest",
        "target": "connectivity",
        "port": int
    }

| Parameter  | Value  | Description                           |
|------------|--------|---------------------------------------|
| `port`     | int    | Port number to perform the test using |


Before sending this message, the client must ensure that it is listening for UDP
messages on the given port.

The server will send a UDP packet to the client's address on the requested port, containing the following data:

    \x08Are you public? <user_id>

Where `<user_id>` is the user ID of the signed in user.

On receipt of a UDP packet of the given form, the client must send the following
response:

    {
        "command": "ProcessNatPacket",
        "target": "connectivity",
        "args": [address, message]
    }

| Parameter     | Value     | Description                               |
|---------------|-----------|-------------------------------------------|
| `address`     | string    | The address that the UDP packet came from |
| `message`     | string    | The message that was received             |


If the server doesn't receive the expected response, it will send the following request:

    {
        "command": "SendNatPacket",
        "target": "connectivity",
        "args": [address, message]
    }

The client must form a UDP packet containing `\x08`+message and send it to the given `address`.

When the test is complete, the server will send the following reply:

#### TestConnectivity Response

    {
        "command": "ConnectivityState",
        "target": "connectivity",
        "state": string
    }

| Parameter  | Value             | Description                             |
|------------|-------------------|-----------------------------------------|
| `state`    | ConnectivityState | The determined state, as describe above |


## Hosting a game

Before hosting a game, the client must ensure that it has completed the Connectivity test as described 
above.

#### Request

    {
        "command": "game_host"
        "title": string,
        "gameport": int,
        "mapname": string,
        "password": string,
        "visibility": VisibilityState,
        "relay_address": string
    }

If the connectivity state was STUN or PROXY, the client must include the relay_address parameter.

| Parameter       | Type            | Description                        |
|-----------------|-----------------|------------------------------------|
| `title`         | string          | The wanted title of the game       |
| `gameport`      | int             | The port number to use             |
| `mapname`       | string          | Name of the map                    |
| `password`      | string          | Password                           |
| `visibility`    | VisibilityState | "public" or "friends"              |
| `relay_address` | string          | address of allocated TURN relay    |

On receipt of the request, the server assumes that the client is ready to receive UDP messages
on the advertised game port. It should also be ready to receive GPGNet format messages targeted at "game".

If the client needs to launch the game before it is ready to receive
UDP messages, it is recommended to wait sending this message before the game has launched and is in the
'Idle' state.

#### Response

    {
        "command": "game_launch",
        "mod": string,
        "uid": int
    }

If successful, the server replies with the above command, where `uid` is the associated
ID of the game and `mod` is the featured mod in use.

A series of GPGNet commands targeted at "game" will follow. These are described in the GPGNet section.

## Joining a game

Before joining a game, the client must ensure that it has completed the Connectivity test as described 
above.

#### Request

    {
        "command": "game_join"
        "uid": int,
        "gameport": int,
        "password": string,
        "relay_address": string
    }

If the connectivity state is STUN or PROXY, the client must include the relay_address parameter.

| Parameter       | Type            | Description                        |
|-----------------|-----------------|------------------------------------|
| `uid`           | int             | ID of the game to join             |
| `gameport`      | int             | The port number to use             |
| `password`      | string          | Password                           |
| `relay_address` | string          | address of allocated TURN relay    |

On receipt of the request, the server assumes that the client is ready to receive UDP messages
on the advertised game port. It should also be ready to receive GPGNet format messages targeted at "game".

If the client needs to launch the game before it is ready to receive
UDP messages, it is recommended to wait sending this message before the game has launched and is in the
'Idle' state.

#### Response

    {
        "command": "game_launch",
        "mod": string,
        "uid": int,
        "sim_mods": [string]
    }

| Parameter       | Type            | Description                        |
|-----------------|-----------------|------------------------------------|
| `sim_mods`      | [string]        | List of mod id's in the game       |


If successful, the server replies with the above command, where `uid` is the associated
ID of the game and `mod` is the featured mod in use.

A series of GPGNet commands targeted at "game" will follow. These are described in the GPGNet section.

## GPGNet

The GPGNet protocol is used to control the game itself, report scores, and connection bottlenecks.

All GPGNet messages are of the form:
 
    {
        "command": string, 
        "target": "game",
        "args": [string|int|bool]
    }

