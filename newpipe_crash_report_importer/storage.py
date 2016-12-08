import bleach
import html
import json
import os
import raven.conf.remote
import re
import requests
import string
import unicodedata
from datetime import datetime
from email.utils import parsedate_to_datetime
from hashlib import sha256


class ParserError(Exception):
    pass


class StorageError(Exception):
    pass


class NoPlaintextMessageFoundError(Exception):
    pass


class Message:
    """
    Represents an incoming mail fetched from the IMAP server.
    """

    possible_charsets = [
        "ascii",
        "utf-8",
        "windows-1252",
    ]

    def __init__(self, rfc822_message):
        self.rfc822_message = rfc822_message
        self. plaintext_or_html_part = self.get_plaintext_or_html_part()
        payload = self.plaintext_or_html_part.get_payload(decode=True)

        for charset in self.possible_charsets:
            try:
                decoded_payload = payload.decode(charset)
            except UnicodeDecodeError:
                continue
            else:
                break
        else:
            raise ParserError("Could not decode message payload")

        self.plaintext = self.sanitize_message(decoded_payload)
        self.embedded_json = self.extract_json_from_string(self.plaintext)

    def get_plaintext_or_html_part(self):
        """
        Searches for the first part in the multipart RFC822 message whose
        content type is text/plain or text/html.

        :return: The part or None
        :rtype: class:`email.message.Message`
        """
        for part in self.rfc822_message.walk():
            if part.get_content_type() in ("text/plain", "text/html"):
                return part
        else:
            return None

    @staticmethod
    def sanitize_message(original_data):
        normalized = unicodedata.normalize("NFKD", original_data)
        decoded = html.unescape(normalized)
        sanitized = bleach.clean(decoded,
                                 tags=[], attributes={}, styles=[], strip=True)
        return unicodedata.normalize("NFKD", sanitized)

    @staticmethod
    def extract_json_from_string(json_string):
        """
        Attemt to fix all the shit "intelligent" mail clients do to the plain
        # text data NewPipe gives them.
        Although it's a really BAD idea to sanitize untrusted data, we'll give it
        a try - as long as there's no bugs in the JSON parser, it should be safe
        to do this.
        """

        match = re.search("({.*})", json_string, re.MULTILINE + re.DOTALL)

        if match:
            try:
                data = match.group(1)
                data = unicodedata.normalize("NFKD", data)
                return json.loads(data, strict=False)
            except json.JSONDecodeError:
                raise ParserError("Could not parse JSON in given data")
        else:
            raise ParserError("Could not find JSON in given data")


    def date_from_received_headers(self):
        headers = self.rfc822_message.get_all("received")
        header = None

        for _h in headers:
            for domain in ["mail.orange-it.de", "mail.commandnotfound.org"]:
                if "by %s (Dovecot) with LMTP id" % domain in _h:
                    break
            else:
                continue
            header = _h
            break

        date = parsedate_to_datetime(header.split(";")[-1].strip())

        return date


