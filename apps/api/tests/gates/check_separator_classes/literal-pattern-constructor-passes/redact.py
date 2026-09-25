"""A stand-in redactor that turns data into a pattern only through the constructor."""

import re

_HSPACE = r"[^\S\n\v\f\r\x1c\x1d\x1e\x85\u2028\u2029]"


def _literal_pattern(needle):
    """Where `re.escape(` is allowed -- mentioned here, called below."""
    tokens = needle.split()
    return (_HSPACE + "+").join(re.escape(t) for t in tokens)


def redact_org_name(text, org_name):
    return re.compile(_literal_pattern(org_name), re.IGNORECASE).sub("[CLIENT]", text)
