import traceback
from email.parser import Parser

import sentry_sdk
from aiosmtpd.controller import Controller
from aiosmtpd.lmtp import LMTP
from aiosmtpd.smtp import Envelope

from . import make_logger


class LmtpController(Controller):
    """
    A custom controller implementation, return LMTP instances instead of SMTP ones.
    Inspired by GNU Mailman 3"s LMTPController.
    """

    def factory(self):
        return LMTP(self.handler, ident="NewPipe crash report importer")


class CrashReportHandler:
    """
    Very simple handler which only accepts mail for allowed addresses and stores them into the Sentry database.
    """

    def __init__(self, callback: callable):
        self.callback = callback

        self.logger = make_logger("lmtp_handler")

    async def handle_LHLO(self, *args):
        # it seems like the LMTP server will always call the HELO handler when it sees an LHLO, but for good measures,
        # we'll rather implement this handler, too, to not miss it when they change it in the future
        self.logger.warning("handle_LHLO called")
        return self.handle_HELO(*args)

    async def handle_HELO(self, server, session, envelope, hostname):
        # the only reason this callback exists is so there is some *compact* logging of new connections
        # it's not really all that robust (as the connection is made before the HELO call is made already), but it's
        # the only less invasive choice for implementing this kind of logging outside aiosmtpd.SMTP.
        # see https://github.com/aio-libs/aiosmtpd/issues/239 for more information
        # it's a really poor solution, though, as disconnects are also not tracked
        peer = f"{session.peer[0]}:{session.peer[1]}"
        self.logger.info(f"Client connected: {peer} ({hostname})")

        # these lines have been copied over from aiosmtpd/smtp.py, and are required to make things work
        # it's a bit unfortunate that there's no Handler class one can derive from that implements these default
        # reactions, so one could call them with a super().handle_HELO(...) call
        session.host_name = hostname
        return "250 {}".format(server.hostname)

    async def handle_RCPT(
        self, server, session, envelope: Envelope, address: str, rcpt_options
    ):
        if address not in ["crashreport@newpipe.net", "crashreport@newpipe.schabi.org"]:
            return f"550 not handling mail for address {address}"

        envelope.rcpt_tos.append(address)
        return "250 OK"

    @staticmethod
    def convert_to_rfc822_message(envelope: Envelope):
        return Parser().parsestr(envelope.content.decode())

    async def handle_DATA(self, server, session, envelope: Envelope):
        try:
            message = self.convert_to_rfc822_message(envelope)

            # as the volume of incoming mails is relatively low (< 3 per minute usually) and reporting doesn't take
            # very long, we can just do it here and don't require some message queue/worker setup
            # the callback is defined as async, but can, due to the low volume, be implemented synchronously, too
            await self.callback(message)

        except:
            # in case an exception happens in the callback (e.g., the message can't be parsed correctly), we don't
            # want to notify the sending MTA, but have them report success of delivery
            # it's after all not their problem: if they got so far, the message was indeed delivered to our LMTP server
            # however, we want the exception to show up in the log
            traceback.print_exc()

            # also, we want to report all kinds of issues to GlitchTip
            sentry_sdk.capture_exception()

        # make sure all control flow paths return a string reply!
        return "250 Message accepted for delivery"
