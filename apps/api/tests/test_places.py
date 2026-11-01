from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from seeing_api.db import get_session_factory
from seeing_api.main import create_app
from seeing_db import Forecast, ModelRun, RunStatus, Site, User, UserRole

PASSWORD = "Correct horse battery 7"


@pytest.fixture(autouse=True)
def no_users() -> Iterator[None]:
    def wipe() -> None:
        with get_session_factory()() as s:
            s.execute(delete(ModelRun))
            s.execute(delete(User))  # their places too (ON DELETE CASCADE)
            s.commit()

    wipe()
    yield
    wipe()


def client_for(email: str) -> TestClient:
    c = TestClient(create_app(static_dir="/nonexistent"), base_url="https://testserver")
    assert c.post("/api/auth/signup", json={"email": email, "password": PASSWORD}).status_code == 201
    return c


def test_create_list_update_archive_restore_place():
    ada = client_for("ada@example.org")
    r = ada.post("/api/places", json={"name": " Jardin ", "lat": 44.30, "lon": 5.30})
    assert r.status_code == 201
    p = r.json()
    assert p["name"] == "Jardin" and p["visibility"] == "private" and p["owned"] is True
    assert p["k"] == [2.0, 57.0, 0.1]  # starting K: the global map K
    mine = {s["slug"]: s for s in ada.get("/api/sites").json()}
    assert mine[p["slug"]]["owned"] and mine["saint-veran"]["k"] is None

    r = ada.patch(f"/api/places/{p['slug']}", json={"k_tke": 4.5, "shared": True})
    assert r.status_code == 200 and r.json()["k"] == [4.5, 57.0, 0.1] and r.json()["visibility"] == "shared"
    assert ada.patch(f"/api/places/{p['slug']}", json={"k_cis": 151}).status_code == 422

    assert ada.delete(f"/api/places/{p['slug']}").status_code == 415  # CSRF guard: JSON only
    assert ada.request("DELETE", f"/api/places/{p['slug']}", json={}).status_code == 204  # archived, not deleted
    assert p["slug"] not in {s["slug"] for s in ada.get("/api/sites").json()}
    assert [s["slug"] for s in ada.get("/api/places/archived").json()] == [p["slug"]]
    assert ada.post(f"/api/places/{p['slug']}/restore", json={}).status_code == 200
    assert p["slug"] in {s["slug"] for s in ada.get("/api/sites").json()}
    assert ada.get("/api/places/archived").json() == []


def test_domain_is_checked():
    ada = client_for("ada@example.org")
    assert ada.post("/api/places", json={"name": "Bretagne", "lat": 48.2, "lon": -3.0}).status_code == 201
    assert ada.post("/api/places", json={"name": "Maroc", "lat": 31.6, "lon": -8.0}).status_code == 422


def test_private_and_shared_places_seen_by_others():
    ada, bob = client_for("ada@example.org"), client_for("bob@example.org")
    priv = ada.post("/api/places", json={"name": "Secret", "lat": 45.0, "lon": 6.0}).json()
    pub = ada.post("/api/places", json={"name": "Col", "lat": 45.2, "lon": 6.2, "shared": True}).json()
    seen = {s["slug"]: s for s in bob.get("/api/sites").json()}
    assert priv["slug"] not in seen
    s = seen[pub["slug"]]
    assert s["name"] == "Lieu partagé" and s["k"] is None and not s["owned"] and s["altitude_m"] is None
    assert s["cells"] is None  # the cells around the place would give its exact position away
    import math
    d = math.hypot((s["lat"] - 45.2) * 111.2, (s["lon"] - 6.2) * 111.32 * math.cos(math.radians(45.2)))
    assert 4.9 <= d <= 11.1
    assert bob.get(f"/api/sites/{priv['slug']}/forecast").status_code == 404
    assert bob.patch(f"/api/places/{pub['slug']}", json={"name": "x"}).status_code == 404
    anon = TestClient(create_app(static_dir="/nonexistent"), base_url="https://testserver")
    assert anon.post("/api/places", json={"name": "x", "lat": 45, "lon": 6}).status_code == 401


def test_place_limit_and_admin():
    ada = client_for("ada@example.org")
    for i in range(5):
        assert ada.post("/api/places", json={"name": f"L{i}", "lat": 45.0, "lon": 6.0 + i / 10}).status_code == 201
    assert ada.post("/api/places", json={"name": "L5", "lat": 45.0, "lon": 6.6}).status_code == 409
    # an archived place does not count; restoring it needs a free slot again
    first = ada.get("/api/sites").json()
    slug0 = next(s["slug"] for s in first if s.get("owned"))
    assert ada.request("DELETE", f"/api/places/{slug0}", json={}).status_code == 204
    assert ada.post("/api/places", json={"name": "L5", "lat": 45.0, "lon": 6.6}).status_code == 201
    assert ada.post(f"/api/places/{slug0}/restore", json={}).status_code == 409
    with get_session_factory()() as s:
        s.scalar(select(User)).role = UserRole.admin
        s.commit()
    assert ada.post("/api/places", json={"name": "L6", "lat": 45.0, "lon": 6.7}).status_code == 201
    sites = {s["slug"]: s for s in ada.get("/api/sites").json()}
    assert sites["saint-veran"]["k"] == [5.17, 41.1, 0.1]  # the administrator sees the curated K


def test_archiving_a_place_keeps_its_forecasts():
    from datetime import UTC, datetime

    ada = client_for("ada@example.org")
    p = ada.post("/api/places", json={"name": "Jardin", "lat": 44.3, "lon": 5.3}).json()
    with get_session_factory()() as s:
        site = s.scalar(select(Site).where(Site.slug == p["slug"]))
        run = ModelRun(run_time=datetime(2026, 10, 13, tzinfo=UTC), status=RunStatus.success)
        s.add(run)
        s.flush()
        s.add(Forecast(run_id=run.id, site_id=site.id, valid_time=run.run_time, lead_hour=0, seeing_arcsec=1.0))
        s.commit()
    assert ada.request("DELETE", f"/api/places/{p['slug']}", json={}).status_code == 204
    with get_session_factory()() as s:
        assert s.scalar(select(Forecast)) is not None
        assert s.scalar(select(Site).where(Site.slug == p["slug"])).active is False
