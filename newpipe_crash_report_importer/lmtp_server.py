import traceback
from email.parser import Parser

import sentry_sdk
from aiosmtpd.controller import Controller
from aiosmtpd.lmtp import LMTP
from aiosmtpd.smtp import Envelope


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
