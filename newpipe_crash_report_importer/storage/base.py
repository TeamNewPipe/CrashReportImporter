from newpipe_crash_report_importer.database_entry import DatabaseEntry


class Storage:
    """
    Storage base class. Uses async I/O if possible
    """

    async def save(self, entry: DatabaseEntry) -> None:
        raise NotImplementedError()