class DatabaseEntry:
    def __init__(self, rfc822_message):
        self.message = Message(rfc822_message)

        self.from_ = rfc822_message["from"]
        self.to = rfc822_message["to"]

        self.plaintext = self.message.plaintext
        self.newpipe_exception_info = self.message.embedded_json

        try:
            # try to use the date given by the crash report
            self.date = datetime.strptime(self.newpipe_exception_info["time"],
                                          "%Y-%m-%d %H:%M")
            if self.date.year < 2010:
                raise ValueError()
        except ValueError:
            # try to use the date from the mail header
            self.date = parsedate_to_datetime(rfc822_message["date"])
            if self.date.year < 2010:
                self.date = self.message.date_from_received_headers()
                print(self.date)

    def to_dict(self):
        return {
            "from": self.from_,
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


class Storage:
    """
    Storage base class.
    """

    def save(self, entry: DatabaseEntry):
        return NotImplemented


class DirectoryStorage(Storage):
    """
    Local storage implementation. Puts every database entry in a file named
    by their hash ID in a directory.
    """

    def __init__(self, directory: str):
        self.directory = os.path.abspath(directory)
        os.makedirs(self.directory, exist_ok=True)

    def save(self, entry: DatabaseEntry):
        message_id = entry.hash_id() + ".json"
        path = os.path.join(self.directory, message_id)
        if not os.path.isfile(path):
            with open(path, "w") as f:
                json.dump(entry.to_dict(), f, indent=2)
        else:
            print("\nEntry already stored in directory -> skipped")


class SentryStorage(Storage):
    """
    Used to store incoming mails on a Sentry server.
    https://docs.sentry.io

    Remembers already sent mail reports by putting their hash IDs in a file
    in the application's root directory.
    """

    def __init__(self, dsn: str):
        self.dsn = raven.conf.remote.RemoteConfig.from_string(dsn)
        valid_chars = string.ascii_letters + string.digits
        self.db_fname = "".join(filter(lambda s: s in valid_chars,
                                       self.dsn.store_endpoint)) + \
                        ".stored.txt"

    @staticmethod
    def make_sentry_exception(entry: DatabaseEntry):
        newpipe_exc_info = entry.newpipe_exception_info

        frames = []
        try:
            raw_data = "".join(newpipe_exc_info["exceptions"])
        except KeyError:
            raise StorageError("'exceptions' key missing in JSON body")
        raw_frames = raw_data.replace("\n", " ").replace("\r", " ").split("\tat")

        message = raw_frames[0]

        for frame in raw_frames[1:]:
            expr = "([a-zA-Z0-9\.]+)\(([a-zA-Z0-9:\.\s]+)\)"
            frame_match = re.search(expr, frame)

            if frame_match:
                module_path = frame_match.group(1).split(".")

                if ":" in frame_match.group(2):
                    expr = "([a-zA-Z]+\.java+):([0-9]+)"
                    filename_and_lineno = re.search(expr, frame_match.group(2))

                    frame_dict = {
                        "package": ".".join(module_path[:-1]),
                        "function": module_path[-1],
                        "filename": filename_and_lineno.group(1),
                        "lineno": filename_and_lineno.group(2),
                    }

                else:
                    frame_dict = {
                        "module": ".".join(module_path[:-1]),
                        "function": module_path[-1],
                        "filename": frame_match.group(2),
                    }

                frame_dict["in_app"] = True
                frames.append(frame_dict)

            else:
                raise ParserError("Could not parse frame: '{}'".format(frame))

        try:
            type = message.split(":")[0].split(".")[-1]
            value = message.split(":")[1]
            module = ".".join(message.split(":")[0].split(".")[:-1])
        except IndexError:
            type = value = module = "<none>"

        timestamp = entry.date.timestamp()

        rv = {
            "message": message,
            "stacktrace": {
                "type": type,
                "value": value,
                "module": module,
                "frames": frames,
            },
            "extra": {
                "user_comment": None,
                "request": None,
                "ip_range": None,
                "user_action": None,
            },
            "timestamp": timestamp,
            "tags": {
                "os": None,
                "service": None,
                "content_language": None,
            },
            "level": "error",
        }

        try:
            rv["release"] = newpipe_exc_info["version"]
        except KeyError:
            pass

        for key in ["user_comment", "request", "ip_range", "user_action"]:
            try:
                rv["extra"][key] = newpipe_exc_info[key]
            except KeyError:
                pass

        for key in ["os", "service", "content_language"]:
            try:
                rv["tags"][key] = newpipe_exc_info[key]
            except KeyError:
                pass

        return rv

    def save(self, entry: DatabaseEntry):
        try:
            with open(self.db_fname, "r") as f:
                entry_ids = f.read().splitlines()
        except OSError:
            print("\nCould not open list of entries already sent to Sentry!")
            entry_ids = []

        entry_id = entry.hash_id()

        if entry_id in entry_ids:
            print("\nMail has been sent to Sentry already -> skipped")
            return

        data = self.make_sentry_exception(entry)

        auth_header = """
        Sentry sentry_version=5,
          sentry_client=newpipe-mail-reporter_0.0.1,
          sentry_key={pubkey},
          sentry_secret={privkey}
        """.replace("\n", "").format(
            timestamp=str(entry.date.timestamp()),
            pubkey=self.dsn.public_key,
            privkey=self.dsn.secret_key
        ).strip()

        request = requests.Request("POST",
                                   self.dsn.store_endpoint,
                                   headers={"X-Sentry-Auth": auth_header},
                                   data=json.dumps(data))
        response = requests.Session().send(request.prepare())
        response.raise_for_status()

        with open(self.db_fname, "a") as f:
            f.write(entry_id + "\n")
