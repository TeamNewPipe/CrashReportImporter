import json
import os

from . import AlreadyStoredError
from ..database_entry import DatabaseEntry
from .base import Storage


class DirectoryStorage(Storage):
    """
    Local storage implementation. Puts every database entry in a file named
    by their hash ID in a directory.
    """

    def __init__(self, directory: str):
        self.directory = os.path.abspath(directory)
        os.makedirs(self.directory, exist_ok=True)

    async def save(self, entry: DatabaseEntry):
        message_id = entry.hash_id() + ".json"
        subdir = os.path.join(
            self.directory, message_id[0], message_id[:3], message_id[:5]
        )
        os.makedirs(subdir, exist_ok=True)
        path = os.path.join(subdir, message_id)
        if os.path.isfile(path):
            raise AlreadyStoredError()

        with open(path, "w") as f:
            json.dump(entry.to_dict(), f, indent=2)
