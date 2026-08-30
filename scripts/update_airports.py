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


def current_cycle_page():
    """
    Discover FAA NASR cycle links and choose the newest
    cycle whose effective date is today or earlier.
    """

    html = fetch(LANDING).decode("utf-8", "replace")

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
            "Could not identify the current FAA NASR cycle."
        )

    _, cycle = max(eligible)

    page = urljoin(
        LANDING,
        cycle + "/"
    )

    return page, cycle


def apt_zip_url(cycle_page):
    """
    Find the Airports and Other Landing Facilities CSV ZIP
    on the current FAA cycle page.
    """

    html = fetch(cycle_page).decode("utf-8", "replace")

    patterns = [
        r'href=["\']([^"\']*APT_CSV\.zip)["\']',
        r'href=["\']([^"\']*APT[^"\']*CSV[^"\']*\.zip)["\']'
    ]

    for pattern in patterns:
        m = re.search(pattern, html, re.I)

        if m:
            return urljoin(
                cycle_page,
                unescape(m.group(1))
            )

    raise RuntimeError(
        "Could not find FAA airport CSV ZIP on current NASR page."
    )


def clean(value):
    return (value or "").strip()


def titleish(value):
    """
    FAA city and airport names are often all uppercase.
    Convert those to mixed case while leaving already
    mixed-case names unchanged.
    """

    value = clean(value)

    if value and value.upper() == value:
        return value.title()

    return value


def get_first(row, names):
    """
    Return the first non-empty field found among several
    possible FAA column-name variants.
    """

    for name in names:
        value = clean(row.get(name))

        if value:
            return value

    return ""


def main():
    cycle_page, cycle = current_cycle_page()

    zip_url = apt_zip_url(cycle_page)

    print("FAA NASR cycle:", cycle)
    print("APT source:", zip_url)

    zip_bytes = fetch(zip_url)

    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:

        names = zf.namelist()

        candidates = [
            name
            for name in names
            if name.upper().endswith("APT_BASE.CSV")
        ]

        if not candidates:
            candidates = [
                name
                for name in names
                if name.upper().endswith(".CSV")
                and "APT" in name.upper()
            ]

        if not candidates:
            raise RuntimeError(
                "FAA airport CSV not found inside ZIP."
            )

        csv_name = candidates[0]

        print("Reading:", csv_name)

        raw = (
            zf.read(csv_name)
            .decode("utf-8-sig", "replace")
        )

    rows = csv.DictReader(io.StringIO(raw))

    if not rows.fieldnames:
        raise RuntimeError(
            "FAA airport CSV contains no header row."
        )

    print(
        "FAA columns:",
        ", ".join(rows.fieldnames[:20]),
        "..."
    )

    airports = []
    seen = set()

    for row in rows:

        status = get_first(
            row,
            [
                "ARPT_STATUS",
                "AIRPORT_STATUS_CODE",
                "STATUS_CODE",
                "STATUS"
            ]
        ).upper()

        # Keep open/active airports.
        # If FAA changes or omits the status field,
        # absence of a value does not cause deletion.
        if (
            status
            and status not in {
                "O",
                "OPEN",
                "ACTIVE"
            }
        ):
            continue

        faa = get_first(
            row,
            [
                "ARPT_ID",
                "ARPT_IDNT",
                "FAA_ID",
                "LOCAL_CODE"
            ]
        ).upper()

        icao = get_first(
            row,
            [
                "ICAO_ID",
                "ICAO_IDENTIFIER",
                "ICAO_CODE"
            ]
        ).upper()

        if not faa and not icao:
            continue

        lat_text = get_first(
            row,
            [
                "LAT_DECIMAL",
                "LAT_DECIMAL_DEGREE",
                "LATITUDE_DECIMAL",
                "LATITUDE"
            ]
        )

        lon_text = get_first(
            row,
            [
                "LONG_DECIMAL",
                "LONG_DECIMAL_DEGREE",
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

        # Sanity check coordinates.
        if not (-90 <= lat <= 90):
            continue

        if not (-180 <= lon <= 180):
            continue

        city = titleish(
            get_first(
                row,
                [
                    "CITY",
                    "ASSOC_CITY",
                    "CITY_NAME"
                ]
            )
        )

        name = titleish(
            get_first(
                row,
                [
                    "ARPT_NAME",
                    "AIRPORT_NAME",
                    "FACILITY_NAME"
                ]
            )
        )

        state = get_first(
            row,
            [
                "STATE_CODE",
                "STATE",
                "STATE_POST_OFFICE_CODE"
            ]
        ).upper()

        country = get_first(
            row,
            [
                "COUNTRY_CODE",
                "COUNTRY"
            ]
        ).upper()

        if not country:
            country = "US"

        facility_use = get_first(
            row,
            [
                "FACILITY_USE_CODE",
                "FACILITY_USE",
                "USE_CODE"
            ]
        ).upper()

        site_type = get_first(
            row,
            [
                "SITE_TYPE_CODE",
                "SITE_TYPE",
                "FACILITY_TYPE"
            ]
        ).upper()

        elevation = None

        elev_text = get_first(
            row,
            [
                "ELEV",
                "ELEVATION",
                "ELEVATION_FT",
                "ARPT_ELEV"
            ]
        )

        if elev_text:
            try:
                elevation = float(elev_text)
            except ValueError:
                pass

        record = {
            "faa": faa,
            "icao": icao,
            "city": city,
            "name": name,
            "state": state,
            "country": country,
            "lat": round(lat, 6),
            "lon": round(lon, 6)
        }

        if elevation is not None:
            record["elev"] = round(elevation, 1)

        if facility_use:
            record["use"] = facility_use

        if site_type:
            record["type"] = site_type

        key = icao or faa

        if key in seen:
            continue

        seen.add(key)
        airports.append(record)

    airports.sort(
        key=lambda a: (
            a.get("icao")
            or a.get("faa")
            or ""
        )
    )

    if len(airports) < 1000:
        raise RuntimeError(
            f"Parsed only {len(airports)} airports; "
            "refusing to overwrite the last known-good snapshot."
        )

    output = {
        "source": "FAA NASR",
        "cycle": cycle,
        "count": len(airports),
        "airports": airports
    }

    # Write only after the download and parse have succeeded.
    with open(
        "airports_snapshot.json",
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
        f"Wrote airports_snapshot.json "
        f"with {len(airports):,} airports."
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
