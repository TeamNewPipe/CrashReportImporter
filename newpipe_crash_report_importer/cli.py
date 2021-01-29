import asyncio
import os
from datetime import datetime, timedelta

import click
import sentry_sdk

from . import (
    DatabaseEntry,
    DirectoryStorage,
    GlitchtipStorage,
    GlitchtipError,
    LmtpController,
    CrashReportHandler,
    Message,
    make_logger,
    configure_logging,
)


configure_logging()
logger = make_logger("cli")


@click.group()
def cli():
    """
    Placeholder. Allows integration the subcommands.
    """
    pass


@cli.command()
@click.option("--host", type=str, default="::1")
@click.option("--port", type=int, default=8025)
def serve(host, port):
    # report errors in the importer to GlitchTip, too
    sentry_sdk.init(dsn=os.environ["OWN_DSN"])

    # initialize storages
    directory_storage = DirectoryStorage("mails")

    newpipe_dsn = os.environ["NEWPIPE_DSN"]
    newpipe_legacy_dsn = os.environ["NEWPIPE_LEGACY_DSN"]

    sentry_storage = GlitchtipStorage(newpipe_dsn, "org.schabi.newpipe")
    legacy_storage = GlitchtipStorage(newpipe_legacy_dsn, "org.schabi.newpipelegacy")

    # define handler code as closure
    # TODO: this is not very elegant, should be refactored
    async def handle_received_mail(message: Message):
        logger.info(f"Handling mail")

        try:
            entry = DatabaseEntry(message)
        except Exception as e:
            logger.info("Error while parsing the message: %s" % repr(e))
            return

        if entry.date.timestamp() > datetime.now().timestamp():
            logger.info("Exception occured in the future... How could that happen?")
            return

        await directory_storage.save(entry)

        package = entry.newpipe_exception_info["package"]

        try:
            if package == "org.schabi.newpipe":
                await sentry_storage.save(entry)
            elif package == "org.schabi.newpipelegacy":
                await legacy_storage.save(entry)
            else:
                raise RuntimeError("Unknown package: " + package)

        except GlitchtipError as e:
            logger.error("Failed to store error in GlitchTip: %s", e)

    # set up LMTP server
    controller = LmtpController(
        CrashReportHandler(handle_received_mail),
        enable_SMTPUTF8=True,
        hostname=host,
        port=port,
    )
    controller.start()
    logger.info(f"server listening on {controller.hostname}:{controller.port}")

    # run server forever
    asyncio.get_event_loop().run_forever()


if __name__ == "__main__":
    cli()
