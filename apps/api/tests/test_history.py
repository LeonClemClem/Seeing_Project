from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from seeing_api.db import get_session_factory
from seeing_api.main import create_app
from seeing_db import ModelRun, SiteHistory, User, UserRole

PASSWORD = "correct horse battery"
HIST = {"nom": "Drôme", "K": [3.94, 49.7, 0.1], "episodes": [{"a": "2026-09-18T18:09", "b": "2026-09-19T04:20",
        "prevu": [["2026-09-18T19:00", 4.14]], "mediane": [["2026-09-18T19:00", 5.0]], "brut": [["2026-09-18T18:39", 5.5]]}],
        "paires": [["2026-09-18T19:00", 4.14, 5.0, True]], "integ": [["2026-09-18T19:00", 1.5e-12, 2.5e-14, 0.0]]}


@pytest.fixture(autouse=True)
def clean() -> Iterator[None]:
    def wipe() -> None:
        with get_session_factory()() as s:
            s.execute(delete(ModelRun))
            s.execute(delete(SiteHistory))
            s.execute(delete(User))
            s.commit()

    wipe()
    yield
    wipe()


def client_for(email: str, role: UserRole = UserRole.user) -> TestClient:
    c = TestClient(create_app(static_dir="/nonexistent"), base_url="https://testserver")
    assert c.post("/api/auth/signup", json={"email": email, "password": PASSWORD}).status_code == 201
    if role != UserRole.user:
        with get_session_factory()() as s:
            s.scalar(select(User).where(User.email == email)).role = role
            s.commit()
    return c


def test_history_upload_and_visibility():
    adm, bob = client_for("adm@example.org", UserRole.admin), client_for("bob@example.org")
    assert bob.put("/api/admin/sites/ohp/history", json=HIST).status_code == 403
    assert adm.put("/api/admin/sites/ohp/history", json=HIST).json() == {"site": "ohp", "episodes": 1, "pairs": 1}
    full = adm.get("/api/sites/ohp/history").json()
    assert full["integ"] and full["K"] == [3.94, 49.7, 0.1]
    pub = bob.get("/api/sites/ohp/history").json()
    assert pub["paires"] == HIST["paires"] and "K" not in pub and "integ" not in pub
    # hidden sites: administrator only
    adm.put("/api/admin/sites/seeing-monitor-5/history", json=HIST)
    assert bob.get("/api/sites/seeing-monitor-5/history").status_code == 404
    assert adm.get("/api/sites/seeing-monitor-5/history").status_code == 200
    assert bob.get("/api/sites/saint-veran/history").status_code == 404


def test_forecast_import_keeps_batch_rows():
    adm = client_for("adm@example.org", UserRole.admin)
    run = {"run_time": "2026-10-14T00:00:00Z", "hours": [[0, 100.0, 0.0, 0.0, 1e-14], [1, 90.0, 1e-13, 0.0, 2e-14]]}
    r = adm.post("/api/admin/sites/ohp/forecasts", json={"runs": [run]}).json()
    assert r == {"site": "ohp", "new_runs": 1, "rows": 2, "kept_existing": 0, "too_recent_runs": 0}
    again = adm.post("/api/admin/sites/ohp/forecasts", json={"runs": [run]}).json()
    assert again["rows"] == 0 and again["kept_existing"] == 2
    fc = adm.get("/api/sites/ohp/forecast", params={"run": "2026-10-14T00:00Z"}).json()
    assert [p["lead_hour"] for p in fc["points"]] == [0, 1] and fc["points"][1]["seeing_arcsec"] > 0
    terms = adm.get("/api/sites/ohp/terms", params={"from": "2026-10-14T00:00:00Z", "to": "2026-10-15T00:00:00Z"}).json()
    assert terms["i_tke"] == [0.0, 1e-13]
    late = {"run_time": "2026-10-20T00:00:00Z", "hours": [[0, 100.0, 0.0, 0.0, 1e-14]]}
    assert adm.post("/api/admin/sites/ohp/forecasts", json={"runs": [late]}).json()["too_recent_runs"] == 1  # newer than every stored run: skipped


def test_cn2_import_for_the_week_view():
    adm = client_for("adm@example.org", UserRole.admin)
    body = {"heights_m": [10.0, 110.0, 210.0], "runs": [{"run_time": "2026-10-14T00:00:00Z",
            "hours": [[1, [1e-15, None, 1e-17]], [2, [2e-15, 1e-16, None]], [3, [1e-15]]]}]}
    r = adm.post("/api/admin/sites/ohp/cn2", json=body).json()
    assert r == {"site": "ohp", "profiles": 2, "kept_existing": 0, "too_recent_runs": 0}  # wrong length skipped
    cn = adm.get("/api/sites/ohp/cn2", params={"run": "2026-10-14T00:00Z"}).json()
    assert cn["heights_m"] == [10.0, 110.0, 210.0]
    row = cn["cn2"][0]  # stored as REAL (float32)
    assert row[1] is None and row[0] == pytest.approx(1e-15, rel=1e-6) and row[2] == pytest.approx(1e-17, rel=1e-6)
