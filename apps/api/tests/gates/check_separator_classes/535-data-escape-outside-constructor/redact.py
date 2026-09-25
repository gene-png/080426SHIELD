"""A stand-in redactor with #535's shape: data becomes a pattern via re.escape."""

import re


def redact_org_name(text, org_name):
    pat = re.compile(r"\b" + re.escape(org_name) + r"\b", re.IGNORECASE)
    return pat.sub("[CLIENT]", text)
