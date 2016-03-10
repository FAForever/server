#!/usr/bin/env bash
py.test --cov-report term-missing --cov=server
coveralls
