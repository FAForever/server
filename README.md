# FA Forever - Server

This is the source code for the [Forged Alliance Forever](http://www.faforever.com/) server.

master|develop
 ------------ | -------------
[![Build Status](https://travis-ci.org/FAForever/server.svg?branch=master)](https://travis-ci.org/FAForever/server) | [![Build Status](https://travis-ci.org/FAForever/server.svg?branch=develop)](https://travis-ci.org/FAForever/server)
[![Coverage Status](https://coveralls.io/repos/FAForever/server/badge.png?branch=master)](https://coveralls.io/r/FAForever/server?branch=master) | [![Coverage Status](https://coveralls.io/repos/FAForever/server/badge.png?branch=develop)](https://coveralls.io/r/FAForever/server?branch=develop)


## Installation

Install Python 3.4 or later. Pre-requisites are listed in `requirements.txt`,
install using `pip install -r requirements.txt`.

Instructions for Ubuntu 14.10:

If you do not have pip for python 3 yet, install it.

    sudo apt-get install python3-pip

Then install the dependencies of the repo.

    sudo pip3 install -r requirements.txt
    
Also install PySide

    sudo pip3 install PySide --no-index --find-links=http://content.dev.faforever.com/wheel/

And run the `pyside_postinstall.py` script

    sudo python3 /usr/local/bin/pyside_postinstall.py -install

## Running the tests

Set the `QUAMASH_QTIMPL` environment variable to `PySide`.

    export QUAMASH_QTIMPL=PySide

Also create the `passwords.py` file. This can be done by executing `.travis.sh`.

    bash .travis.sh

Use `py.test` to execute the unit tests.

# License

GPLv1. See the [license](license.txt) file.
