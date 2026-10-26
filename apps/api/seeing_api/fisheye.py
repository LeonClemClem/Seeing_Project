"""Fisheye: seeing in every direction of the sky at a point, from the stored global maps (no new
physics). Two-layer line of sight: the boundary-layer turbulence (share and height stored with each
map frame) and the free-atmosphere turbulence (its height) are read at the points where the line of
sight crosses their heights, and the integral is divided by sin(elevation).

The response gives, per frame, the low and high line-of-sight integrals at the map K, so that the
browser can rescale them with other K:  J = K_TKE / K_TKE_map * j_low + K_CIS / K_CIS_map * j_high.
"""

import math
import zlib
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select

from seeing_api.api import MAP_SEE_MAX, MAP_SEE_MIN, RunParam, SessionDep, _map_run, utc
from seeing_db import MapFrame

router = APIRouter(prefix="/api")

LAMBDA = 500e-9
ELEVATIONS = list(range(10, 91, 5))
AZIMUTHS = list(range(0, 360, 10))
H_LOW_STEP, H_HIGH_STEP = 20.0, 100.0  # same as seeing_core.grid
_LN0, _LN1 = math.log(MAP_SEE_MIN), math.log(MAP_SEE_MAX)
_JC = 0.423 * (2 * math.pi / LAMBDA) ** 2


def j_of_seeing(s: float) -> float:
    """Integral of Cn2 [m^1/3] giving the seeing s [arcsec] (inverse of the seeing formula)."""
    return (s / (0.98 * LAMBDA * 206265.0)) ** (5.0 / 3.0) / _JC


# J of each byte code of the seeing maps
J_OF_CODE = [j_of_seeing(math.exp(_LN0 + c / 254.0 * (_LN1 - _LN0))) for c in range(255)] + [math.nan]


class FisheyeFrame(BaseModel):
    lead_hour: int
    valid_time: str
    j_low: list[list[float | None]]  # [elevation][azimuth]
    j_high: list[list[float | None]]


class FisheyeOut(BaseModel):
    run_time: str
    k: list[float]  # map K the integrals are computed with
    elevations: list[int]
    azimuths: list[int]
    frames: list[FisheyeFrame]


def _sampler(buf: bytes, offset: int, ny: int, nx: int, decode):
    """Bilinear sampling of one uint8 plane (255 = none) at fractional (row, col)."""
    def at(r: float, c: float) -> float:
        if not (0 <= r <= ny - 1 and 0 <= c <= nx - 1):
            return math.nan
        r0, c0 = int(r), int(c)
        r1, c1 = min(r0 + 1, ny - 1), min(c0 + 1, nx - 1)
        fr, fc = r - r0, c - c0
        s = w = 0.0
        for rr, cc, ww in ((r0, c0, (1 - fr) * (1 - fc)), (r0, c1, (1 - fr) * fc), (r1, c0, fr * (1 - fc)), (r1, c1, fr * fc)):
            code = buf[offset + rr * nx + cc]
            if code != 255 and ww > 0:
                s += decode(code) * ww
                w += ww
        return s / w if w > 0 else math.nan
    return at


def _round(v: float) -> float | None:
    return None if not math.isfinite(v) else float(f"{v:.4g}")


@router.get("/fisheye", response_model=FisheyeOut)
def fisheye(
    session: SessionDep,
    lat: Annotated[float, Query(ge=-90, le=90)],
    lon: Annotated[float, Query(ge=-180, le=180)],
    run: RunParam = "latest",
) -> FisheyeOut:
    model_run = _map_run(session, run)
    rows = session.execute(
        select(MapFrame).where(MapFrame.run_id == model_run.id, MapFrame.extra.is_not(None)).order_by(MapFrame.lead_hour)
    ).scalars().all()
    if not rows:
        raise HTTPException(404, "No fisheye data for this run yet")
    frames = []
    for f in rows:
        n = f.ny * f.nx
        see, ext = zlib.decompress(f.data), zlib.decompress(f.extra)
        J = _sampler(see, 0, f.ny, f.nx, lambda c: J_OF_CODE[c])
        share = _sampler(ext, 0, f.ny, f.nx, lambda c: c / 254.0)
        h_low = _sampler(ext, n, f.ny, f.nx, lambda c: c * H_LOW_STEP)
        h_high = _sampler(ext, 2 * n, f.ny, f.nx, lambda c: c * H_HIGH_STEP)

        def rc(la: float, lo: float, f=f) -> tuple[float, float]:
            return (la - f.lat0) / f.dlat, (lo - f.lon0) / f.dlon

        r, c = rc(lat, lon)
        hl, hh = h_low(r, c), h_high(r, c)
        if not (math.isfinite(hl) and math.isfinite(hh)):
            raise HTTPException(404, "Point outside the AROME map")
        coslat = math.cos(math.radians(lat))
        jl_rows, jh_rows = [], []
        for el in ELEVATIONS:
            se, te = math.sin(math.radians(el)), math.tan(math.radians(el))
            jl_row, jh_row = [], []
            for az in AZIMUTHS:
                ca, sa = math.cos(math.radians(az)), math.sin(math.radians(az))
                out = []
                for h, low in ((hl, True), (hh, False)):
                    d = h / te if el < 90 else 0.0
                    pr, pc = rc(lat + d * ca / 111200.0, lon + d * sa / (111320.0 * coslat))
                    j, s = J(pr, pc), share(pr, pc)
                    out.append((s if low else 1.0 - s) * j / se)
                jl_row.append(_round(out[0]))
                jh_row.append(_round(out[1]))
            jl_rows.append(jl_row)
            jh_rows.append(jh_row)
        frames.append(FisheyeFrame(lead_hour=f.lead_hour, valid_time=utc(f.valid_time).isoformat(), j_low=jl_rows, j_high=jh_rows))
    k = rows[0]
    return FisheyeOut(run_time=utc(model_run.run_time).isoformat(), k=[k.k_tke, k.k_cis, k.k_conv],
                      elevations=ELEVATIONS, azimuths=AZIMUTHS, frames=frames)
