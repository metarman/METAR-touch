#!/usr/bin/env python3

import json
import math
import urllib.parse
import urllib.request
from pathlib import Path
from datetime import datetime, timezone

BASE = (
    "https://services6.arcgis.com/ssFJjBXIUyZDrSYZ/"
    "ArcGIS/rest/services/Class_Airspace/FeatureServer/0/query"
)

TOLERANCE = 0.002
PAGE_SIZE = 100


def perpendicular_distance(point, start, end):
    x, y = point
    x1, y1 = start
    x2, y2 = end

    if x1 == x2 and y1 == y2:
        return math.hypot(x - x1, y - y1)

    dx = x2 - x1
    dy = y2 - y1

    return abs(
        dy * x -
        dx * y +
        x2 * y1 -
        y2 * x1
    ) / math.hypot(dx, dy)


def simplify_line(points, tolerance):
    if len(points) <= 2:
        return points

    keep = {0, len(points) - 1}
    stack = [(0, len(points) - 1)]

    while stack:
        first, last = stack.pop()

        max_distance = 0.0
        index = None

        for i in range(first + 1, last):
            d = perpendicular_distance(
                points[i],
                points[first],
                points[last]
            )

            if d > max_distance:
                max_distance = d
                index = i

        if index is not None and max_distance > tolerance:
            keep.add(index)
            stack.append((first, index))
            stack.append((index, last))

    return [points[i] for i in sorted(keep)]


def simplify_ring(ring):
    if len(ring) < 5:
        return ring

    points = ring[:-1] if ring[0] == ring[-1] else ring

    simplified = simplify_line(
        points,
        TOLERANCE
    )

    if len(simplified) < 3:
        simplified = points

    simplified = [
        [round(p[0], 5), round(p[1], 5)]
        for p in simplified
    ]

    if simplified[0] != simplified[-1]:
        simplified.append(simplified[0])

    return simplified


def simplify_geometry(geometry):
    if not geometry:
        return geometry

    gtype = geometry.get("type")
    coords = geometry.get("coordinates")

    if gtype == "Polygon":
        geometry["coordinates"] = [
            simplify_ring(ring)
            for ring in coords
        ]

    elif gtype == "MultiPolygon":
        geometry["coordinates"] = [
            [
                simplify_ring(ring)
                for ring in polygon
            ]
            for polygon in coords
        ]

    return geometry


def fetch_page(cls, offset):
    params = {
        "where": f"CLASS='{cls}'",
        "outFields":
            "NAME,IDENT,ICAO_ID,CLASS,UPPER_DESC,LOWER_DESC",

        "geometry": "-126,23,-65,51",
        "geometryType": "esriGeometryEnvelope",

        "inSR": "4326",
        "outSR": "4326",

        "spatialRel": "esriSpatialRelIntersects",

        "returnGeometry": "true",

        "resultOffset": str(offset),
        "resultRecordCount": str(PAGE_SIZE),

        "orderByFields": "OBJECTID",

        "f": "geojson",
    }

    url = BASE + "?" + urllib.parse.urlencode(params)

    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "METAR-touch/1.0"
        }
    )

    with urllib.request.urlopen(
        req,
        timeout=180
    ) as response:
        return json.load(response)


features = []

for cls in ("B", "C", "D"):

    offset = 0

    while True:
        print(
            f"Downloading Class {cls}, "
            f"offset {offset}"
        )

        data = fetch_page(
            cls,
            offset
        )

        if "error" in data:
            raise RuntimeError(
                data["error"]
            )

        page = data.get(
            "features",
            []
        )

        if not page:
            break

        for feature in page:
            feature["geometry"] = (
                simplify_geometry(
                    feature.get("geometry")
                )
            )

            features.append(feature)

        if len(page) < PAGE_SIZE:
            break

        offset += PAGE_SIZE


output = {
    "type": "FeatureCollection",

    "features": features,

    "metadata": {
        "generated_utc":
            datetime.now(
                timezone.utc
            ).isoformat(),

        "source":
            "FAA Class Airspace FeatureServer; "
            "classes B/C/D",

        "simplification_tolerance":
            TOLERANCE,
    },
}


encoded = json.dumps(
    output,
    separators=(",", ":")
)

Path(
    "airspace_snapshot.json"
).write_text(
    encoded,
    encoding="utf-8"
)


size_mb = len(
    encoded.encode("utf-8")
) / 1024 / 1024

print(
    f"Wrote {len(features)} "
    f"FAA B/C/D polygons"
)

print(
    f"airspace_snapshot.json "
    f"size: {size_mb:.1f} MB"
)
