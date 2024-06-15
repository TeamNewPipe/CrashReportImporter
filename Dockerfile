FROM python:3.9-slim

# we want to run the server with an unprivileged user
RUN addgroup --gid 101 web && \
    adduser --system --group --uid 101 web

# set up mount for directory storage
RUN install -o web -d /app/mails
VOLUME /app/mails

WORKDIR /app/

# LMTP server port
EXPOSE 8025

# when not using poetry to install the dependencies, we need to make the sources available for this step already
COPY pyproject.toml poetry.lock /app/
COPY newpipe_crash_report_importer/ /app/newpipe_crash_report_importer/
RUN pip install -U -e .

USER web

# finally, configure the server command
CMD python -m newpipe_crash_report_importer --force-colors=true serve --host 0.0.0.0 --port 8025
