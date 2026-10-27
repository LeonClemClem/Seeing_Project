"""Daily collection of the seeing measured by the public monitors that publish their data online.

Ported from the research collectors (claude/seeing-*/collect-*.ps1):
- Miratlas Grafana API (anonymous): Saint-Véran, OHP, Seeing monitor 5 (Villeneuve); raw ~1 min values,
  SSM by day, CDIMM by night; the API keeps at least 30 days, so a missed day is caught up;
- Copernic 05: text file of the current night, local time;
- ROSA (Verclause, Drôme): RRDtool image of the last 24 h, digitised (blue = raw, red = mean).
Pic du Midi and CosmoDrôme have no online data (their files are uploaded by research/envoi_site.py).
"""

from __future__ import annotations

import json
import logging
import struct
import urllib.request
import zlib
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime

import numpy as np
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import sessionmaker

from seeing_db import Measurement, Site

logger = logging.getLogger("seeing_batch")

MIRATLAS_API = "https://dashboard.miratlas.net/api/ds/query?orgId=29"
# site slug -> Miratlas datasource (one station per datasource)
MIRATLAS = {
    "saint-veran": "ddzuval7sgglcb",
    "ohp": "dec92cumscphca",
    "seeing-monitor-5": "d4ce5b0b-3a85-4e59-8931-c82a59f73f6e",
}
COPERNIC_URL = "https://www.asso-copernic.org/seeing/data.txt"
ROSA_URL = "https://rosa-remote.com/rosa-live/images/sm.png"
SEEING_RANGE = (0.05, 20.0)  # same bounds as the measurement upload of the API
TIMEOUT = 120
USER_AGENT = "seeing-batch (seeingthesky.com)"

Points = list[tuple[datetime, float]]


def _get(url: str, data: bytes | None = None) -> tuple[bytes, dict]:
    headers = {"User-Agent": USER_AGENT}
    if data is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers)  # noqa: S310 - fixed https URLs above
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:  # noqa: S310
        return r.read(), dict(r.headers)


def paris_offset(t_utc: datetime) -> timedelta:
    """Europe/Paris offset at a UTC time (EU rule: UTC+2 from the last Sunday of March to the last Sunday of
    October, 01:00 UTC), without depending on the tz database of the image."""

    def last_sunday(year: int, month: int) -> datetime:
        d = datetime(year, month, 31, 1, tzinfo=UTC)
        return d - timedelta(days=(d.weekday() + 1) % 7)

    y = t_utc.year
    return timedelta(hours=2 if last_sunday(y, 3) <= t_utc < last_sunday(y, 10) else 1)


def paris_to_utc(local: datetime) -> datetime:
    """Naive Europe/Paris time -> aware UTC (the doubled hour of the October change is taken as summer time)."""
    for h in (2, 1):
        t = (local - timedelta(hours=h)).replace(tzinfo=UTC)
        if paris_offset(t) == timedelta(hours=h):
            return t
    return (local - timedelta(hours=1)).replace(tzinfo=UTC)  # skipped hour of the March change


