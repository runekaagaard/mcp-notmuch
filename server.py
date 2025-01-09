import base64, re, quopri, os, logging, traceback
from datetime import datetime
from functools import wraps

import html2text
from mcp.server.fastmcp import FastMCP
from notmuch import Query, Database

### Constants ###

NOTMUCH_DATABASE_PATH = os.getenv('NOTMUCH_DATABASE_PATH', False)
LOG_FILE_PATH = os.getenv('LOG_FILE_PATH', False)

### Logging ###

logger = None

if LOG_FILE_PATH:
    logger = logging.getLogger('function_logger')
    logger.setLevel(logging.DEBUG)
    fh = logging.FileHandler(LOG_FILE_PATH)
    fh.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    logger.addHandler(fh)

def log(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if not logger:
            return func(*args, **kwargs)

        try:
            logger.info(f"Calling {func.__name__} with args={args}, kwargs={kwargs}")
            result = func(*args, **kwargs)
            logger.info(f"{func.__name__} returned {result}")
            return result
        except Exception as e:
            logger.error(f"{func.__name__} raised {type(e).__name__}: {str(e)}\n{traceback.format_exc()}")
            raise

    return wrapper

### Notmuch API ###

REPLY_SEPARATORS = [
    "* * *", "venlig hilsen", "med venlig hilsen", "med venlig hilse", "mvh", "m.v.h", "de bedste hilsner",
    "bedste hilsner", "/ tuxen", "på forhånd tak", "på forhånd mange tak", "hilsen "
]

def message_to_text(message):
    def normalize_empty_lines(text):
        return re.sub(r'(\n\s*){2,}', '\n\n', text)

    def extract_reply(text):
        result = []
        for line in text.splitlines():
            for reply_separator in REPLY_SEPARATORS:
                if line.lower().startswith(reply_separator):
                    return "\n".join(result).strip()
            result.append(line)
        return text

    def decode_qp(text):
        try:
            return quopri.decodestring(text.encode('utf-8')).decode('utf-8')
        except UnicodeDecodeError:
            return quopri.decodestring(text.encode('utf-8')).decode('latin1')

    from_addr = message.get_header('From').strip()
    date_str = datetime.fromtimestamp(message.get_date()).strftime("%Y-%m-%d %H:%M:%S")

    result = [f"FROM: {from_addr}", f"DATE: {date_str}"]
    parts = list(message.get_message_parts())

    for part in parts:
        if part.get_content_type() == "text/html":
            html = part.get_payload()
            encoding = part.get('Content-Transfer-Encoding', '').lower()
            if encoding == "base64":
                html = base64.b64decode(html).decode("utf-8")
            elif encoding == "quoted-printable":
                html = decode_qp(html)
            h = html2text.HTML2Text()
            h.body_width = 0
            h.emphasis_mark = ""
            h.strong_mark = ""
            plain = h.handle(html)
            plain = normalize_empty_lines(plain)
            plain = extract_reply(plain)
            result.append(plain)

    return "\n".join(result)

### MCP Implementation ###

mcp = FastMCP("Notmuch MCP")

@mcp.tool(description=f"View all messages in an email thread at the notmuch database at {NOTMUCH_DATABASE_PATH}")
@log
def view_email_thread(thread_id: str) -> str:
    try:
        db = Database(NOTMUCH_DATABASE_PATH)
        # query = Query(db, 'thread:0000000000005329')
        # query = Query(db, 'thread:00000000000052b1')
        query = Query(db, f'thread:{thread_id}')
        query.set_sort(Query.SORT.OLDEST_FIRST)
        messages = query.search_messages()

        result = "- - -\n".join([message_to_text(message) for message in messages])

        if not result:
            return "Not found!"
        else:
            return result
    except:
        raise
    finally:
        try:
            db.close()
            del query
            del db
        except:
            pass

if __name__ == "__main__":
    mcp.run()
