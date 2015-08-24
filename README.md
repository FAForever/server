# FA Forever - Server

This is the source code for the [Forged Alliance Forever](http://www.faforever.com/) server.

master|develop
 ------------ | -------------
[![Build Status](https://travis-ci.org/FAForever/server.svg?branch=master)](https://travis-ci.org/FAForever/server) | [![Build Status](https://travis-ci.org/FAForever/server.svg?branch=develop)](https://travis-ci.org/FAForever/server)
[![Coverage Status](https://coveralls.io/repos/FAForever/server/badge.png?branch=master)](https://coveralls.io/r/FAForever/server?branch=master) | [![Coverage Status](https://coveralls.io/repos/FAForever/server/badge.png?branch=develop)](https://coveralls.io/r/FAForever/server?branch=develop)
[![Scrutinizer Code Quality](https://scrutinizer-ci.com/g/FAForever/server/badges/quality-score.png?b=master)](https://scrutinizer-ci.com/g/FAForever/server/?branch=master) | [![Scrutinizer Code Quality](https://scrutinizer-ci.com/g/FAForever/server/badges/quality-score.png?b=develop)](https://scrutinizer-ci.com/g/FAForever/server/?branch=develop)

## Installation

Install Python 3.4 or later. Pre-requisites are listed in `requirements.txt`,
install using `pip install -r requirements.txt`.

Instructions for Ubuntu (12 and 14.10):

If you do not have pip for python 3 yet, install it.

    sudo apt-get install python3-pip

Then install the dependencies of the repo.

    sudo pip3 install -r requirements.txt
    
Also install PySide, either from source using pip

    sudo pip3 install PySide

or use the prebuilt wheel distributed by FAF, for use on travis-ci:

    sudo pip3 install PySide --no-index --find-links=http://content.dev.faforever.com/wheel/

If you installed using the wheel, also run the `pyside_postinstall.py` script

    sudo python3 /usr/local/bin/pyside_postinstall.py -install

## Running the tests

Create the `passwords.py` file. This can be done by copying `passwords.py.example`.

    cp passwords.py.example passwords.py

Ensure that the `server` package is importable.

    pip install -e .

Run `py.test`

    py.test tests/

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

##### Misc

* [deprecated] `{command: ask_session}`: response with an welcome command and an valid session (can be delayed)
* `{command: fa_state, state: <on|...>}`: notify the server if the game has launched or closed
* `{command: ladder_maps, maps: <map_ids>}`: select user specific maps for the ladder
* `{command: quit_team}`: Leave a team
* `{command: accept_team_proposal, leader: <leader_name>}`: Accept Team Invitation
* `{command: hello, version: <...>, login: <...>, password: <...>, unique_id: <...>, (session: <...>)}`: Accept Team Invitation

##  Stream

The stream API is deprecated, but currently the following message types are supported:

* `PING`: response with a `PONG`
* `PONG`: internal state changed to ponged
* `UPLOAD_MOD, login, session, zipmap, infos, size, fileDaatas`: Upload a mod
* `UPLOAD_MAP, login, session, zipmap, infos, size, fileDatas`: Upload a map
