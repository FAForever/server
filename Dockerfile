FROM python:3.4.3

ENTRYPOINT ["faf-server"]

RUN apt-get update

RUN yes '' | apt-get install libqt4-dev

RUN pip install --upgrade pip

COPY requirements.txt /tmp/requirements.txt

RUN pip install --trusted-host content.dev.faforever.com -r /tmp/requirements.txt

COPY . /tmp/

COPY passwords.py.example /tmp/passwords.py

WORKDIR /tmp/

RUN pip install -e .

RUN py.test
