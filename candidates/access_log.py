"""logfmt access logger: one line per request, no standard log prefix."""

import logging
import re

_CONTROL = r'\x00-\x1f\x7f-\x9f\u2028\u2029'
_NEEDS_QUOTE = re.compile(r'[\s"=\\' + _CONTROL + ']')
_ESCAPE_CHARS = re.compile(r'["\\' + _CONTROL + ']')
_ESCAPES = {'"': '\\"', "\\": "\\\\", "\n": "\\n", "\r": "\\r", "\t": "\\t"}


def _escape(ch: str) -> str:
    return _ESCAPES.get(ch, f"\\u{ord(ch):04x}")


def _value(v: object) -> str:
    s = "-" if v is None else str(v)
    if s == "":
        return "-"
    if _NEEDS_QUOTE.search(s):
        return '"' + _ESCAPE_CHARS.sub(lambda m: _escape(m.group()), s) + '"'
    return s


def logfmt(pairs: list[tuple[str, object]]) -> str:
    return " ".join(f"{k}={_value(v)}" for k, v in pairs)


access_logger = logging.getLogger("access")
access_logger.setLevel(logging.INFO)
access_logger.propagate = False
if not access_logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("%(message)s"))
    access_logger.addHandler(_handler)
