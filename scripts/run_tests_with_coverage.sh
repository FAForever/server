#!/usr/bin/env bash
set -e
mypy server.py
py.test --cov-report term-missing --cov=server --mysql_database=faf -r w
