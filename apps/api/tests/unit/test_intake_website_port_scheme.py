"""#1116: a website the client typed as a bare number, or as "http"/"https" and
a colon followed by a number, is REFUSED.

"https:8080" got the `https://` prefix (the colon-digit reads as a port) and
was stored with host "https". And `HttpUrl` turns a bare number into an
address, so "8080", "https:/8080", a percent-encoded or full-width "8080" all
land on host 0.0.31.144 (review of 2a4f17eb). Refused with the schema 422 the
wizard shows as "This value was not accepted, so it was not saved.". A typed
dotted quad names its host and is kept, as are hosts with ports.

Through the real endpoint, asserted on the response and the stored column.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.models.client import Client
from tests.unit.test_intake_routes import (
    _register_and_bearer,
    app_client,  # noqa: F401  (fixture)
)

pytestmark = pytest.mark.unit


def _patch_website(client, bearer: str, website: str):
    return client.patch(
        "/intake",
        headers={"Authorization": f"Bearer {bearer}"},
        json={"client": {"website": website}},
    )


@pytest.mark.parametrize(
    "typed",
    [
        "https:8080",
        "http:443/x",
        "HTTPS:8080",
        "https:8080/about",
        " http:80 ",
        "8080",
        "https:/8080",
        "https:\\8080",
        "https:%38080",
        # The "//" missing before a real dotted quad: the prefix made its host
        # "https", so it is refused too.
        "https:1.2.3.4",
        # #1230 item 1: the dotted quad must be the HOST the client typed, not
        # text anywhere else in the value.
        "8080/0.0.31.144",
        "8080?0.0.31.144",
        "https:/8080#0.0.31.144",
        "8080\\0.0.31.144",  # a backslash cuts the authority too
        "https:\uff18\uff10\uff18\uff10",  # full-width "8080"
    ],
)
def test_a_bare_scheme_and_a_port_is_refused(app_client, typed) -> None:  # noqa: F811
    client, TestSession = app_client
    bearer = _register_and_bearer(client)
    r = _patch_website(client, bearer, typed)
    assert r.status_code == 422, r.text
    assert r.json()["error"]["reason"].startswith("schema_")
    with TestSession() as db:
        assert db.execute(select(Client)).scalar_one().website is None


@pytest.mark.parametrize(
    ("typed", "stored"),
    [
        # A real host with a port still gets the prefix (the reading #1116
        # must not break), and so does a host that merely starts with "http".
        ("example.com:8080", "https://example.com:8080/"),
        ("httpbin.org:8080", "https://httpbin.org:8080/"),
        ("https://kentro.com:8443", "https://kentro.com:8443/"),
        # A dotted quad the client typed names its own host (review of
        # 2a4f17eb: the widened rule must not refuse a real address).
        ("https://1.2.3.4", "https://1.2.3.4/"),
        ("http://1.2.3.4", "http://1.2.3.4/"),
        ("1.2.3.4:8080", "https://1.2.3.4:8080/"),
        # A dotted quad in the PATH after a real host is not the host at all.
        ("example.com/1.2.3.4", "https://example.com/1.2.3.4"),
        ("https://1.2.3.4/0.0.0.1", "https://1.2.3.4/0.0.0.1"),
        ("//1.2.3.4", "https://1.2.3.4/"),  # leading slashes, no scheme
    ],
)
def test_a_host_with_a_port_is_still_accepted(app_client, typed, stored) -> None:  # noqa: F811
    client, _ = app_client
    bearer = _register_and_bearer(client)
    r = _patch_website(client, bearer, typed)
    assert r.status_code == 200, r.text
    assert r.json()["client"]["website"] == stored
