import math
from datetime import timedelta

import pytest

from conftest import T0, add_run
from seeing_db import RunStatus


def test_healthz_needs_no_db(client):
    assert client.get("/healthz").json() == {"status": "ok"}


def test_sites_lists_active_seeded_sites(client, session):
    r = client.get("/api/sites")
    assert r.status_code == 200
    assert r.headers["cache-control"] == "private, max-age=300"
    sites = {s["slug"]: s for s in r.json()}
    assert set(sites) == {"saint-veran", "pic-du-midi", "ohp", "cosmodrome"}
    assert sites["saint-veran"]["altitude_m"] == 2930.0
    assert sites["cosmodrome"]["altitude_m"] is None
    assert set(sites["saint-veran"]) == {"slug", "name", "lat", "lon", "altitude_m", "visibility", "owned", "k"}
    assert sites["saint-veran"]["k"] is None and sites["saint-veran"]["owned"] is False
    assert sites["ohp"]["name"] == "OHP" and sites["pic-du-midi"]["name"] == "Pic du Midi"
    assert {s: sites[s]["visibility"] for s in sites} == {
        "saint-veran": "public", "pic-du-midi": "public", "ohp": "public", "cosmodrome": "shared",
    }


def test_hidden_sites_are_not_served(client, session):
    # Copernic and Verclause are still computed by the batch but not offered on the website.
    assert client.get("/api/sites/copernic-gap/forecast").status_code == 404
    assert client.get("/api/sites/verclause/cn2").status_code == 404


def test_latest_run_404_when_no_success(client, session):
    assert client.get("/api/runs/latest").status_code == 404
    add_run(session, T0, status=RunStatus.failed)
    add_run(session, T0 + timedelta(hours=6), status=RunStatus.running)
    assert client.get("/api/runs/latest").status_code == 404
    assert client.get("/api/sites/saint-veran/forecast").status_code == 404
    assert client.get("/api/sites/saint-veran/cn2").status_code == 404


def test_latest_is_newest_success_only(client, session):
    add_run(session, T0)
    add_run(session, T0 + timedelta(hours=6), seeing=[2.0])
    add_run(session, T0 + timedelta(hours=12), status=RunStatus.failed)
    add_run(session, T0 + timedelta(hours=18), status=RunStatus.running)
    body = client.get("/api/runs/latest").json()
    assert body == {"run_time": "2026-10-13T06:00:00Z", "finished_at": "2026-10-13T09:00:00Z", "status": "success"}
    fc = client.get("/api/sites/saint-veran/forecast").json()
    assert fc["run_time"] == "2026-10-13T06:00:00Z"
    assert [p["seeing_arcsec"] for p in fc["points"]] == [2.0]


def test_explicit_run_param(client, session):
    add_run(session, T0, seeing=[1.1, 1.2])
    add_run(session, T0 + timedelta(hours=6), seeing=[2.0])
    add_run(session, T0 + timedelta(hours=12), status=RunStatus.failed)
    for run in ("2026-10-13T00:00:00Z", "2026-10-13T00:00Z", "2026-10-13T02:00:00+02:00", "2026-10-13T00:00:00"):
        r = client.get("/api/sites/saint-veran/forecast", params={"run": run})
        assert r.status_code == 200, run
        assert r.json()["run_time"] == "2026-10-13T00:00:00Z"
        assert len(r.json()["points"]) == 2
    # failed / unknown runs are invisible
    assert client.get("/api/sites/saint-veran/forecast", params={"run": "2026-10-13T12:00Z"}).status_code == 404
    assert client.get("/api/sites/saint-veran/cn2", params={"run": "2026-10-13T12:00Z"}).status_code == 404
    assert client.get("/api/sites/saint-veran/forecast", params={"run": "2025-01-01T00:00Z"}).status_code == 404
    assert client.get("/api/sites/saint-veran/forecast", params={"run": "yesterday"}).status_code == 422


def test_unknown_slug_404(client, session):
    add_run(session, T0)
    assert client.get("/api/sites/atlantis/forecast").status_code == 404
    assert client.get("/api/sites/atlantis/cn2").status_code == 404


def test_site_without_rows_returns_empty_points(client, session):
    add_run(session, T0, slug="saint-veran")
    fc = client.get("/api/sites/pic-du-midi/forecast").json()
    assert fc["points"] == [] and fc["site"]["slug"] == "pic-du-midi"


def test_forecast_shape_and_null_handling(client, session):
    add_run(session, T0, seeing=[1.0, None, math.nan])
    fc = client.get("/api/sites/saint-veran/forecast").json()
    assert fc["site"]["slug"] == "saint-veran"
    assert [p["lead_hour"] for p in fc["points"]] == [0, 1, 2]
    assert [p["seeing_arcsec"] for p in fc["points"]] == [1.0, None, None]
    assert fc["points"][1]["valid_time"] == "2026-10-13T01:00:00Z"
    assert set(fc["points"][0]) == {"lead_hour", "valid_time", "seeing_arcsec", "r0_m", "integral_cn2", "h_coulim_m",
                                    "model_altitude_m", "variables"}


def test_cn2_union_grid_padded_with_null(client, session):
    add_run(session, T0, seeing=[1.0, 1.0, 1.0])
    cn = client.get("/api/sites/saint-veran/cn2").json()
    assert cn["valid_times"] == ["2026-10-13T00:00:00Z", "2026-10-13T01:00:00Z", "2026-10-13T02:00:00Z"]
    assert cn["heights_m"] == [0.0, 100.0, 200.0]
    assert len(cn["cn2"]) == 3
    # lead 0 and 2 only have two heights -> padded with null
    assert cn["cn2"][0][2] is None and cn["cn2"][2][2] is None
    assert math.isclose(cn["cn2"][1][2], 1e-17, rel_tol=1e-5)


