from datetime import UTC, datetime, timedelta

import pandas as pd

from seeing_batch import arome

RUN = datetime(2026, 10, 13, 0, tzinfo=UTC)


def test_cycle_urls():
    urls = arome.cycle_urls(RUN, "HP1")
    assert len(urls) == 9
    assert urls[-1].endswith("/2026-10-13T00:00:00Z/arome/0025/HP1/arome__0025__HP1__49H51H__2026-10-13T00:00:00Z.grib2")


def test_latest_complete_cycle_falls_back_to_the_previous_main_cycle(monkeypatch):
    latest = RUN + timedelta(hours=6)
    monkeypatch.setattr(arome.Arome0025, "get_latest_forecast_time", classmethod(lambda cls, paquet: pd.Timestamp(latest)))
    # The 06Z cycle misses IP4: 00Z, never the secondary 03Z.
    monkeypatch.setattr(arome, "are_downloadable", lambda urls: not ("IP4" in urls[0] and "T06" in urls[0]))
    assert arome.latest_complete_cycle() == RUN


def test_latest_complete_cycle_never_secondary(monkeypatch):
    # the latest published cycle is the secondary 09Z: the main 06Z is computed
    monkeypatch.setattr(
        arome.Arome0025, "get_latest_forecast_time", classmethod(lambda cls, paquet: pd.Timestamp(RUN + timedelta(hours=9)))
    )
    monkeypatch.setattr(arome, "are_downloadable", lambda urls: True)
    assert arome.latest_complete_cycle() == RUN + timedelta(hours=6)


def test_download_and_extract_streams_and_deletes(monkeypatch, tmp_path):
    seen = []

    def fake_url_to_file(url, tempdir, num_retries=1):
        p = tmp_path / "dl" / ".part" / url.rsplit("/", 1)[1].replace(":", "-")
        p.write_bytes(b"x" * 10)
        return p

    class FakeExtractor:
        def __init__(self, sites, forecast_hours):
            pass

        def add_file(self, path, package):
            # never more than 2 files (current + prefetched) on disk
            assert len(list((tmp_path / "dl").glob("arome__*"))) <= 2
            seen.append((package, path.name))

        def result(self):
            from seeing_core import ExtractedRun
            return ExtractedRun(run_time=RUN, slugs=[], data={}, surface_h={}, grid_points={})

    monkeypatch.setattr(arome.Arome0025, "_url_to_file", staticmethod(fake_url_to_file))
    monkeypatch.setattr(arome, "RunExtractor", FakeExtractor)
    run, stats = arome.download_and_extract(RUN, [], tmp_path / "dl")
    assert len(seen) == 6 * 9 and stats["files"] == 54
    assert [p for p, _ in seen][:9] == ["SP2"] * 9
    assert list((tmp_path / "dl").glob("arome__*")) == []
