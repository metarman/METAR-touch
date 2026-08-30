#!/usr/bin/env python3

import json
import urllib.parse
import urllib.request
from pathlib import Path
from datetime import datetime, timezone

BASE = (
    "https://services6.arcgis.com/ssFJjBXIUyZDrSYZ/"
    "ArcGIS/rest/services/Class_Airspace/FeatureServer/0/query"
)

features = []

for cls in ("B", "C", "D"):

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
        "f": "geojson",
    }

    url = BASE + "?" + urllib.parse.urlencode(params)

    req = urllib.request.Request(
        url,
        headers={"User-Agent": "METAR-touch/1.0"}
    )

    with urllib.request.urlopen(
        req,
        timeout=60
    ) as response:
        data = json.load(response)

    if "error" in data:
        raise RuntimeError(data["error"])

    features.extend(data.get("features", []))


output = {
    "type": "FeatureCollection",
    "features": features,
    "metadata": {
        "generated_utc":
            datetime.now(timezone.utc).isoformat(),
        "source":
            "FAA Class Airspace FeatureServer; classes B/C/D",
    },
}

Path("airspace_snapshot.json").write_text(
    json.dumps(output, separators=(",", ":")),
    encoding="utf-8",
)

print(
    f"Wrote {len(features)} FAA B/C/D polygons"
)
