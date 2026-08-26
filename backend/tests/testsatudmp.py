"""SatDump TLE-cache compatibility coverage."""

import sqlite3

from tasks.satdumpprocessor import (
    _build_tle_file_from_ground_station_db,
    _count_omm_only_satellites,
)


def test_satdump_cache_excludes_omm_only_six_digit_satellites(tmp_path):
    db_path = tmp_path / "gs.db"
    output_path = tmp_path / "satdump_tles.txt"
    connection = sqlite3.connect(db_path)
    try:
        connection.execute("CREATE TABLE satellites (name TEXT, tle1 TEXT, tle2 TEXT)")
        connection.execute(
            "INSERT INTO satellites VALUES (?, ?, ?)",
            (
                "Five digit object",
                "1 25544U 98067A   25001.50000000  .00012345  00000-0  21914-3 0  9999",
                "2 25544  51.6416 247.4627 0006703 130.5360 325.0288 15.50000000999999",
            ),
        )
        connection.execute("INSERT INTO satellites VALUES (?, ?, ?)", ("OMM only", None, None))
        connection.commit()
    finally:
        connection.close()

    assert _build_tle_file_from_ground_station_db(db_path, output_path) == 1
    assert _count_omm_only_satellites(db_path) == 1
    cache = output_path.read_text()
    assert "Five digit object" in cache
    assert "OMM only" not in cache
