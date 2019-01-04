FROM python:3.6-alpine

# Apt-install and cleanup temporary files afterwards
# openssl-dev for pycrypto
# lua5.1-dev for lupa
RUN apk update && \
    apk add \
        mysql-client \
        git vim bash \
        g++ musl-dev libffi-dev openssl-dev lua5.1-dev

COPY requirements.txt /tmp/requirements.txt

RUN python3 -m pip install -r /tmp/requirements.txt

ADD . /code/
WORKDIR /code/

RUN python3 -m pip install -e .

# Main entrypoint and the default command that will be run
CMD ["/usr/local/bin/python3.6", "server.py"]

# Game server runs on 8000/tcp, lobby server runs on 8001/tcp, nat echo server runs on 30351/udp
EXPOSE 8000 8001 30351

RUN python3 -V
