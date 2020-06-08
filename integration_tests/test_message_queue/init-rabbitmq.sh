#!/usr/bin/env bash

MAX_WAIT=60 # max. 1 minute waiting time in loop before timeout

source faf-rabbitmq.env
docker run --rm -d -p 5672:5672 --env-file faf-rabbitmq.env --name faf-rabbitmq-test rabbitmq:3.8.2-management-alpine

# Create RabbitMQ users
docker exec faf-rabbitmq-test rabbitmqctl wait --timeout ${MAX_WAIT} "${RABBITMQ_PID_FILE}"

docker exec faf-rabbitmq-test rabbitmqctl add_vhost "${RABBITMQ_LOBBYSERVER_VHOST}"
docker exec faf-rabbitmq-test rabbitmqctl add_user "${RABBITMQ_LOBBYSERVER_USER}" "${RABBITMQ_LOBBYSERVER_PASS}"
docker exec faf-rabbitmq-test rabbitmqctl set_permissions -p "${RABBITMQ_LOBBYSERVER_VHOST}" "${RABBITMQ_LOBBYSERVER_USER}" ".*" ".*" ".*"
