FROM python:3.4.3

RUN apt-get update

RUN yes '' | apt-get install libqt4-dev mysql-client

RUN pip install --upgrade pip

COPY requirements.txt /tmp/requirements.txt

RUN pip install --trusted-host content.dev.faforever.com -r /tmp/requirements.txt

ADD . /code/

COPY passwords.example.py /code/passwords.py

WORKDIR /code/

RUN pip install -e .

VOLUME ["/code/logs"]

CMD ["./server.py"]
