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

The test is as follows:

* The server will send a UDP packet to the client's address on the requested port, containing the following data:


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

