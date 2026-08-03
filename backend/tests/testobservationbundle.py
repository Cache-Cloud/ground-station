from observations.bundle import ARTIFACT_DIRECTORIES, add_bundle_session, create_observation_bundle


def test_create_observation_bundle_has_readable_name_and_manifest(tmp_path):
    bundle_dir = create_observation_bundle(
        "observation-12345678",
        {"name": "NOAA 19", "norad_id": 33591},
        tmp_path,
    )

    assert bundle_dir.name.endswith(".gsobs")
    assert bundle_dir.name.startswith("NOAA_19_")
    assert all((bundle_dir / name).is_dir() for name in ARTIFACT_DIRECTORIES)

    add_bundle_session(bundle_dir, "internal:observation-12345678:sdr-1", "sdr-1")
    manifest = (bundle_dir / "manifest.json").read_text()
    assert '"observation_id": "observation-12345678"' in manifest
    assert '"session_key": "sdr-1"' in manifest