def test_me_reads_iap_header(client):
    r = client.get("/api/me", headers={"X-Goog-Authenticated-User-Email": "accounts.google.com:user@example.com"})
    assert r.json()["email"] == "user@example.com"
    assert client.get("/api/me").json()["email"] is None


def test_me_env(client, monkeypatch):
    monkeypatch.setenv("ENV", "prod")
    assert client.get("/api/me").json() == {"email": None, "env": "prod", "user": None}


def test_global_map(client, session):
    import zlib

    from seeing_db import MapFrame

    assert client.get("/api/map").status_code == 404
    run = add_run(session, T0)
    add_run(session, T0 + timedelta(hours=6))  # newer run without a map
    codes = bytes([0, 127, 254, 255, 10, 20])
    for lead in (20, 21):
        session.add(MapFrame(run_id=run.id, valid_time=T0 + timedelta(hours=lead), lead_hour=lead, ny=2, nx=3,
                             lat0=51.0, lon0=-5.0, dlat=-0.05, dlon=0.05, k_tke=2.0, k_cis=57.0, k_conv=0.1,
                             data=zlib.compress(codes)))
    session.commit()
    body = client.get("/api/map").json()
    assert body["run_time"] == "2026-10-13T00:00:00Z"
    assert body["grid"] == {"ny": 2, "nx": 3, "lat0": 51.0, "lon0": -5.0, "dlat": -0.05, "dlon": 0.05}
    assert [f["lead_hour"] for f in body["frames"]] == [20, 21]
    r = client.get("/api/map/frame", params={"lead": 21})
    assert r.status_code == 200 and r.content == codes
    assert client.get("/api/map/frame", params={"lead": 5}).status_code == 404


def test_fisheye_from_the_map(client, session):
    import math
    import zlib

    from seeing_api.fisheye import J_OF_CODE
    from seeing_db import MapFrame

    run = add_run(session, T0)
    ny, nx = 40, 60
    n = ny * nx
    codes = bytes([127] * n)  # uniform seeing
    extra = bytes([127] * n + [25] * n + [80] * n)  # half low (500 m), half high (8000 m)
    session.add(MapFrame(run_id=run.id, valid_time=T0 + timedelta(hours=20), lead_hour=20, ny=ny, nx=nx,
                         lat0=46.0, lon0=4.0, dlat=-0.05, dlon=0.05, k_tke=2.0, k_cis=57.0, k_conv=0.1,
                         data=zlib.compress(codes), extra=zlib.compress(extra)))
    session.commit()
    body = client.get("/api/fisheye", params={"lat": 45.0, "lon": 5.5}).json()
    assert body["k"] == [2.0, 57.0, 0.1] and body["elevations"][-1] == 90
    f = body["frames"][0]
    j = J_OF_CODE[127]
    assert f["j_low"][-1][0] + f["j_high"][-1][0] == pytest.approx(j, rel=1e-3)  # zenith
    el = body["elevations"].index(30)
    assert f["j_high"][el][9] == pytest.approx(j / 2 / math.sin(math.radians(30)), rel=1e-3)
    assert client.get("/api/fisheye", params={"lat": 30.0, "lon": 5.5}).status_code == 404


def test_week_view_stitches_main_runs(client, session):
    # 00Z (3 h), 03Z secondary (3 h), 06Z (3 h): week view = 00Z, 01Z, 02Z from 00Z, 03Z-05Z from 03Z
    # (fills the gap), 06Z-08Z from 06Z; the run view keeps the 06Z run only.
    add_run(session, T0, seeing=[1.0, 1.1, 1.2])
    add_run(session, T0 + timedelta(hours=3), seeing=[2.0, 2.1, 2.2])
    add_run(session, T0 + timedelta(hours=6), seeing=[3.0, 3.1, 3.2])
    wk = client.get("/api/sites/saint-veran/forecast", params={"view": "week"}).json()
    assert [p["seeing_arcsec"] for p in wk["points"]] == [1.0, 1.1, 1.2, 2.0, 2.1, 2.2, 3.0, 3.1, 3.2]
    run = client.get("/api/sites/saint-veran/forecast").json()
    assert [p["seeing_arcsec"] for p in run["points"]] == [3.0, 3.1, 3.2]
    cn = client.get("/api/sites/saint-veran/cn2", params={"view": "week"}).json()
    assert len(cn["valid_times"]) == 9 and cn["run_time"] == "2026-10-13T06:00:00Z"
    assert client.get("/api/sites/saint-veran/cn2", params={"view": "x"}).status_code == 422


def test_all_view_goes_back_beyond_a_week(client, session):
    add_run(session, T0 - timedelta(days=20), seeing=[0.5, 0.6])
    add_run(session, T0, seeing=[1.0, 1.1])
    wk = client.get("/api/sites/saint-veran/forecast", params={"view": "week"}).json()
    assert [p["seeing_arcsec"] for p in wk["points"]] == [1.0, 1.1]
    al = client.get("/api/sites/saint-veran/forecast", params={"view": "all"}).json()
    assert [p["seeing_arcsec"] for p in al["points"]] == [0.5, 0.6, 1.0, 1.1]
