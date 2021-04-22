FROM python:3.9-alpine

# we want to run the server with an unprivileged user
RUN adduser -S web

# install build dependencies
RUN apk add --no-cache gcc g++ make musl-dev libffi-dev openssl-dev rust cargo && \
    python3 -m pip install -U poetry

# set up mount for directory storage
RUN install -o web -d /app/mails
VOLUME /app/mails

WORKDIR /app/
USER web

# setting up the port now, as it'll hardly ever change
# doing this before the rest of the commands will speed up building the image a bit
EXPOSE 8025

# the Python dependencies hardly ever change (and it takes quite some time), so we install them first
# this way, we don't have to reinstall them when we only have some code changes
COPY pyproject.toml poetry.lock /app/
RUN poetry install

# next, we copy the source code
COPY newpipe_crash_report_importer/ /app/newpipe_crash_report_importer/

# finally, configure the server command
CMD poetry run python -m newpipe_crash_report_importer --force-colors=true serve --host 0.0.0.0 --port 8025
