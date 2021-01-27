import hashlib
import re
from typing import List, Union, Optional

import aiohttp
from sentry_sdk.utils import Dsn

from . import Storage
from ..database_entry import DatabaseEntry
from ..exceptions import StorageError, ParserError


class SentryFrame:
    """
    Represents a Sentry stack frame payload.

    Mostly based on a mix of reading the Sentry SDK docs, GlitchTip example data and a lot of trial-and-error.

    Implements the value object pattern.
    """

    def __init__(
        self, filename: str, function: str, package: str, lineno: Optional[int] = None
    ):
        # all the attributes in stack frames are optional

        # in case of NewPipe, we require filename and function and package
        self.filename = filename
        self.function = function
        self.package = package

        # line number is optional, as for builtins (java.*), we don't have any
        self.lineno = lineno

    def to_dict(self):
        # GlitchTip doesn't care if optional data is set to null, so we don't even have to implement checks for that
        rv = {
            "filename": self.filename,
            "function": self.function,
            "package": self.package,
            "lineno": self.lineno,
            # for the sake of simplicity, we just say "every frame belongs to the app"
            "in_app": True,
        }

        return rv


class SentryStacktrace:
    """
    Represents a Sentry stacktrace payload.

    Mostly based on a mix of reading the Sentry SDK docs, GlitchTip example data and a lot of trial-and-error.

    Implements the value object pattern.
    """

    def __init__(self, frames: List[SentryFrame]):
        # the only mandatory element is the stack frames
        # we don't require any register values
        self.frames = frames

    def to_dict(self):
        return {
            "frames": [f.to_dict() for f in self.frames],
        }


class SentryException:
    """
    Represents a Sentry exception payload.

    Mostly based on a mix of reading the Sentry SDK docs, GlitchTip example data and a lot of trial-and-error.

    Implements the value object pattern.
    """

    def __init__(
        self, type: str, value: str, module: str, stacktrace: SentryStacktrace
    ):
        # these are mandatory per the format description
        self.type = type
        # value appears to be the exception's message
        self.value = value

        # the fields module, thread_id, mechanism and stacktrace are optional
        # we send the java package name as module, and a parsed stacktrace via stacktrace
        self.module = module
        self.stacktrace = stacktrace

    def to_json(self) -> dict:
        # format description: https://develop.sentry.dev/sdk/event-payloads/exception/
        return {
            "type": self.type,
            "value": self.value,
            "stacktrace": self.stacktrace.to_dict(),
        }


class SentryPayload:
    """
    Represents a Sentry event payload, sent to the GlitchTip instance.

    Mostly based on a mix of reading the Sentry SDK docs, GlitchTip example data and a lot of trial-and-error.

    This class doesn't strictly implement the value object, as some attributes are optional and can and shall be
    mutated by the caller. The list of attributes initialized below, however, is constant.
    """

    def __init__(
        self,
        event_id: str,
        timestamp: Union[str, int],
        message: str,
        exception: SentryException,
    ):
        # as we calculate hashes anyway for the directory storage, we probably should just use those as IDs here, too
        # this allows cross-referencing events in both storage implementations, which might be important for re-imports
        # of the database
        # first, try to make sure we receive an actual SHA256 hash
        assert len(event_id) == 64

        # this is supposed to be a UUID4 (i.e., random) identifier, hence the limit to 32 characters (without dashes)
        # however, those are SHA256 hashes, which means their hex digests have a length of 64 characters
        # therefore, we derive a 32-character size MD5 hash from the SHA256 one
        self.event_id = hashlib.md5(event_id.encode()).hexdigest()
        assert len(self.event_id) == 32

        # this could either be implemented as a RFC3339 string, or some numeric UNIX epoch style timestamp
        self.timestamp = timestamp

        # will be used as the value for the "formatted" key in the message interface
        self.message = message

        #
        self.exception = exception

        # these are optional attributes according to the format description
        # IIRC, we had to explicitly these to null in order to avoid Sentry from guesstimating their values
        # some of the values may be populated by users after initializing the object
        self.extra = {
            "user_comment": None,
            "request": None,
            "user_action": None,
        }
        self.tags = {
            "os": None,
            "service": None,
            "content_language": None,
        }
        self.release: Optional[str] = None

    @staticmethod
    def _render_sdk():
        # format description: https://develop.sentry.dev/sdk/event-payloads/sdk/
        return {
            "name": "newpipe.crashreportimporter",
            # we don't really care at all about the version, but it's supposed to be semver
            "version": "0.0.1",
        }

    def _render_exceptions(self):
        return {"values": [self.exception.to_json()]}

    def to_dict(self) -> dict:
        # the Sentry API requires the keys event_id, timestamp and platform to be set
        # optional keys we want to use for some additional convenience are release, tags, and extra
        # future versions might use fingerprint as well to help with the deduplication of the events
        rv = {
            "event_id": self.event_id,
            "timestamp": self.timestamp,
            # setting the right platform apparently enables some convenience functionality in Sentry
            # Java seems the most suitable for Android stuff
            "platform": "java",
            # doesn't seem to be contained in any of the examples in glitchtip-backend/events/test_data any more
            # but still works, apparently (and is required by GlitchTip)
            "message": self.message,
            # Sentry apparently now allows for more than one exception to be passed (i.e., when an exception is
            # caused by another exception)
            # GlitchTip seems to support that, too, looking at their example data
            # therefore, the singular is not really appropriate and misleading
            "exception": self._render_exceptions(),
            "extra": self.extra,
            "tags": self.tags,
            # sending None/null in case this won't cause any issues, so we can be lazy here
            "release": self.release,
            # for some annoying reason, GlitchTip insists on us specifying an SDK
            "sdk": self._render_sdk(),
            # we only report errors to GlitchTip (it's also the default value)
            "level": "error",
        }

        return rv


