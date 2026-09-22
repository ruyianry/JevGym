from __future__ import annotations

from datetime import datetime, timezone

from jevgym.util import from_unix, iso, parse_dt, sha256_file, short_hash, to_unix


def test_parse_dt_accepts_unix_iso_and_dateonly():
    assert parse_dt(1758400000).tzinfo is not None
    assert parse_dt("2026-09-21T00:00:00Z") == datetime(2026, 9, 21, tzinfo=timezone.utc)
    assert parse_dt("2026-08-01") == datetime(2026, 8, 1, tzinfo=timezone.utc)
    assert parse_dt("") is None
    assert parse_dt(None) is None
    assert parse_dt("not-a-date") is None


def test_unix_roundtrip():
    dt = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    assert from_unix(to_unix(dt)) == dt


def test_short_hash_is_deterministic():
    assert short_hash("a", 1) == short_hash("a", 1)
    assert short_hash("a", 1) != short_hash("a", 2)


def test_sha256_file(tmp_path):
    p = tmp_path / "f.bin"
    p.write_bytes(b"hello")
    digest, size = sha256_file(p)
    assert size == 5
    assert digest == "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"


def test_iso_none():
    assert iso(None) is None
