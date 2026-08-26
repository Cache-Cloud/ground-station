"""Six-digit OMM coverage at the tracking boundary."""

from datetime import datetime, timezone

from orbits import CentralBody, get_propagation_input
from tracking.satellite import get_satellite_az_el_from_propagation

OMM_PAYLOAD = {
    "OBJECT_NAME": "New catalogue object",
    "OBJECT_ID": "2025-001A",
    "EPOCH": "2025-01-01T12:00:00.000000",
    "MEAN_MOTION": "15.50000000",
    "ECCENTRICITY": "0.0006703",
    "INCLINATION": "51.6416",
    "RA_OF_ASC_NODE": "247.4627",
    "ARG_OF_PERICENTER": "130.5360",
    "MEAN_ANOMALY": "325.0288",
    "EPHEMERIS_TYPE": "0",
    "CLASSIFICATION_TYPE": "U",
    "NORAD_CAT_ID": "100000",
    "ELEMENT_SET_NO": "999",
    "REV_AT_EPOCH": "12345",
    "BSTAR": "0.00021914",
    "MEAN_MOTION_DOT": "0.00012345",
    "MEAN_MOTION_DDOT": "0.0",
}


def test_tracking_azimuth_and_elevation_accept_omm_without_tle():
    satellite = {
        "norad_id": 100000,
        "name": "New catalogue object",
        "orbit_format": "omm",
        "orbit_payload": OMM_PAYLOAD,
    }
    propagation_input = get_propagation_input(satellite, central_body=CentralBody.EARTH)

    azimuth, elevation = get_satellite_az_el_from_propagation(
        37.9838,
        23.7275,
        propagation_input,
        datetime(2026, 8, 26, tzinfo=timezone.utc),
    )

    assert isinstance(azimuth, float)
    assert isinstance(elevation, float)