# ---------------------------------------------------------------- Miratlas
def miratlas_query(ds_uid: str, days: int) -> bytes:
    start = (datetime.now(UTC) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    queries = []
    for ref, field in (("day", "day_see"), ("night", "night_see")):
        flux = (
            f'from(bucket: "miratlas")\n  |> range(start: {start}, stop: v.timeRangeStop)\n'
            f'  |> filter(fn: (r) => r._measurement == "ism_stations" and r._field == "{field}")\n'
            "  |> filter(fn: (r) => r._value > 0 and r._value <= 10)\n"
            '  |> group(columns: ["_field"])'
        )
        queries.append({"refId": ref, "datasource": {"type": "influxdb", "uid": ds_uid}, "query": flux, "maxDataPoints": 100000})
    return json.dumps({"queries": queries, "from": f"now-{days}d", "to": "now"}).encode()


def parse_miratlas(payload: dict) -> Points:
    """SSM (day) where present, CDIMM (night) otherwise, as the research `observations()`."""
    series: dict[str, dict[int, float]] = {}
    for ref in ("day", "night"):
        r = payload.get("results", {}).get(ref, {})
        if r.get("error"):
            raise RuntimeError(f"Miratlas {ref}: {r['error']}")
        vals: dict[int, float] = {}
        for frame in r.get("frames") or []:
            t, v = frame["data"]["values"][0], frame["data"]["values"][1]
            vals.update({int(a): float(b) for a, b in zip(t, v, strict=False) if b is not None})
        series[ref] = vals
    merged = {**series["night"], **series["day"]}
    return [(datetime.fromtimestamp(ms / 1000, UTC), v) for ms, v in sorted(merged.items())]


def fetch_miratlas(ds_uid: str, days: int) -> Points:
    body, _ = _get(MIRATLAS_API, miratlas_query(ds_uid, days))
    return parse_miratlas(json.loads(body))


# ---------------------------------------------------------------- Copernic
def parse_copernic(text: str) -> Points:
    """Lines `dd/mm/yyyy,HH:MM:SS,scintillation,seeing` in local time."""
    out = []
    for line in text.splitlines():
        f = line.strip().split(",")
        if len(f) < 4:
            continue
        try:
            local = datetime.strptime(f"{f[0]} {f[1]}", "%d/%m/%Y %H:%M:%S")
            out.append((paris_to_utc(local), float(f[3])))
        except ValueError:
            continue
    return out


def fetch_copernic(days: int) -> Points:
    body, _ = _get(COPERNIC_URL)
    return parse_copernic(body.decode("utf-8", "replace"))


# ---------------------------------------------------------------- ROSA (image)
def decode_png(data: bytes) -> np.ndarray:
    """8-bit, non-interlaced PNG (RGB, RGBA, grey or palette) -> uint8 array (H, W, 3). RRDtool images only
    need this subset, and it avoids an image library in the batch image."""
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("not a PNG")
    pos, idat, plte = 8, b"", None
    w = h = depth = ctype = interlace = 0
    while pos < len(data):
        n, kind = struct.unpack(">I4s", data[pos : pos + 8])
        chunk = data[pos + 8 : pos + 8 + n]
        pos += 12 + n
        if kind == b"IHDR":
            w, h, depth, ctype, _, _, interlace = struct.unpack(">IIBBBBB", chunk)
        elif kind == b"PLTE":
            plte = np.frombuffer(chunk, np.uint8).reshape(-1, 3)
        elif kind == b"IDAT":
            idat += chunk
        elif kind == b"IEND":
            break
    if depth != 8 or interlace:
        raise ValueError(f"unsupported PNG (depth {depth}, interlace {interlace})")
    bpp = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[ctype]
    raw = np.frombuffer(zlib.decompress(idat), np.uint8)
    stride = w * bpp
    img = np.zeros((h, stride), np.uint8)
    prev = np.zeros(stride, np.int32)
    for y in range(h):
        f = raw[y * (stride + 1)]
        line = raw[y * (stride + 1) + 1 : (y + 1) * (stride + 1)].astype(np.int32)
        if f == 0:
            cur = line
        elif f == 2:
            cur = (line + prev) & 255
        else:  # 1 (sub), 3 (average), 4 (Paeth) depend on the left pixel: byte by byte
            cur = np.zeros(stride, np.int32)
            for i in range(stride):
                a = cur[i - bpp] if i >= bpp else 0
                b = prev[i]
                c = prev[i - bpp] if i >= bpp else 0
                if f == 1:
                    p = a
                elif f == 3:
                    p = (a + b) >> 1
                else:
                    pa, pb, pc = abs(b - c), abs(a - c), abs(a + b - 2 * c)
                    p = a if pa <= pb and pa <= pc else (b if pb <= pc else c)
                cur[i] = (line[i] + p) & 255
        img[y] = cur
        prev = cur
    px = img.reshape(h, w, bpp)
    if ctype == 3:
        if plte is None:
            raise ValueError("palette PNG without PLTE")
        return plte[px[:, :, 0]]
    if ctype in (0, 4):
        return np.repeat(px[:, :, :1], 3, axis=2)
    return px[:, :, :3].copy()


GREEN_REF = 2.5  # arcsec of the green threshold line


def digitise_rosa(img: np.ndarray, ref_local: datetime) -> Points:
    """Digitise the ROSA RRDtool chart (same steps as collect-seeing-rosa.ps1); `ref_local` = Last-Modified in
    local time, which places the right edge. Returns the raw values (blue; the mean where blue is hidden)."""
    R, G, B = (img[:, :, k].astype(int) for k in range(3))
    H, W = R.shape
    gray = (R == 128) & (G == 128) & (B == 128)
    hourl = (R == 162) & (G == 110) & (B == 110)
    green = (G >= 240) & (R <= 20) & (B <= 20)
    red = (R >= 170) & (G <= 110) & (B <= 110) & (R - G >= 90)
    blue = (B >= 170) & (R <= 140) & (B - R >= 60)
    xs = np.flatnonzero(gray[H // 3])
    if not len(xs):
        raise ValueError("plot area not found")
    x0, x1 = int(xs[0]), int(xs[-1])
    # probe column: most grey background, with the green line and no curve
    probe, best, probe_any, best_any = -1, -1, -1, -1
    for lim in (x0 + 30, x1 - 1):
        for x in range(x0 + 1, lim + 1):
            n, curve = int(gray[:, x].sum()), bool((red[:, x] | blue[:, x]).any())
            if not curve and green[:, x].any() and n > best:
                probe, best = x, n
            if not curve and n > best_any:
                probe_any, best_any = x, n
        if best >= 0:
            break
    if best < 0:
        probe = probe_any
    if probe < 0:
        raise ValueError("no probe column")
    bg = gray[:, probe] | ((R[:, probe] == 133) & (G[:, probe] == 133)) | hourl[:, probe] | green[:, probe]
    y_top = y_last = -1
    for y in range(H):
        if bg[y]:
            if y_top < 0:
                y_top = y
            y_last = y
        elif y_top >= 0 and y_last - y_top < 10:
            y_top = y_last = -1  # isolated grey (title)
        elif y_top >= 0:
            break
    y_axis = y_last + 1
    if y_top < 0 or y_axis <= y_top:
        raise ValueError("plot area not found")
    # Y scale: green line = 2.5", refined with the major gridlines (step 1" without the green line)
    yg = np.flatnonzero(green[y_top:y_axis, probe])
    px_unit = (y_axis - (y_top + yg[0])) / GREEN_REF if len(yg) else -1.0
    major = [y for y in range(y_top, y_axis) if hourl[y, x0 : x1 + 1].sum() >= 100]
    if len(major) >= 2:
        spacing = (y_axis - major[0]) / len(major)
        step = 1.0
        if px_unit > 0:
            approx = spacing / px_unit
            step = min((0.1, 0.2, 0.25, 0.5, 1, 2, 2.5, 5, 10), key=lambda s: abs(np.log(s / approx)))
        px_unit = spacing / step
    if px_unit <= 0:
        raise ValueError("Y scale not found")
    # X scale: hourly lines crossing the plot
    hour_x = [x for x in range(x0, x1 + 1) if hourl[y_top:y_axis:3, x].sum() >= 10]
    if len(hour_x) < 4:
        raise ValueError("hourly lines not found")
    px_hour = float(np.polyfit(np.arange(len(hour_x)), hour_x, 1)[0])
    sec_px = 3600 / px_hour
    x_last = hour_x[-1]
    h_ref = ref_local.replace(minute=0, second=0, microsecond=0)
    h_last = min(
        (h_ref + timedelta(hours=dh) for dh in range(-3, 2)),
        key=lambda hh: abs(x1 - (ref_local - hh).total_seconds() / sec_px - x_last),
    )
    out: Points = []
    span = y_axis - y_top
    for x in range(x0, x1 + 1):
        r_y, b_y = np.flatnonzero(red[y_top:y_axis, x]), np.flatnonzero(blue[y_top:y_axis, x])
        if not len(r_y) and not len(b_y):
            continue
        if len(r_y) + len(b_y) > 0.5 * span:  # gridline, not a measurement
            continue
        ys = b_y if len(b_y) else r_y
        v = (y_axis - (y_top + ys.mean())) / px_unit
        out.append((paris_to_utc(h_last + timedelta(seconds=(x - x_last) * sec_px)), round(float(v), 2)))
    # empty chart (ROSA shows "-nan"): fewer than 20 columns, or one single value
    if len(out) < 20 or len({v for _, v in out}) <= 1:
        return []
    return out


def fetch_rosa(days: int) -> Points:
    body, headers = _get(ROSA_URL)
    lm = headers.get("Last-Modified")
    ref = parsedate_to_datetime(lm).astimezone(UTC) if lm else datetime.now(UTC)
    ref_local = (ref + paris_offset(ref)).replace(tzinfo=None)
    return digitise_rosa(decode_png(body), ref_local)


SOURCES = {
    **{slug: (lambda days, ds=ds: fetch_miratlas(ds, days)) for slug, ds in MIRATLAS.items()},
    "copernic-gap": fetch_copernic,
    "verclause": fetch_rosa,
}


def store(session_factory: sessionmaker, slug: str, points: Points) -> int:
    rows = {t: v for t, v in points if SEEING_RANGE[0] <= v <= SEEING_RANGE[1]}
    if not rows:
        return 0
    with session_factory() as session:
        site_id = session.scalar(select(Site.id).where(Site.slug == slug))
        if site_id is None:
            return 0
        stmt = pg_insert(Measurement).values([dict(site_id=site_id, time=t, seeing_arcsec=v) for t, v in rows.items()])
        session.execute(stmt.on_conflict_do_update(index_elements=["site_id", "time"], set_={"seeing_arcsec": stmt.excluded.seeing_arcsec}))
        session.commit()
    return len(rows)


def collect(session_factory: sessionmaker, days: int = 7, sources=None) -> dict[str, int | str]:
    """Fetch every source and store its points (idempotent: same time = same row). A failing source is logged
    and skipped, never failing the batch."""
    report: dict[str, int | str] = {}
    for slug, fetch in (sources or SOURCES).items():
        try:
            report[slug] = store(session_factory, slug, fetch(days))
        except Exception as e:  # noqa: BLE001 - one monitor down must not stop the others
            report[slug] = f"error: {e}"
            logger.warning("Monitor %s: %s", slug, e)
    logger.info("Monitors collected: %s", report, extra={"monitors": report})
    return report
