#!/usr/bin/env bash

MAX_WAIT=60 # max. 1 minute waiting time in loop before timeout
RABBITMQ_PID_FILE=/var/lib/rabbitmq/pid

RABBITMQ_LOBBYSERVER_USER=faf-python-server
RABBITMQ_LOBBYSERVER_PASS=banana
RABBITMQ_LOBBYSERVER_VHOST=/faf-core

# Create RabbitMQ users
docker exec faf-rabbitmq rabbitmqctl wait --timeout ${MAX_WAIT} "${RABBITMQ_PID_FILE}"

docker exec faf-rabbitmq rabbitmqctl add_vhost "${RABBITMQ_LOBBYSERVER_VHOST}"
docker exec faf-rabbitmq rabbitmqctl add_user "${RABBITMQ_LOBBYSERVER_USER}" "${RABBITMQ_LOBBYSERVER_PASS}"
docker exec faf-rabbitmq rabbitmqctl set_permissions -p "${RABBITMQ_LOBBYSERVER_VHOST}" "${RABBITMQ_LOBBYSERVER_USER}" ".*" ".*" ".*"
