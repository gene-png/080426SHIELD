"""A stand-in redactor whose separators are COMPUTED, not listed."""

import re

# The subtraction, not a hand list: let the language define the set. The
# vertical characters are written as ESCAPE TEXT, never as literal bytes --
# a fixture for one gate must not trip another, and check_no_control_chars
# caught exactly that here because its exemption covers only its own tree.
_HSPACE = r"[^\S\n\v\f\r\x1c\x1d\x1e\x85\u2028\u2029]"
_STREET_SEP = _HSPACE + r"+"

_RE_ADDRESS = re.compile(r"\d+" + _STREET_SEP + r"[A-Z]\w+")
