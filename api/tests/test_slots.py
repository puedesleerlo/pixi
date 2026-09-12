import pytest
from pixie.slots import SLOTS, SLOT_ORDER, apply_move, auto_assign, design_row, validate_version, free_slots

E = {
    "fig": {"id": "fig", "label": "Figure", "size_class": "large"},
    "fig2": {"id": "fig2", "label": "Figure 2", "size_class": "large"},
    "star": {"id": "star", "label": "Star", "size_class": "small"},
    "sun": {"id": "sun", "label": "Sun", "size_class": "small"},
    "cup": {"id": "cup", "label": "Cup", "size_class": "small"},
    "moon": {"id": "moon", "label": "Moon", "size_class": "small"},
    "grp": {"id": "grp", "label": "Celestial", "size_class": None},
}


def test_slot_table():
    assert SLOTS == {"center": 1.0, "top": 0.7, "bottom": 0.7, "left": 0.5, "right": 0.5}
    assert SLOT_ORDER[0] == "center"


def test_auto_assign_first_large_takes_center_in_pick_order():
    out = auto_assign([E["star"], E["fig"], E["sun"], E["fig2"]])
    assert out == [{"element_id": "star", "slot": "top"}, {"element_id": "fig", "slot": "center"},
                   {"element_id": "sun", "slot": "bottom"}, {"element_id": "fig2", "slot": "left"}]


def test_auto_assign_without_large_leaves_center_empty_max_4():
    out = auto_assign([E["star"], E["sun"], E["cup"], E["moon"]])
    assert [o["slot"] for o in out] == ["top", "bottom", "left", "right"]
    with pytest.raises(ValueError):
        auto_assign([E["star"], E["sun"], E["cup"], E["moon"], E["star"]])


@pytest.mark.parametrize("els,msg", [
    ([{"element_id": "fig", "slot": "center"}], "at least 2"),
    ([{"element_id": k, "slot": s} for k, s in zip(["fig", "star", "sun", "cup", "moon", "fig2"], SLOT_ORDER + ["top"])], "at most 5"),
    ([{"element_id": "star", "slot": "center"}, {"element_id": "sun", "slot": "top"}], "small"),
    ([{"element_id": "fig", "slot": "center"}, {"element_id": "fig", "slot": "top"}], "already"),
    ([{"element_id": "fig", "slot": "center"}, {"element_id": "sun", "slot": "center"}], "twice"),
    ([{"element_id": "fig", "slot": "middle"}, {"element_id": "sun", "slot": "top"}], "unknown slot"),
    ([{"element_id": "nope", "slot": "center"}, {"element_id": "sun", "slot": "top"}], "unknown element"),
    ([{"element_id": "grp", "slot": "top"}, {"element_id": "sun", "slot": "bottom"}], "group"),
])
def test_validate_version_rejects(els, msg):
    with pytest.raises(ValueError, match=msg):
        validate_version(els, E)


def test_design_row():
    v = [{"element_id": "fig", "slot": "center"}, {"element_id": "star", "slot": "left"}]
    row = design_row(v, {"fig": 0, "star": 1, "sun": 2}, 3)
    assert row.tolist() == [1.0, 0.5, 0.0]


BASE = [{"element_id": "fig", "slot": "center"}, {"element_id": "star", "slot": "top"}, {"element_id": "sun", "slot": "left"}]


def test_apply_move_add_auto_and_explicit():
    out = apply_move(BASE, {"type": "add", "element_id": "cup"}, E)
    assert {"element_id": "cup", "slot": "bottom"} in out and len(out) == 4
    out = apply_move(BASE, {"type": "add", "element_id": "cup", "to_slot": "right"}, E)
    assert {"element_id": "cup", "slot": "right"} in out
    with pytest.raises(ValueError, match="taken"):
        apply_move(BASE, {"type": "add", "element_id": "cup", "to_slot": "top"}, E)
    with pytest.raises(ValueError, match="already"):
        apply_move(BASE, {"type": "add", "element_id": "star"}, E)
    small_only = [{"element_id": "star", "slot": "top"}, {"element_id": "sun", "slot": "bottom"},
                  {"element_id": "cup", "slot": "left"}, {"element_id": "moon", "slot": "right"}]
    with pytest.raises(ValueError):  # only center is free and fig2 is large → ok; a small one → no slot
        apply_move(small_only, {"type": "add", "element_id": "grp"}, E)
    assert apply_move(small_only, {"type": "add", "element_id": "fig2"}, E)[-1]["slot"] == "center"


def test_apply_move_remove_swap_move():
    out = apply_move(BASE, {"type": "remove", "element_id": "sun"}, E)
    assert len(out) == 2 and all(o["element_id"] != "sun" for o in out)
    with pytest.raises(ValueError, match="at least"):
        apply_move(out, {"type": "remove", "element_id": "star"}, E)
    out = apply_move(BASE, {"type": "swap", "element_id": "star", "to_element_id": "cup"}, E)
    assert {"element_id": "cup", "slot": "top"} in out and len(out) == 3
    with pytest.raises(ValueError, match="small"):
        apply_move(BASE, {"type": "swap", "element_id": "fig", "to_element_id": "cup"}, E)
    out = apply_move(BASE, {"type": "move", "element_id": "sun", "to_slot": "right"}, E)
    assert {"element_id": "sun", "slot": "right"} in out
    with pytest.raises(ValueError, match="taken"):
        apply_move(BASE, {"type": "move", "element_id": "sun", "to_slot": "top"}, E)
    with pytest.raises(ValueError, match="small"):
        apply_move([{"element_id": "star", "slot": "top"}, {"element_id": "sun", "slot": "left"}],
                   {"type": "move", "element_id": "sun", "to_slot": "center"}, E)
    with pytest.raises(ValueError):
        apply_move(BASE, {"type": "teleport", "element_id": "sun"}, E)
    assert free_slots(BASE) == ["bottom", "right"]
    assert BASE == [{"element_id": "fig", "slot": "center"}, {"element_id": "star", "slot": "top"}, {"element_id": "sun", "slot": "left"}]  # never mutated
