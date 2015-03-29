# FA Forever - Server

This is the source code for the [Forged Alliance Forever](http://www.faforever.com/) server.

master|develop
 ------------ | -------------
[![Build Status](https://travis-ci.org/FAForever/server.svg?branch=master)](https://travis-ci.org/FAForever/server) | [![Build Status](https://travis-ci.org/FAForever/server.svg?branch=develop)](https://travis-ci.org/FAForever/server)
[![Coverage Status](https://coveralls.io/repos/FAForever/server/badge.png?branch=master)](https://coveralls.io/r/FAForever/server?branch=master) | [![Coverage Status](https://coveralls.io/repos/FAForever/server/badge.png?branch=develop)](https://coveralls.io/r/FAForever/server?branch=develop)


## Installation - Automatic

To setup the development environment automatic we use Vagrant and a VM.

1. Install Vagrant: http://www.vagrantup.com/downloads
2. Install VirtualBox: https://www.virtualbox.org/wiki/Downloads
3. Clone this repository
4. Open the command console and navigate to folder of this repository (check with `ls` or `dir` that `Vagrantfile` is present)
5. Run `vagrant up`

To login the vm use `vagrant ssh`.
To shutdown the vm use `vagrant halt`.
You find the data under `/vagrant` in the VM.
This folder is autmatically synced from host to guest and back.

## Installation - Manual

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

Set the `QUAMASH_QTIMPL` environment variable to `PySide`.

    export QUAMASH_QTIMPL=PySide

Also create the `passwords.py` file. This can be done by executing `.travis.sh`.

    bash .travis.sh

Use `py.test` to execute the unit tests.

# License

GPLv3. See the [license](license.txt) file.

# Network Protocol

WIP: JSON Protocol Overview based on [QStreamData](http://doc.qt.io/qt-5/qdatastream.html) (UTF-16, BigEndian)

## Incoming Packages

###### Mod Vault

* `{command: modvault, type: start}`
* `{command: modvault, type: like, uid: <uid>}`