import logging

import coloredlogs


def make_logger(child_name: str = None):
    main_logger = logging.getLogger("importer")

    if child_name:
        return main_logger.getChild(child_name)

    return main_logger


def configure_logging(force_colors: bool = False):
    # better log format: less verbose, but including milliseconds
    fmt = "%(asctime)s,%(msecs)03d %(name)s [%(levelname)s] %(message)s"

    extra_kwargs = dict()

    if force_colors:
        extra_kwargs["isatty"] = True

    coloredlogs.install(level=logging.INFO, fmt=fmt, **extra_kwargs)

    # hide aiosmtpd's log spam
    # unfortunately, it can't be configured any more fine grainedly at this point
    # see https://github.com/aio-libs/aiosmtpd/issues/239 for more information
    logging.getLogger("mail").setLevel(logging.WARNING)
