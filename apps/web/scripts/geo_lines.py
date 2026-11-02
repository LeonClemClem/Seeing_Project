"""Coastlines and land borders of the map (public/geo/lines.json) from Natural Earth 1:10m (public domain,
https://www.naturalearthdata.com): ne_10m_coastline and ne_10m_admin_0_boundary_lines_land, clipped to the AROME
domain and simplified to ~300 m (the full-resolution map cells are ~2 km).

    python geo_lines.py <folder with the two .shp files> ../public/geo/lines.json
"""

import json
import struct
import sys
from pathlib import Path

from shapely.geometry import LineString, box

BOX = box(-12.5, 37.0, 16.5, 56.0)  # AROME 0.025 domain (-12..16 E, 37.5..55.4 N) with a margin
TOL = 0.003  # simplification tolerance [deg]


def polylines(shp: Path):
    """Parts of the PolyLine records (shape type 3) of an ESRI shapefile, as [(lon, lat), ...]."""
    b = shp.read_bytes()
    i = 100
    while i < len(b):
        _, words = struct.unpack(">ii", b[i : i + 8])
        rec = b[i + 8 : i + 8 + 2 * words]
        i += 8 + 2 * words
        if struct.unpack("<i", rec[:4])[0] != 3:
            continue
        nparts, npts = struct.unpack("<ii", rec[36:44])
        parts = list(struct.unpack(f"<{nparts}i", rec[44 : 44 + 4 * nparts])) + [npts]
        pts = struct.unpack(f"<{2 * npts}d", rec[44 + 4 * nparts : 44 + 4 * nparts + 16 * npts])
        for a, z in zip(parts, parts[1:]):
            yield [(pts[2 * k], pts[2 * k + 1]) for k in range(a, z)]


def layer(shp: Path) -> list[list[float]]:
    out = []
    for line in polylines(shp):
        if len(line) < 2:
            continue
        g = LineString(line).intersection(BOX)
        for part in getattr(g, "geoms", [g]):
            if part.is_empty or part.geom_type != "LineString":
                continue
            s = part.simplify(TOL, preserve_topology=False)
            xy = [round(v, 3) for p in s.coords for v in p]
            if len(xy) >= 4:
                out.append(xy)
    return out


def main(src: str, dst: str) -> None:
    d = Path(src)
    data = {
        "source": "Natural Earth 1:10m (public domain)",
        "coast": layer(d / "ne_10m_coastline.shp"),
        "borders": layer(d / "ne_10m_admin_0_boundary_lines_land.shp"),
    }
    Path(dst).write_text(json.dumps(data, separators=(",", ":")), encoding="utf-8")
    n = {k: sum(len(x) // 2 for x in v) for k, v in data.items() if k != "source"}
    print(dst, n, Path(dst).stat().st_size // 1024, "KB")


if __name__ == "__main__":
    main(*sys.argv[1:3])
