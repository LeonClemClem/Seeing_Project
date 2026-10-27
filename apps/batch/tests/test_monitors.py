"""Online seeing monitors: parsing of each source and idempotent storage."""

import struct
import zlib
from datetime import UTC, datetime, timedelta

import numpy as np
from seeing_batch import monitors
from seeing_batch.cli import monitors_due
from sqlalchemy import func, select

from seeing_db import Measurement


def test_paris_time():
    assert monitors.paris_offset(datetime(2026, 7, 1, tzinfo=UTC)) == timedelta(hours=2)
    assert monitors.paris_offset(datetime(2026, 10, 27, tzinfo=UTC)) == timedelta(hours=1)
    # changes of 2026: 29/03 and 25/10 at 01:00 UTC
    assert monitors.paris_offset(datetime(2026, 3, 29, 0, 59, tzinfo=UTC)) == timedelta(hours=1)
    assert monitors.paris_offset(datetime(2026, 3, 29, 1, 0, tzinfo=UTC)) == timedelta(hours=2)
    assert monitors.paris_offset(datetime(2026, 10, 25, 1, 0, tzinfo=UTC)) == timedelta(hours=1)
    assert monitors.paris_to_utc(datetime(2026, 10, 27, 18, 1, 21)) == datetime(2026, 10, 27, 17, 1, 21, tzinfo=UTC)
    assert monitors.paris_to_utc(datetime(2026, 8, 1, 22, 0)) == datetime(2026, 8, 1, 20, 0, tzinfo=UTC)


def test_parse_copernic():
    pts = monitors.parse_copernic("27/10/2026,18:01:21,57.23,2.64\nbad line\n27/10/2026,18:02:21,59.77,2.58\n")
    assert pts == [(datetime(2026, 10, 27, 17, 1, 21, tzinfo=UTC), 2.64), (datetime(2026, 10, 27, 17, 2, 21, tzinfo=UTC), 2.58)]


def test_parse_miratlas_day_over_night():
    def frame(t, v):
        return {"frames": [{"data": {"values": [t, v]}}]}

    payload = {"results": {"day": frame([1000, 2000], [1.0, 1.5]), "night": frame([2000, 3000], [9.0, 2.0])}}
    pts = monitors.parse_miratlas(payload)
    assert [v for _, v in pts] == [1.0, 1.5, 2.0]  # SSM kept where both exist
    assert pts[0][0] == datetime.fromtimestamp(1, UTC)


def _png(rgb: np.ndarray, filt: int) -> bytes:
    h, w, _ = rgb.shape
    rows = b""
    for y in range(h):
        line = rgb[y].astype(np.int32).reshape(-1)
        if filt == 1:  # sub
            enc = (line - np.concatenate([[0, 0, 0], line[:-3]])) & 255
        else:
            enc = line
        rows += bytes([filt]) + enc.astype(np.uint8).tobytes()

    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))

    ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b"")


def test_decode_png():
    rgb = np.random.default_rng(1).integers(0, 256, (5, 7, 3), dtype=np.uint8)
    for filt in (0, 1):
        np.testing.assert_array_equal(monitors.decode_png(_png(rgb, filt)), rgb)


def test_monitors_due(monkeypatch):
    monkeypatch.delenv("MONITORS_ENABLED", raising=False)
    monkeypatch.delenv("MONITORS_UTC_HOUR", raising=False)
    assert monitors_due(datetime(2026, 10, 28, 11, 45, tzinfo=UTC))
    assert not monitors_due(datetime(2026, 10, 28, 3, 45, tzinfo=UTC))
    monkeypatch.setenv("MONITORS_ENABLED", "0")
    assert not monitors_due(datetime(2026, 10, 28, 11, 45, tzinfo=UTC))


def test_collect_stores_idempotently(db):
    t0 = datetime(2026, 10, 27, 20, tzinfo=UTC)
    pts = [(t0, 1.2), (t0 + timedelta(minutes=1), 1.4), (t0 + timedelta(minutes=2), 99.0)]  # 99" out of range

    def broken(days):
        raise OSError("down")

    sources = {"ohp": lambda days: pts, "copernic-gap": broken}
    assert monitors.collect(db, 7, sources) == {"ohp": 2, "copernic-gap": "error: down"}
    monitors.collect(db, 7, sources)  # same points again: no duplicate
    with db() as s:
        assert s.scalar(select(func.count()).select_from(Measurement)) == 2
