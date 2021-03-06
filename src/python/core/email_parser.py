"""
Parse email module.
Return the necessary email attributes:
from, to, subject, timestamp, body, html, attachments
"""

import hashlib
import os
import re
import time
from StringIO import StringIO
from email.utils import parseaddr

from email.Header import decode_header

import email
import dateutil.parser
import MySQLdb

ADDR_FIELDS = ['To', 'Cc', 'Bcc']


class NotSupportedMailFormat(Exception):
    """
    NotSupportedMailFormat exception is raised when
    unsupported email file contents received.
    """
    def __init__(self, custom_message):
        msg = '%s' % (custom_message, )
        Exception.__init__(self, msg)


def parse_raw_email(path, u_id, attachments_path):
    """Parse raw email file (RFC 822).

    Get and return email attributes and file attachments."""
    try:
        with open(path, 'r') as work_file:
            msgobj = email.message_from_file(work_file)
            if 'Content-Type' not in msgobj:
                raise NotSupportedMailFormat(
                    'Unsupported email content received'
                )

        subject, timestamp, recipients = parse_header(msgobj)
        attachments, body, html = parse_content(
            msgobj, u_id, attachments_path
        )

        return {
            'subject': subject,
            'timestamp': timestamp,
            'body': body,
            'html': html,
            'from': parseaddr(msgobj.get('From'))[1],
            'to': recipients,
            'source_email_path': path,
            'attachments': attachments
        }

    except NotSupportedMailFormat:
        print 'Not supported email format'
        return None


def parse_header(msgobj):
    """Parse email header.

    Return subject, timestamp and recipients."""
    if msgobj.get('Subject'):
        decode_frag = decode_header(msgobj.get('Subject'))
        subj_fragments = []
        for subj, enc in decode_frag:
            if enc:
                subj = unicode(subj, enc).encode('utf8', 'replace')
            subj_fragments.append(subj)
        subject = ''.join(subj_fragments)
    else:
        subject = None

    date = msgobj.get('Date')
    if date:
        datetime = dateutil.parser.parse(date)
        timestamp = time.mktime(datetime.timetuple())
    else:
        timestamp = None

    recipients = []
    for address in ADDR_FIELDS:
        if msgobj.get(address):
            recipient = re.findall(
                r'[\w\.,]+@[\w\.,]+\.\w+', msgobj.get(address)
            )
            for item in recipient:
                recipients.append(item)
    return subject, timestamp, recipients


def parse_content(msgobj, u_id, attachments_path):
    """Parse email content.

    Return attachments, body, html."""
    attachments = parse_attachments(msgobj, u_id, attachments_path)
    body = None
    html = None

    for part in msgobj.walk():
        if not part.is_multipart():
            payload = part.get_payload(decode=True)
            charset = part.get_content_charset()
            if payload and charset:
                text = unicode(
                    payload,
                    charset,
                    'replace'
                ).encode('utf8', 'replace')
                if part.get_content_type() == 'text/plain':
                    if not body:
                        body = ""
                        body += text
                elif part.get_content_type() == 'text/html':
                    if not html:
                        html = ""
                        html += text

    if body:
        body = body.replace('\t', '').replace('\r', '').replace('\n', ' ')
        body = MySQLdb.escape_string(body.rstrip())
        body = ' '.join(body.split())
    html = MySQLdb.escape_string(html) if html else None

    return attachments, body, html


def parse_attachments(msgobj, u_id, attachments_path):
    """Get and decode file attachments.

    Save attachments to corresponding files."""
    if not os.path.exists(attachments_path):
        os.mkdir(attachments_path)

    attachments = []

    for part in msgobj.walk():

        content_disposition = part.get('Content-Disposition')

        if content_disposition:
            dispositions = content_disposition.strip().split(";")
            if content_disposition \
                    and 'attachment' or 'inline' in dispositions[0].lower():

                if not os.path.exists(os.path.join(attachments_path, u_id)):
                    os.mkdir(os.path.join(attachments_path, u_id))

                file_data = part.get_payload(decode=True)

                attachment = StringIO(file_data)
                attachment.content_type = part.get_content_type()
                attachment.name = None
                attachment.path = None
                attachment.md5 = None
                attachment.size = None
                attachment.source_email_path = None

                try:
                    name = decode_header(part.get_filename())
                    file_name, charset = name[0]
                    attachment.name = \
                        file_name.decode(charset) if charset else file_name
                except UnicodeEncodeError:
                    for param in dispositions[1:]:
                        name, value = param.split('=')
                        name = name.lower()
                        if 'filename' in name:
                            attachment.name = value.replace('"', '')

                if attachment.name:
                    file_path = os.path.join(
                        attachments_path, u_id, attachment.name
                    )

                    with open(file_path, 'wb') as destination_file:
                        destination_file.write(file_data)
                    attachment.path = file_path
                    attachment.size = os.path.getsize(file_path)
                    md5_obj = hashlib.md5()
                    md5_obj.update(file_data)
                    attachment.md5 = md5_obj.hexdigest()
                    attachments.append(attachment)
    return attachments
