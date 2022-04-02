# Development
This document outlines how to set up the project for development in extensive
detail.

*Only developing on Linux is officially supported, but people have gotten the
project to build on Windows using the WSL.*

## System dependencies
You will need the following software installed on your system:
-   [Docker](https://docs.docker.com/engine/)
-   [Docker Compose](https://github.com/docker/compose)
-   [Python 3.9](https://www.python.org/downloads/)
-   [Pipenv](https://github.com/pypa/pipenv/)

Once you have Docker installed, make sure to add yourself to the `docker` group
so that you can run docker commands without `sudo`. You will need to relogin
for the changes to take effect.
```
$ sudo usermod -aG docker <user>
```

It's very likely that the right version of Python may not be available in your
distro's package repositories. In this case you will need to install from
source. Make sure that you compile with the
`--enable-loadable-sqlite-extensions` flag otherwise some of the dependencies
will not work.

```
$ ./configure --enable-loadable-sqlite-extensions
```

There are a number of steps to compiling Python from source so make sure to
look up a guide if you haven't done it before.

Once you have Pipenv installed, you might want to enable the 'movable' virtual
environment option that will put your virtual environment into the traditional
`.venv` directory of the project. Just add the following line to your `.bashrc`
and reload your terminal:
```
export PIPENV_VENV_IN_PROJECT=1
```

## Application Dependencies
The lobby server needs the FAF MySQL database for storing persistent state.
Follow the instructions on the [faf-db repo](https://github.com/FAForever/db)
to setup an instance of the database.

If the database version defined in
[`.github/workflows/test.yml`](.github/workflows/test.yml) does not match
the one defined in your `docker-compose.yml`, you will need to update the
compose file and then re-run the migrations.

Find the section in `docker-compose.yml` that looks like this and change the
version number to the required version in
[`.github/workflows/test.yml`](.github/workflows/test.yml).
```
faf-db-migrations:
  container_name: faf-db-migrations
  image: faforever/faf-db-migrations:<version tag>
```

Then run the migrations with the following command.
```
$ docker-compose run faf-db-migrations migrate
```

Install the pinned versions of the dependencies (and dev dependencies) to a
virtual environment using pipenv by running:
```
$ pipenv sync --dev
```

## Running the development server
Once you have installed all the application dependencies including the FAF
database, you can start the server in development mode with:
```
$ pipenv run devserver
```

You will probably see a number of errors and warnings show up in the log which
is completely normal for a development setup. If you see any of the following,
they can be safely ignored:

```
WARNING  Twilio is not set up. You must set TWILIO_ACCOUNT_SID and TWILIO_TOKEN to use the Twilio ICE servers.
WARNING  GEO_IP_LICENSE_KEY not set! Unable to download GeoIP database!
WARNING  Unable to connect to RabbitMQ. Is it running?
ConnectionError: [Errno 111] Connect call failed ('127.0.0.1', 5672)
WARNING  Not connected to RabbitMQ, unable to declare exchange.
ERROR    Failure updating NickServ password for test
```

**Note:** *The pipenv scripts are NOT meant for production deployment. For
deployment use [faf-stack](https://github.com/FAForever/faf-stack).*

## Running the tests

The unit tests are written using [pytest](https://docs.pytest.org/en/latest) and
can be run through the pipenv shortcut:
```
$ pipenv run tests
```
Any arguments passed to the shortcut will be forwarded to pytest, so the usual
pytest options can be used for test selection. For instance, to run all unit
tests containing the keyword "ladder":
```
$ pipenv run tests tests/unit_tests -k ladder
```

If you are running `pytest` by some other means (e.g. with PyCharm) you may need
to provide the database configuration as command line arguments:
```
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
```

For further information on available command line arguments run `pytest --help`
or see the official
[pytest documentation](https://docs.pytest.org/en/latest/usage.html).

There are also some integration tests which simulate real traffic to the test
server.
```
$ pipenv run integration
```

Some of them may fail depending on the configuration deployed on the test
server.

## Other tools

There are some pre-commit hooks that can fix basic formatting issues for you
to make the review process go smoother. You can install them by running:
```
$ python3 -m pip install pre-commit
$ pre-commit install
```

(optional) Run against all the files (usually `pre-commit` will only run on the
changed files during git hooks):
```
$ pre-commit run --all-files
```

You can check for possible unused code with `vulture` by running:
```
$ pipenv run vulture
```

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
```
$ docker build -t faf-server .
$ docker run --link faf-db:db -p 8001:8001 -d faf-server
```

Check if the container is running with
```
$ docker ps
```

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
```
$ docker run --link faf-db:db -p 8001:8001 -e CONFIGURATION_FILE=<path> faf-server
```

You can find an example configuration file under
[tests/data/test_conf.yaml](https://github.com/FAForever/server/blob/develop/tests/data/test_conf.yaml).

## Administrator/root privileges

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
```
$ pip install --user pipenv
```
