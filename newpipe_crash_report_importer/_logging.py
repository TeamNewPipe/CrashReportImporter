import logging

import coloredlogs


def make_logger(child_name: str = None):
    main_logger = logging.getLogger("importer")

    if child_name:
        return main_logger.getChild(child_name)

    return main_logger


def configure_logging():
    # better log format: less verbose, but including milliseconds
    fmt = "%(asctime)s,%(msecs)03d %(name)s [%(levelname)s] %(message)s"
    coloredlogs.install(level=logging.INFO, fmt=fmt)

    logging.getLogger("mail").setLevel(logging.WARNING)
