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
    FAA's NASR landing page contains Preview, Current and archive
    cycle links. Discover every YYYY-MM-DD cycle on the page,
    then choose the newest one whose effective date is today or
    earlier.

    That automatically ignores the future Preview cycle.
    """

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

    html = fetch(cycle_page).decode(
        "utf-8",
        "replace"
    )

    m = re.search(
        r'href=["\']([^"\']*APT_CSV\.zip)["\']',
        html,
        re.I
    )

    if not m:
        raise RuntimeError(
            "Could not find FAA APT_CSV.zip "
            "on current NASR page."
        )

    return urljoin(
        cycle_page,
        unescape(m.group(1))
    )


def clean(value):
    return (value or "").strip()


def titleish(value):
    """
    FAA city and airport names are frequently uppercase.
    Make those normal mixed case for the map.

    Existing mixed-case text is left alone.
    """

    value = clean(value)

    if value and value.upper() == value:
        return value.title()

    return value


def main():

    cycle_page, cycle = current_cycle_page()

    zip_url = apt_zip_url(
        cycle_page
    )

    print(
        "FAA NASR cycle:",
        cycle
    )

    print(
        "APT source:",
        zip_url
    )


    # -----------------------------
    # DOWNLOAD CURRENT FAA APT DATA
    # -----------------------------

    zip_bytes = fetch(
        zip_url
    )


    with zipfile.ZipFile(
        io.BytesIO(zip_bytes)
    ) as zf:

        candidates = [
            name
            for name in zf.namelist()
            if name.upper().endswith(
                "APT_BASE.CSV"
            )
        ]

        if not candidates:
            raise RuntimeError(
                "APT_BASE.csv not found "
                "inside FAA APT ZIP."
            )

        csv_name = candidates[0]

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


    airports = []

    seen = set()


    # -----------------------------
    # BUILD SMALL LOCAL DATABASE
    # -----------------------------

    for row in rows:

        status = clean(
            row.get("ARPT_STATUS")
        ).upper()


        /*
        FAA normally represents open
        facilities with O.

        Accept the text variants too
        in case the CSV representation
        changes.
        */
