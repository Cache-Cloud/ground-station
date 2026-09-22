# Copyright (c) 2026 Efstratios Goudelis

from common.targetkey import build_target_key, normalize_target_key


def test_target_key_normalizes_case_whitespace_and_underscores():
    assert (
        build_target_key(target_type="mission", command="  Parker\t Solar__Probe  ")
        == "mission:parker_solar_probe"
    )
    assert build_target_key(target_type="body", body_id=" Mars ") == "body:mars"
    assert normalize_target_key(" MISSION:Voyager\u00a0\u00a01 ") == "mission:voyager_1"


def test_target_key_rejects_legacy_and_unknown_namespaces():
    assert normalize_target_key("missioncmd:Voyager 1") is None
    assert normalize_target_key("satellite:25544") is None
    assert normalize_target_key("mission:") is None
