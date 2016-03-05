FROM python:3.5

# Apt-install mysql client and cleanup temporary files afterwards
RUN apt-get update
RUN yes '' | apt-get install mysql-client
RUN apt-get clean
RUN rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

RUN mkdir /python
WORKDIR /python
RUN git clone https://github.com/python/cpython.git .
RUN git checkout 3.5
RUN ./configure
RUN make
RUN make install
RUN python3.5 -m ensurepip
RUN python3.5 -m pip install --upgrade pip

COPY requirements.txt /tmp/requirements.txt

RUN python3.5 -m pip install --trusted-host content.dev.faforever.com -r /tmp/requirements.txt

ADD . /code/

RUN mkdir /var/log/faforever

WORKDIR /code/

RUN python3.5 -m pip install -e .

# Shared volume for logs
VOLUME ["/code/logs"]

# Main entrypoint and the default command that will be run
CMD ["./server.py"]

# Game server runs on 8000/tcp, lobby server runs on 8001/tcp, nat echo server runs on 30351/udp
EXPOSE 8000 8001 30351

RUN python3.5 -V
