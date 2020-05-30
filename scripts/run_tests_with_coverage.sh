#!/usr/bin/env bash
set -e
pytest --flake8 --cov-report term-missing --cov=server --mysql_database=faf -o testpaths=tests "$@"
