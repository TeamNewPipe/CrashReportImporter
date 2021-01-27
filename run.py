"""
NewPipe Crash Report Importer
=============================

Parses crash reports received via e-mail and stores them on a sentry instance
and in a local directory.

See README.md for more information.
"""

import asyncio
import os
from datetime import datetime, timedelta

import sentry_sdk

from newpipe_crash_report_importer import (
    DatabaseEntry,
    DirectoryStorage,
    GlitchtipStorage,
    LmtpController,
    CrashReportHandler,
    Message,
)


if __name__ == "__main__":
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
        print(f"Handling mail")

        try:
            entry = DatabaseEntry(message)
        except Exception as e:
            print("Error while parsing the message: %s" % repr(e))
            return

        if (
            entry.date.timestamp()
            < (datetime.now() - timedelta(days=29, hours=23)).timestamp()
        ):
            print("Exception older than 29 days and 23 hours, discarding...")
            return

        if entry.date.timestamp() > datetime.now().timestamp():
            print("Exception occured in the future... How could that happen?")
            return

        await directory_storage.save(entry)

        package = entry.newpipe_exception_info["package"]

        if package == "org.schabi.newpipe":
            await sentry_storage.save(entry)
        elif package == "org.schabi.newpipelegacy":
            await legacy_storage.save(entry)
        else:
            raise RuntimeError("Unknown package: " + package)

    # set up LMTP server
    controller = LmtpController(
        CrashReportHandler(handle_received_mail), enable_SMTPUTF8=True
    )
    controller.start()
    print(controller.hostname, controller.port)

    # run server forever
    asyncio.get_event_loop().run_forever()
