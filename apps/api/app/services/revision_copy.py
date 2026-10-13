"""#1120 "Start a revision": the API's refusal copy, approved verbatim by the
advisor (#736 6136101129, item 6). Extracted by script from section 8 of the
#1120 design note rev 10 (sha256 c5fcfb745c6c4ad9...), never retyped; do not
edit by hand. Placeholders: `{v}` is the version the request named, `{n}` is
the newer version that blocks it."""

COPY: dict[str, str] = {
    "V6": "Version {n} is open as a draft. Approve it, or discard it, before starting another revision.",  # noqa: E501
    "V8": "Version {v} is a draft, so it can be edited directly.",  # noqa: E501
    "V10": "Version {v} was submitted by the client and is waiting for your review. Approve it before starting a revision.",  # noqa: E501
    "V12": "Version {n} is newer than version {v}. Only the newest version can be revised.",  # noqa: E501
    "X0": "This assessment is in a state SHIELD does not expect, so nothing was changed. The details have been logged for the team.",  # noqa: E501
    "X1": "This version was discarded, so it cannot be revised.",  # noqa: E501
    "X2": "This service has been archived, so it cannot be revised.",  # noqa: E501
}
