"""A stand-in redactor with the D-058 defect: an enumerated whitespace class."""

import re

# "space, tab, non-breaking space, surely that is all of them"
_STREET_SEP = r"[ \t\xa0]+"

_RE_ADDRESS = re.compile(r"\d+" + _STREET_SEP + r"[A-Z]\w+")