class GlitchtipStorage(Storage):
    """
    Used to store incoming mails on a GlitchTip server.
    https://app.glitchtip.com/docs/

    Remembers already sent mail reports by putting their hash IDs in a file
    in the application's working directory.
    """

    def __init__(self, dsn: str, package: str):
        self.sentry_auth = Dsn(dsn).to_auth()
        self.package = package

    def make_sentry_payload(self, entry: DatabaseEntry):
        newpipe_exc_info = entry.newpipe_exception_info

        frames: List[SentryFrame] = []

        try:
            raw_data = "".join(newpipe_exc_info["exceptions"])
        except KeyError:
            raise StorageError("'exceptions' key missing in JSON body")

        raw_frames = raw_data.replace("\n", " ").replace("\r", " ").split("\tat")

        # pretty ugly, but that's what we receive from NewPipe
        # both message and exception name are contained in the first item in the frames
        message = raw_frames[0]

        for raw_frame in raw_frames[1:]:
            # some very basic sanitation, as e-mail clients all suck
            raw_frame = raw_frame.strip()

            # _very_ basic but gets the job done well enough
            frame_match = re.search(r"(.+)\(([a-zA-Z0-9:.\s]+)\)", raw_frame)

            if frame_match:
                module_path = frame_match.group(1).split(".")
                filename_and_lineno = frame_match.group(2)

                if ":" in filename_and_lineno:
                    # "unknown source" is shown for lambda functions
                    filename_and_lineno_match = re.search(
                        r"(Unknown\s+Source|(?:[a-zA-Z]+\.(?:kt|java)+)):([0-9]+)",
                        filename_and_lineno,
                    )

                    if not filename_and_lineno_match:
                        raise ValueError(
                            f"could not find filename and line number in string {frame_match.group(2)}"
                        )

                    # we want just two matches, anything else would be an error in the regex
                    assert len(filename_and_lineno_match.groups()) == 2

                    frame = SentryFrame(
                        filename_and_lineno_match.group(1),
                        module_path[-1],
                        ".".join(module_path[:-1]),
                        lineno=int(filename_and_lineno_match.group(2)),
                    )

                    frames.append(frame)

                else:
                    # apparently a native exception, so we don't have a line number
                    frame = SentryFrame(
                        frame_match.group(2),
                        module_path[-1],
                        ".".join(module_path[:-1]),
                    )

                    frames.append(frame)

            else:
                raise ParserError("Could not parse frame: '{}'".format(raw_frame))

        try:
            type = message.split(":")[0].split(".")[-1]
            value = message.split(":")[1]
            module = ".".join(message.split(":")[0].split(".")[:-1])

        except IndexError:
            type = value = module = "<none>"

        timestamp = entry.date.timestamp()

        # set up the payload, with all intermediary value objects
        stacktrace = SentryStacktrace(frames)
        exception = SentryException(type, value, module, stacktrace)

        # TODO: support multiple exceptions to support "Caused by:"
        payload = SentryPayload(entry.hash_id(), timestamp, message, exception)

        # try to fill in as much optional data as possible

        try:
            # in Sentry, releases are now supposed to be unique organization wide
            # in GlitchTip, however, they seem to be regarded as tags, so this should work well enough
            payload.release = entry.newpipe_exception_info["version"]
        except KeyError:
            pass

        for key in ["user_comment", "request", "user_action"]:
            try:
                payload.extra[key] = newpipe_exc_info[key]
            except KeyError:
                pass

        for key in ["os", "service", "content_language"]:
            try:
                payload.tags[key] = newpipe_exc_info[key]
            except KeyError:
                pass

        try:
            package = newpipe_exc_info["package"]
        except KeyError:
            package = None

        if package is not None:
            if package != self.package:
                raise ValueError("Package name not allowed: %s" % package)
            else:
                payload.tags["package"] = newpipe_exc_info["package"]

        return payload

    async def save(self, entry: DatabaseEntry):
        exception = self.make_sentry_payload(entry)
        data = exception.to_dict()

        # we use Sentry SDK's auth helper object to calculate both the required auth header as well as the URL from the
        # DSN string we already created a Dsn object for
        url = self.sentry_auth.store_api_url

        # it would be great if the Auth object just had a method to create/update a headers dict
        headers = {
            "X-Sentry-Auth": str(self.sentry_auth.to_header()),
            # user agent isn't really necessary, but sentry-sdk sets it, too, so... why not
            "User-Agent": "NewPipe Crash Report Importer",
            # it's recommended by the Sentry docs to send a valid MIME type
            "Content-Type": "application/json",
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(url, data=data, headers=headers) as response:
                response.raise_for_status()
