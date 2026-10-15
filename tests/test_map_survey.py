import map_survey

XML = """<?xml version="1.0"?><map>
<group name="Land_Mil_Barracks4" pos="1000.0 50.0 1000.0" a="0"/>
<group name="Land_Mil_GuardShed" pos="1010.0 51.0 1020.0" a="0"/>
<group name="Land_Mil_Guardhouse1" pos="1030.0 52.0 990.0" a="0"/>
<group name="Land_HBarrierTower_TK" pos="1050.0 53.0 1050.0" a="0"/>
<group name="Land_Mil_ContainerWatchTower" pos="1060.0 54.0 1040.0" a="0"/>
<group name="Land_Mil_Tent_Big1_1_Desert" pos="1070.0 55.0 1010.0" a="0"/>
<group name="Land_Water_Station" pos="5000.0 10.0 5000.0" a="0"/>
<group name="Land_House_1W01" pos="9000.0 300.0 9000.0" a="0"/>
</map>"""


def groups(tmp_path):
    p = tmp_path / "mapgrouppos.xml"
    p.write_text(XML)
    return map_survey.load_groups(p)


def test_load_groups_reads_name_and_xyz(tmp_path):
    g = groups(tmp_path)
    assert g[0] == ("Land_Mil_Barracks4", 1000.0, 50.0, 1000.0)
    assert len(g) == 8


def test_survey_clusters_by_role_with_min_count(tmp_path):
    s = map_survey.survey(groups(tmp_path))
    assert len(s["military"]) == 1 and s["military"][0]["count"] == 6
    assert 1000 <= s["military"][0]["x"] <= 1070
    assert s["water"][0]["count"] == 1                  # water needs only one structure
    assert s["town"] == []                              # one house is not a town


def test_high_ground_is_highest_cells_first(tmp_path):
    s = map_survey.survey(groups(tmp_path))
    assert s["high_ground"][0]["y"] == 300.0


def test_bounds_round_up_to_1024(tmp_path):
    assert map_survey.bounds(groups(tmp_path)) == [0, 0, 9216, 9216]


def test_ground_y_uses_nearest_structure(tmp_path):
    g = groups(tmp_path)
    assert map_survey.ground_y(g, 1001.0, 1001.0) == 50.0
    assert map_survey.ground_y(g, 3000.0, 3000.0) == 0.0     # nothing within 150 m
