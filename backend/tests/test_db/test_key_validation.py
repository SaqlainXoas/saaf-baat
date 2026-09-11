"""A publishable key must fail at construction, not at the first query.

RLS denies everything on this project and only the server key holds grants, so
an anon key connects and then fails every statement with a bare "permission
denied for table raw_articles" - naming neither the cause nor the fix.
"""
import base64
import json

import pytest

from src.db.client import SupabaseClient, _key_role
from src.db.errors import DBConnectionError

URL = "https://example.supabase.co"


def _jwt(role: str) -> str:
    payload = base64.urlsafe_b64encode(
        json.dumps({"role": role, "ref": "example"}).encode()
    ).decode().rstrip("=")
    return f"header.{payload}.signature"


def test_legacy_anon_jwt_is_rejected():
    with pytest.raises(DBConnectionError) as exc:
        SupabaseClient(url=URL, key=_jwt("anon"))
    assert "service_role" in str(exc.value)


def test_publishable_key_is_rejected():
    with pytest.raises(DBConnectionError) as exc:
        SupabaseClient(url=URL, key="sb_publishable_abc123")
    assert "publishable" in str(exc.value).lower()


@pytest.mark.parametrize("key", [_jwt("service_role"), "sb_secret_abc123"])
def test_server_keys_are_accepted(key):
    client = SupabaseClient(url=URL, key=key)
    assert client.key == key


def test_unrecognised_key_shape_is_left_alone():
    """Never block on a key we cannot read - that would be a false positive."""
    client = SupabaseClient(url=URL, key="some-other-format")
    assert client.key == "some-other-format"


@pytest.mark.parametrize(
    "key,expected",
    [
        (_jwt("anon"), "anon"),
        (_jwt("service_role"), "service_role"),
        ("sb_publishable_x", "anon"),
        ("sb_secret_x", "service_role"),
        ("not-a-key", None),
        ("a.b.c", None),
    ],
)
def test_key_role_detection(key, expected):
    assert _key_role(key) == expected
