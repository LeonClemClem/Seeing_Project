"""`seeing-dev-seed`: insert a SYNTHETIC successful model run for local development / screenshots.

The numbers are plausible but fake: a diurnal boundary layer (turbulent by day, calm at night),
a wandering jet-stream layer near the tropopause and site-dependent baseline quality.
Re-running for the same run time replaces that run (idempotent).
"""

import argparse
import math
import random
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from seeing_db import Cn2Profile, Forecast, ModelRun, RunStatus, Site, make_engine, make_session_factory

LEAD_HOURS = range(0, 52)  # 0..51 inclusive -> 52 points
HEIGHTS_M = [float(h) for h in range(0, 15_001, 100)]  # display grid, AGL
WAVELENGTH = 500e-9
RAD_TO_ARCSEC = 206_264.806
K2 = (2 * math.pi / WAVELENGTH) ** 2

# Mountain observatories get calmer skies than lowland club sites.
BASELINE = {"saint-veran": 0.65, "pic-du-midi": 0.7}


def default_run_time(now: datetime) -> datetime:
    """Most recent 00/06/12/18 UTC cycle that would plausibly be processed by now (~3h latency)."""
    t = now - timedelta(hours=3)
    return t.replace(hour=t.hour - t.hour % 6, minute=0, second=0, microsecond=0)


def daylight(valid_time: datetime, lon: float) -> float:
    """0 at night, up to 1 around local solar noon (crude, good enough for fake data)."""
    solar_hour = (valid_time.hour + valid_time.minute / 60 + lon / 15) % 24
    raw = max(0.0, math.cos((solar_hour - 13.5) / 24 * 2 * math.pi)) ** 1.5 * 1.6 - 0.15
    return min(1.0, max(0.0, raw))


def seeing_to_r0(seeing: float) -> float:
    return 0.98 * WAVELENGTH / (seeing / RAD_TO_ARCSEC)


def r0_to_integral(r0: float) -> float:
    return r0 ** (-5 / 3) / (0.423 * K2)


def cn2_profile(integral: float, bl_height: float, jet_height: float, jet_share: float) -> list[float]:
    """Profile shape (BL exponential + gaussian jet layer + weak free atmosphere) scaled to `integral`."""
    shape = []
    for h in HEIGHTS_M:
        bl = math.exp(-h / max(bl_height / 2.5, 80.0))
        jet = jet_share * math.exp(-(((h - jet_height) / 900.0) ** 2)) * 0.25
        free = 0.004 * math.exp(-h / 6000.0)
        shape.append(bl + jet + free)
    total = sum(shape) * 100.0  # 100 m steps
    return [min(1e-13, max(1e-18, s * integral / total)) for s in shape]


def seed(session: Session, run_time: datetime) -> int:
    session.execute(delete(ModelRun).where(ModelRun.run_time == run_time))
    run = ModelRun(run_time=run_time, status=RunStatus.running, started_at=run_time + timedelta(hours=2))
    session.add(run)
    session.flush()

    sites = session.scalars(select(Site).where(Site.active.is_(True)).order_by(Site.id)).all()
    for site in sites:
        rng = random.Random(f"{site.slug}-{run_time.isoformat()}")
        base = BASELINE.get(site.slug, 1.0 + rng.uniform(0.0, 0.3))
        jet_phase = rng.uniform(0, 2 * math.pi)
        drift = 0.0
        for lead in LEAD_HOURS:
            valid = run_time + timedelta(hours=lead)
            day = max(0.0, daylight(valid, site.lon))
            # Slow synoptic variation (a front / jet passing) + red noise.
            jet_share = 0.5 + 0.5 * math.sin(lead / 9.0 + jet_phase)
            drift = 0.8 * drift + rng.gauss(0, 0.08)
            seeing = base + 1.4 * day + 0.6 * jet_share * (1 - day) + drift
            seeing = min(3.2, max(0.55, seeing))
            r0 = seeing_to_r0(seeing)
            integral = r0_to_integral(r0)
            bl_height = 250 + 1900 * day + rng.uniform(-50, 120)
            session.add(
                Forecast(
                    run_id=run.id,
                    site_id=site.id,
                    valid_time=valid,
                    lead_hour=lead,
                    seeing_arcsec=round(seeing, 3),
                    r0_m=r0,
                    integral_cn2=integral,
                    h_coulim_m=round(bl_height, 0),
                    model_altitude_m=site.altitude_m or 1000.0,
                )
            )
            session.add(
                Cn2Profile(
                    run_id=run.id,
                    site_id=site.id,
                    valid_time=valid,
                    lead_hour=lead,
                    heights_m=HEIGHTS_M,
                    cn2=cn2_profile(integral, bl_height, 10_500 + 800 * math.sin(lead / 7.0 + jet_phase), jet_share),
                )
            )
    session.flush()
    run.status = RunStatus.success
    run.finished_at = min(datetime.now(UTC), run_time + timedelta(hours=3))
    session.commit()
    return len(sites)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--run-time", type=datetime.fromisoformat, help="AROME cycle (UTC), default: latest plausible")
    args = parser.parse_args()
    run_time = args.run_time or default_run_time(datetime.now(UTC))
    if run_time.tzinfo is None:
        run_time = run_time.replace(tzinfo=UTC)
    with make_session_factory(make_engine())() as session:
        n = seed(session, run_time)
    print(f"Seeded synthetic run {run_time.isoformat()} for {n} sites ({len(LEAD_HOURS)} hours each)")


if __name__ == "__main__":
    main()
