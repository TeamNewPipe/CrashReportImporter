import logging


def make_logger(child_name: str = None):
    main_logger = logging.getLogger("importer")

    if child_name:
        return main_logger.getChild(child_name)

    return main_logger


def configure_logging():
    pass
