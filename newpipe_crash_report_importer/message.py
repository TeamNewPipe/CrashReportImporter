import html
import json
import re
import unicodedata
from email.message import EmailMessage
from email.utils import parsedate_to_datetime

import bleach

from .exceptions import ParserError


class Message:
    """
    Represents an incoming mail fetched from the IMAP server.
    """

    possible_charsets = [
        "ascii",
        "utf-8",
        "windows-1252",
    ]

    def __init__(self, rfc822_message: EmailMessage):
        self.rfc822_message = rfc822_message
        self.plaintext_or_html_part = self.get_plaintext_or_html_part()
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
        sanitized = bleach.clean(decoded, tags=[], attributes={}, strip=True)
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
