#!/usr/bin/env python3

import csv
import io
import json
import re
import sys
import urllib.request
import zipfile

from datetime import date
from html import unescape
from urllib.parse import urljoin


LANDING = (
    "https://www.faa.gov/air_traffic/flight_info/"
    "aeronav/Aero_Data/NASR_Subscription/"
)

UA = "METAR-touch/1.0 (+https://github.com/metarman/METAR-touch)"


def fetch(url):
    req = urllib.request.Request(
        url,
        headers={"User-Agent": UA}
    )

    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def clean(value):
    return (value or "").strip()


def get_first(row, names):
    for name in names:
        value = clean(row.get(name))
        if value:
            return value
    return ""


def current_cycle_page():
    html = fetch(LANDING).decode(
        "utf-8",
        "replace"
    )

    dates = set(
        re.findall(
            r'NASR_Subscription/(\d{4}-\d{2}-\d{2})/?',
            html,
            re.I
        )
    )

    if not dates:
        dates = set(
            re.findall(
                r'href=["\'][^"\']*(\d{4}-\d{2}-\d{2})/?["\']',
                html,
                re.I
            )
        )

    today = date.today()

    eligible = []

    for s in dates:
        try:
            d = date.fromisoformat(s)
        except ValueError:
            continue

        if d <= today:
            eligible.append((d, s))

    if not eligible:
        raise RuntimeError(
            "Could not identify current FAA NASR cycle."
        )

    _, cycle = max(eligible)

    return (
        urljoin(
            LANDING,
            cycle + "/"
        ),
        cycle
    )


def nav_zip_url(cycle_page):
    html = fetch(
        cycle_page
    ).decode(
        "utf-8",
        "replace"
    )

    patterns = [
        r'href=["\']([^"\']*NAV_CSV\.zip)["\']',
        r'href=["\']([^"\']*NAV[^"\']*CSV[^"\']*\.zip)["\']'
    ]

    for pattern in patterns:
        matches = re.findall(
            pattern,
            html,
            re.I
        )

        for match in matches:
            url = urljoin(
                cycle_page,
                unescape(match)
            )

            if "NAV" in url.upper():
                return url

    raise RuntimeError(
        "Could not find FAA NAV CSV ZIP."
    )


def main():
    cycle_page, cycle = (
        current_cycle_page()
    )

    zip_url = nav_zip_url(
        cycle_page
    )

    print(
        "FAA NASR cycle:",
        cycle
    )

    print(
        "NAV source:",
        zip_url
    )

    zip_bytes = fetch(
        zip_url
    )

    with zipfile.ZipFile(
        io.BytesIO(zip_bytes)
    ) as zf:

        names = zf.namelist()

        candidates = [
            name
            for name in names
            if name.upper().endswith(
                "NAV_BASE.CSV"
            )
        ]

        if not candidates:
            candidates = [
                name
                for name in names
                if name.upper().endswith(".CSV")
                and "NAV_BASE" in name.upper()
            ]

        if not candidates:
            raise RuntimeError(
                "NAV_BASE.csv not found inside ZIP."
            )

        csv_name = candidates[0]

        print(
            "Reading:",
            csv_name
        )

        raw = (
            zf.read(csv_name)
            .decode(
                "utf-8-sig",
                "replace"
            )
        )

    rows = csv.DictReader(
        io.StringIO(raw)
    )

    if not rows.fieldnames:
        raise RuntimeError(
            "FAA NAV CSV contains no header."
        )

    print(
        "FAA NAV columns:",
        ", ".join(
            rows.fieldnames[:25]
        ),
        "..."
    )

    wanted_types = {
        "VOR",
        "VOR/DME",
        "VORTAC",
        "TACAN"
    }

    navaids = []
    seen = set()

    for row in rows:

        ident = get_first(
            row,
            [
                "NAV_ID",
                "NAVAID_ID",
                "FACILITY_ID"
            ]
        ).upper()

        nav_type = get_first(
            row,
            [
                "NAV_TYPE",
                "NAVAID_TYPE",
                "FACILITY_TYPE"
            ]
        ).upper()

        if not ident:
            continue

        if nav_type not in wanted_types:
            continue

        status = get_first(
            row,
            [
                "NAV_STATUS",
                "STATUS"
            ]
        ).upper()

        if status:
            if (
                "DECOMMISSION" in status
                or "OUT OF SERVICE" in status
                or "UNUSABLE" in status
            ):
                continue

        public_use = get_first(
            row,
            [
                "PUBLIC_USE_FLAG",
                "PUBLIC_USE"
            ]
        ).upper()

        if public_use in {
            "N",
            "NO"
        }:
            continue

        lat_text = get_first(
            row,
            [
                "LAT_DECIMAL",
                "LATITUDE_DECIMAL",
                "LATITUDE"
            ]
        )

        lon_text = get_first(
            row,
            [
                "LONG_DECIMAL",
                "LON_DECIMAL",
                "LONGITUDE_DECIMAL",
                "LONGITUDE"
            ]
        )

        try:
            lat = float(lat_text)
            lon = float(lon_text)
        except (TypeError, ValueError):
            continue

        if not (-90 <= lat <= 90):
            continue

        if not (-180 <= lon <= 180):
            continue

        name = get_first(
            row,
            [
                "NAME",
                "NAV_NAME",
                "NAVAID_NAME"
            ]
        )

        city = get_first(
            row,
            [
                "CITY",
                "ASSOC_CITY"
            ]
        )

        state = get_first(
            row,
            [
                "STATE_CODE",
                "STATE"
            ]
        ).upper()

        frequency = get_first(
            row,
            [
                "FREQ",
                "FREQUENCY",
                "NAV_FREQ"
            ]
        )

        key = (
            ident,
            nav_type,
            round(lat, 5),
            round(lon, 5)
        )

        if key in seen:
            continue

        seen.add(key)

        record = {
            "id": ident,
            "type": nav_type,
            "name": name,
            "city": city,
            "state": state,
            "lat": round(lat, 6),
            "lon": round(lon, 6)
        }

        if frequency:
            record["freq"] = frequency

        navaids.append(record)

    navaids.sort(
        key=lambda n: (
            n["id"],
            n["type"]
        )
    )

    if len(navaids) < 300:
        raise RuntimeError(
            f"Parsed only {len(navaids)} VOR/TACAN facilities; "
            "refusing to overwrite last known-good snapshot."
        )

    output = {
        "source": "FAA NASR NAV_BASE",
        "cycle": cycle,
        "count": len(navaids),
        "navaids": navaids
    }

    with open(
        "navaids_snapshot.json",
        "w",
        encoding="utf-8"
    ) as f:
        json.dump(
            output,
            f,
            separators=(",", ":"),
            ensure_ascii=False
        )

    print(
        f"Wrote navaids_snapshot.json "
        f"with {len(navaids):,} VOR/VORTAC/TACAN facilities."
    )


if __name__ == "__main__":
    try:
        main()

    except Exception as e:
        print(
            "ERROR:",
            e,
            file=sys.stderr
        )
        sys.exit(1)
