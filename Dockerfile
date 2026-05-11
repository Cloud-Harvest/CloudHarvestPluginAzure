FROM python:3.14-trixie as python

WORKDIR /src

ENV PIP_ROOT_USER_ACTION=ignore

COPY . .

RUN pip install setuptools \
    && python -m pip install . \
    && pytest tests/

ENTRYPOINT /bin/bash
