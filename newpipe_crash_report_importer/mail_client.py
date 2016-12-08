import email
import imaplib


class IMAPClientError(Exception):
    pass


def fetch_messages_from_imap(host, port, username, password):
    """
    Opens a connection to an IMAP server, downloads the relevant messages and
    archives processed mails in `Archives/Crashreport` directory on the
    IMAP server.

    :param host: IMAP server hostname
    :param port: IMAP server port
    :param username: IMAP login username
    :param password: IMAP login password

    :return: a generator iterating over all mails.
    """

    with imaplib.IMAP4(host, port=port) as client:
        client.starttls()
        client.login(username, password)
        client.select("INBOX", readonly=False)

        client.create("Archives")
        client.create("Archives/Crashreport")

        sorted_reply = client.uid("SORT", "(DATE)", "UTF7", "ALL")

        if not sorted_reply[0] == "OK":
            raise IMAPClientError()

        sorted_messages = sorted_reply[1][0].split()

        for msg_uid in sorted_messages:
            reply = client.uid("FETCH", msg_uid, "(RFC822)")

            if reply[0] != "OK":
                raise IMAPClientError()

            message = email.message_from_bytes(reply[1][0][1])

            yield message

            # mark message as read and move to archives
            mark_read_reply = client.uid("STORE", msg_uid, "+FLAGS", "(\\Seen)")
            if mark_read_reply[0] != "OK":
                raise IMAPClientError()

            # moving messages in IMAP unfortunately means copy and delete
            copy_reply = client.uid("COPY", msg_uid, "Archives/Crashreport")
            if copy_reply[0] != "OK":
                raise IMAPClientError()

            delete_reply = client.uid("STORE", msg_uid, "+FLAGS", "(\\Deleted)")
            if delete_reply[0] != "OK":
                raise IMAPClientError()

            # delete the message immediately
            client.expunge()
