import pytest
from fastapi.testclient import TestClient

from seeing_api.main import create_app


@pytest.fixture
def spa(tmp_path):
    (tmp_path / "index.html").write_text("<!doctype html><title>Seeing the Sky</title>")
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "index-abc123.js").write_text("console.log(1)")
    (tmp_path / "favicon.svg").write_text("<svg/>")
    (tmp_path.parent / "secret.txt").write_text("nope")
    return TestClient(create_app(static_dir=tmp_path))


def test_index_served_no_cache(spa):
    r = spa.get("/")
    assert r.status_code == 200 and "Seeing the Sky" in r.text
    assert r.headers["cache-control"] == "no-cache"


def test_client_routes_fall_back_to_index(spa):
    r = spa.get("/sites/saint-veran")
    assert r.status_code == 200 and "Seeing the Sky" in r.text
    assert r.headers["content-type"].startswith("text/html")


def test_hashed_assets_long_cache(spa):
    r = spa.get("/assets/index-abc123.js")
    assert r.status_code == 200 and r.text == "console.log(1)"
    assert "immutable" in r.headers["cache-control"]
    assert spa.get("/assets/missing.js").status_code == 404
    assert spa.get("/favicon.svg").status_code == 200


def test_api_paths_never_fall_back(spa):
    r = spa.get("/api/does-not-exist")
    assert r.status_code == 404 and r.headers["content-type"].startswith("application/json")


def test_no_path_traversal(spa):
    r = spa.get("/..%2Fsecret.txt")
    assert "nope" not in r.text


def test_healthz_with_spa(spa):
    assert spa.get("/healthz").json() == {"status": "ok"}


def test_missing_static_dir_is_skipped():
    client = TestClient(create_app(static_dir="/definitely/not/here"))
    assert client.get("/").status_code == 404
    assert client.get("/healthz").status_code == 200
