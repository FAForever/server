FROM python:3.9-slim

# Need git for installing aiomysql
RUN apt-get update
RUN apt-get install -y --no-install-recommends \
        git && \
    apt-get clean
RUN rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

WORKDIR /code/
COPY Pipfile.lock Pipfile.lock
COPY Pipfile Pipfile

RUN python3 -m pip install pipenv
RUN pipenv install --ignore-pipfile --system --deploy

ADD . /code/

ARG GITHUB_REF
ENV VERSION=$GITHUB_REF
RUN python3 -m pip install -e .

# Main entrypoint and the default command that will be run
CMD ["/usr/local/bin/python3", "server.py"]

# lobby server runs on 8002/tcp (JSON)
EXPOSE 8002

RUN python3 -V
