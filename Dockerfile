###############
# Build image #
###############
FROM python:3.10-slim as builder

# Need git for installing aiomysql
RUN apt-get update
RUN apt-get install -y --no-install-recommends git

RUN pip install pipenv==2023.4.20

WORKDIR /code/

# Copy dependency files first so we only reinstall when these are changed
COPY Pipfile Pipfile.lock /code/

RUN PIPENV_VENV_IN_PROJECT=1 pipenv sync

COPY . /code/
RUN PIPENV_VENV_IN_PROJECT=1 pipenv run pip install .

#################
# Runtime image #
#################
FROM python:3.10-slim

ARG GITHUB_REF
ENV VERSION=$GITHUB_REF

RUN useradd --no-create-home faf

COPY --from=builder /code/.venv/lib/ /usr/local/lib/
COPY --from=builder --chown=faf:faf /code/main.py /code/

WORKDIR /code/
USER faf

# Main entrypoint and the default command that will be run
CMD ["/usr/local/bin/python3", "main.py"]

# lobby server runs on 8001/tcp (QDataStream) and 8002/tcp (JSON)
EXPOSE 8001 8002

RUN python3 -V
