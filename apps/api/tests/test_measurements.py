from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from seeing_api.db import get_session_factory
from seeing_api.main import create_app
from seeing_db import Forecast, ModelRun, RunStatus, Site, User

PASSWORD = "correct horse battery"
T0 = datetime(2026, 10, 13, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def clean() -> Iterator[None]:
    def wipe() -> None:
        with get_session_factory()() as s:
            s.execute(delete(ModelRun))
            s.execute(delete(User))
            s.commit()

    wipe()
    yield
    wipe()


def client_for(email: str) -> TestClient:
    c = TestClient(create_app(static_dir="/nonexistent"), base_url="https://testserver")
    assert c.post("/api/auth/signup", json={"email": email, "password": PASSWORD}).status_code == 201
    return c


def test_upload_read_delete_measurements():
    ada = client_for("ada@example.org")
    slug = ada.post("/api/places", json={"name": "Jardin", "lat": 44.3, "lon": 5.3}).json()["slug"]
    pts = [["2026-10-13T21:00:00Z", 1.2], ["2026-10-13T21:05:00Z", 1.4], ["2026-10-14T22:00:00Z", 0.9], ["2026-10-13T21:10:00Z", 99]]
    r = ada.post(f"/api/sites/{slug}/measurements", json={"points": pts})
    assert r.json() == {"stored": 3, "rejected": 1}
    # same time again: replaced, not duplicated
    ada.post(f"/api/sites/{slug}/measurements", json={"points": [["2026-10-13T21:00:00Z", 1.3]]})
    m = ada.get(f"/api/sites/{slug}/measurements").json()
    assert m["seeing_arcsec"] == [1.3, 1.4, 0.9] and m["times"][0] == "2026-10-13T21:00:00Z"
    assert ada.request("DELETE", f"/api/sites/{slug}/measurements", params={"night": "2026-10-13"}, json={}).status_code == 204
    assert ada.get(f"/api/sites/{slug}/measurements").json()["seeing_arcsec"] == [0.9]

    bob = client_for("bob@example.org")
    assert bob.get(f"/api/sites/{slug}/measurements").status_code == 404
    assert bob.post(f"/api/sites/{slug}/measurements", json={"points": pts}).status_code == 404
    assert bob.post("/api/sites/saint-veran/measurements", json={"points": pts}).status_code == 404
    # public site: its monitor is readable by every logged-in user, still not writable
    assert bob.get("/api/sites/saint-veran/measurements").status_code == 200


def test_terms_use_the_latest_run_before_each_hour():
    ada = client_for("ada@example.org")
    slug = ada.post("/api/places", json={"name": "Jardin", "lat": 44.3, "lon": 5.3}).json()["slug"]
    with get_session_factory()() as s:
        site = s.scalar(select(Site).where(Site.slug == slug))
        for k, run_time in enumerate((T0, T0 + timedelta(hours=6))):
            run = ModelRun(run_time=run_time, status=RunStatus.success)
            s.add(run)
            s.flush()
            for lead in range(0, 12):
                s.add(Forecast(run_id=run.id, site_id=site.id, valid_time=run_time + timedelta(hours=lead), lead_hour=lead,
                               seeing_arcsec=1.0, i_tke=float(k), i_conv=0.0, i_cis=1e-14))
        s.commit()
    r = ada.get(f"/api/sites/{slug}/terms", params={"from": "2026-10-13T00:00:00Z", "to": "2026-10-14T00:00:00Z"}).json()
    assert len(r["valid_times"]) == 18
    assert r["i_tke"][:6] == [0.0] * 6 and r["i_tke"][6:] == [1.0] * 12  # from 06Z on: the 06Z run
    assert r["lead_hours"][6] == 0
