"""
NewPipe Crash Report Importer
=============================

Parses crash reports received via e-mail and stores them on a sentry instance
and in a local directory.

See README.md for more information.
"""

from datetime import datetime, timedelta
from newpipe_crash_report_importer.mail_client import fetch_messages_from_imap
from newpipe_crash_report_importer.storage import DatabaseEntry, \
    DirectoryStorage, ParserError, SentryStorage, StorageError

if __name__ == "__main__":
    # read e-mail credentials
    with open("mail-credentials.txt") as f:
        lines = [l.strip(" \n") for l in f.readlines()]

    client = fetch_messages_from_imap(*lines[:4])

    directory_storage = DirectoryStorage("mails")

    with open("sentry-dsn.txt") as f:
        sentry_dsn = f.read().strip(" \n\r")

    sentry_storage = SentryStorage(sentry_dsn)

    errors_count = 0
    mails_count = 0

    for i, m in enumerate(client):
        print("\rWriting mail {}".format(i), end="")

        try:
            entry = DatabaseEntry(m)
        except ParserError as e:
            errors_count += 1
            print()
            print("Error while parsing the message: %s" % repr(e))
        else:

            if entry.date.timestamp() < (datetime.now() - timedelta(days=29, hours=23)).timestamp():
                print()
                print("Exception older than 29 days and 23 hours, discarding...")
                continue
            if entry.date.timestamp() > datetime.now().timestamp():
                errors_count += 1
                print()
                print("WOOT THIS EXCEPTION HAS OCCURRED IN THE FUTURE WOOT")
                continue

            try:
                directory_storage.save(entry)
            except (ParserError, StorageError) as e:
                errors_count += 1
                print()
                print("Error while writing the message: %s" % repr(e))

            try:
                sentry_storage.save(entry)
            except (ParserError, StorageError) as e:
                errors_count += 1
                print()
                print("Error while writing the message: %s" % repr(e))

        mails_count = i

    print()
    print("Total message count: %s" % str(mails_count))
    if errors_count > 0:
        print("Total error count: %s" % str(errors_count))
