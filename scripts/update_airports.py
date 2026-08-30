        # FAA normally represents open facilities with O.
        # Accept text variants too in case the representation changes.

        if (
            status
            and status not in {
                "O",
                "OPEN",
                "ACTIVE"
            }
        ):
            continue


        faa = clean(
            row.get("ARPT_ID")
        ).upper()

        icao = clean(
            row.get("ICAO_ID")
        ).upper()


        if not faa and not icao:
            continue


        try:
            lat = float(
                clean(
                    row.get(
                        "LAT_DECIMAL"
                    )
                )
            )

            lon = float(
                clean(
                    row.get(
                        "LONG_DECIMAL"
                    )
                )
            )

        except (
            TypeError,
            ValueError
        ):
            continue


        city = titleish(
            row.get("CITY")
        )

        name = titleish(
            row.get("ARPT_NAME")
        )

        state = clean(
            row.get("STATE_CODE")
        ).upper()

        country = clean(
            row.get("COUNTRY_CODE")
        ).upper() or "US"

        facility_use = clean(
            row.get(
                "FACILITY_USE_CODE"
            )
        ).upper()

        site_type = clean(
            row.get(
                "SITE_TYPE_CODE"
            )
        ).upper()


        elevation = None

        for field in (
            "ELEV",
            "ELEVATION"
        ):

            value = clean(
                row.get(field)
            )

            if not value:
                continue

            try:
                elevation = float(
                    value
                )
            except ValueError:
                pass

            break


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
            record["elev"] = round(
                elevation,
                1
            )


        if facility_use:
            record["use"] = (
                facility_use
            )


        if site_type:
            record["type"] = (
                site_type
            )


        key = (
            icao
            or faa
        )


        if key in seen:
            continue


        seen.add(key)

        airports.append(
            record
        )


    airports.sort(
        key=lambda a:
        (
            a.get("icao")
            or a.get("faa")
            or ""
        )
    )


    output = {
        "source":
            "FAA NASR APT_BASE",

        "cycle":
            cycle,

        "count":
            len(airports),

        "airports":
            airports
    }


    # Important:
    # only write the replacement file
    # after the FAA download and parse
    # have completed successfully.

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
        "Wrote airports_snapshot.json "
        f"with {len(airports):,} "
        "active facilities."
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
