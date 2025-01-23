import json
from datetime import datetime
from email.utils import parsedate_to_datetime
from hashlib import sha256

from .message import Message


class DatabaseEntry:
    def __init__(self, rfc822_message):
        self.message = Message(rfc822_message)

        # from is just needed for calculating the SHA256 hash below
        self.from_ = rfc822_message["from"]
        self.to = rfc822_message["to"]

        self.plaintext = self.message.plaintext
        self.newpipe_exception_info = self.message.embedded_json

        try:
            self.date = datetime.fromisoformat(self.newpipe_exception_info["time"])
        except ValueError:
            try:
                # try to use the date given by the crash report
                self.date = datetime.strptime(
                    self.newpipe_exception_info["time"], "%Y-%m-%d %H:%M"
                )
                if self.date.year < 2010:
                    raise ValueError()
            except ValueError:
                # try to use the date from the mail header
                self.date = parsedate_to_datetime(rfc822_message["date"])
                if self.date.year < 2010:
                    self.date = self.message.date_from_received_headers()

    def to_dict(self):
        # we don't store the From header, as it's not needed for potential re-imports of the database, but could be
        # used to identify the senders after a long time
        # in fact, senders weren't stored in the production system either, but this never got committed to the
        # repository... D'oh!
        return {
            "to": self.to,
            "timestamp": int(self.date.timestamp()),
            "plaintext": self.plaintext,
            "newpipe-exception-info": self.newpipe_exception_info,
        }

    def hash_id(self):
        hash = sha256((str(self.from_) + str(self.to)).encode())
        hash.update(self.date.strftime("%Y%m%d%H%M%S").encode())
        return hash.hexdigest()

    def __hash__(self):
        return hash((self.from_, self.to, self.date))
