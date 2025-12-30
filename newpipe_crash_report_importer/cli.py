import asyncio
import functools
import os
from datetime import datetime
from smtplib import LMTP

import click
import sentry_sdk
from sentry_sdk.integrations.asyncio import AsyncioIntegration

from newpipe_crash_report_importer.lmtp_server import CustomLMTP
from . import (
    DatabaseEntry,
    DirectoryStorage,
    GlitchtipStorage,
    GlitchtipError,
    AlreadyStoredError,
    CrashReportHandler,
    Message,
    make_logger,
    configure_logging,
)


logger = make_logger("cli")


class UnknownPackageError(RuntimeError):
    pass


@click.group()
@click.option("--force-colors", type=bool, default=False)
def cli(force_colors):
    """
    Placeholder. Allows integration the subcommands.
    """

    configure_logging(force_colors=force_colors)


@cli.command()
@click.option("--host", type=str, default="::1")
@click.option("--port", type=int, default=8025)
def serve(host, port):
    # report errors in the importer to GlitchTip, too
    own_dsn = os.environ["OWN_DSN"]
    print(f"Reporting own errors to Sentry DSN {own_dsn}")
    sentry_sdk.init(
        dsn=own_dsn,
        debug=os.environ.get("DEBUG_SENTRY_SDK", False),
        integrations=[
            AsyncioIntegration()
        ],
    )

    # initialize storages
    directory_storage = DirectoryStorage("mails")

    newpipe_dsn = os.environ["NEWPIPE_DSN"]
    newpipe_nightly_dsn = os.environ["NEWPIPE_NIGHTLY_DSN"]
    newpipe_refactor_nightly_dsn = os.environ["NEWPIPE_REFACTOR_NIGHTLY_DSN"]
    newpipe_legacy_dsn = os.environ["NEWPIPE_LEGACY_DSN"]

    sentry_storage = GlitchtipStorage(newpipe_dsn, "org.schabi.newpipe")
    nightly_storage = GlitchtipStorage(newpipe_nightly_dsn, "org.schabi.newpipe.nightly")
    refactor_nightly_storage = GlitchtipStorage(
        newpipe_refactor_nightly_dsn, "org.schabi.newpipe.refactor.nightly"
    )
    legacy_storage = GlitchtipStorage(newpipe_legacy_dsn, "org.schabi.newpipelegacy")

    # define handler code as closure
    # TODO: this is not very elegant, should be refactored
    async def handle_received_mail(message: Message):
        logger.info(f"Handling mail")

        try:
            entry = DatabaseEntry(message)
        except:
            logger.exception("Error while parsing the message")
            return

        logger.info(f"Entry date: {entry.date}")

        if entry.date.timestamp() > datetime.now().timestamp():
            logger.error("Exception occurred in the future... How could that happen?")
            return

        try:
            await directory_storage.save(entry)
        except AlreadyStoredError:
            logger.warning("Already stored in directory storage, skipping")

        package = entry.newpipe_exception_info["package"]

        try:
            if package == "org.schabi.newpipe":
                await sentry_storage.save(entry)
            elif package == "org.schabi.newpipe.nightly":
                await nightly_storage.save(entry)
            elif package == "org.schabi.newpipe.refactor.nightly":
                await refactor_nightly_storage.save(entry)
            elif package == "org.schabi.newpipelegacy":
                await legacy_storage.save(entry)
            else:
                raise UnknownPackageError("Unknown package: " + package)

        except AlreadyStoredError:
            logger.warning("Already stored in GlitchTip storage, skipping")

        except GlitchtipError as e:
            logger.error("Failed to store error in GlitchTip: %s", e)

    handler = CrashReportHandler(handle_received_mail)

    loop = asyncio.new_event_loop()

    loop.run_until_complete(
        loop.create_server(
            functools.partial(
                CustomLMTP,
                handler,
                ident="NewPipe crash report importer",
                enable_SMTPUTF8=True,
            ),
            host=host,
            port=port,
        )
    )

    logger.info(f"server listening on {host}:{port}")

    loop.run_forever()


# note that import is a protected keyword, so we have to specify the command name explicitly
@cli.command("import")
@click.argument("filenames", type=click.Path(exists=True), nargs=-1)
@click.option("--host", type=str, default="::1")
@click.option("--port", type=int, default=8025)
def import_rfc822(filenames, host, port):
    logger.info(f"Connecting to LMTP server {host}:{port}")
    client = LMTP(host=host, port=port)

    for filename in filenames:
        try:
            with open(filename) as f:
                data = f.read()
        except UnicodeDecodeError:
            logger.exception("Failed to decode mail contents, skipping")

        try:
            logger.info(f"Importing RFC822 e-mail file {filename}")
            client.sendmail("a@b.cde", ["crashreport@newpipe.net"], data)

        except KeyboardInterrupt:
            logger.error("SIGINT received, exiting")
            return 1

        except:
            logger.exception("Error while trying to import RFC822 e-mail")


if __name__ == "__main__":
    cli()
