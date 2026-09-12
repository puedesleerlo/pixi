import numpy as np
from pixie.effects import edit_effects


def _v(vid, card, v, elements, edit=None):
    return {"id": vid, "card_id": card, "v": v, "elements": elements, "edit": edit}


def _r(vid, reader, axes):
    return {"version_id": vid, "reader_id": reader, "axes": axes}


def test_add_and_remove_effects_recover_planted_vector():
    w = np.array([2.0, -1.0, 0.5, 0, 0, 0, 0, 1.0])
    base = [{"element_id": "fig", "slot": "center"}, {"element_id": "sun", "slot": "top"}]
    added = base + [{"element_id": "star", "slot": "left"}]           # salience 0.5
    versions = [_v("v0", "c1", 0, base), _v("v1", "c1", 1, added, {"type": "add", "element_id": "star"}),
                _v("u0", "c2", 0, added), _v("u1", "c2", 1, base, {"type": "remove", "element_id": "star"})]
    readings = []
    for k in range(3):
        b = np.zeros(8) + k
        readings += [_r("v0", f"p{k}", b.tolist()), _r("v1", f"p{k}", (b + 0.5 * w).tolist())]
        readings += [_r("u0", f"q{k}", b.tolist()), _r("u1", f"q{k}", (b - 0.5 * w).tolist())]
    readings.append(_r("v1", "lonely", [3] * 8))  # unpaired reader is ignored
    eff = edit_effects(versions, readings)
    assert set(eff) == {"star"} and eff["star"]["n_edits"] == 2 and eff["star"]["n_pairs"] == 6
    assert np.allclose(eff["star"]["mean_effect"], w)


def test_swap_and_move_effects():
    w_in, w_out = np.array([1.0] * 8), np.array([0.0, 2.0] + [0.0] * 6)
    base = [{"element_id": "fig", "slot": "center"}, {"element_id": "out", "slot": "top"}]
    swapped = [{"element_id": "fig", "slot": "center"}, {"element_id": "in", "slot": "top"}]
    versions = [_v("v0", "c", 0, base), _v("v1", "c", 1, swapped, {"type": "swap", "element_id": "out", "to_element_id": "in"})]
    readings = [_r("v0", "p", [0] * 8), _r("v1", "p", (0.7 * (w_in - w_out)).tolist())]
    raw = edit_effects(versions, readings)
    assert np.allclose(raw["in"]["mean_effect"], w_in - w_out) and np.allclose(raw["out"]["mean_effect"], w_out - w_in)
    corrected = edit_effects(versions, readings, coef={"in": w_in, "out": w_out})
    assert np.allclose(corrected["in"]["mean_effect"], w_in) and np.allclose(corrected["out"]["mean_effect"], w_out)
    # move: center (1.0) → left (0.5) on element fig with W = w_in: shift = (0.5-1.0) * w_in
    moved = [{"element_id": "fig", "slot": "left"}, {"element_id": "out", "slot": "top"}]
    versions = [_v("v0", "c", 0, base), _v("v1", "c", 1, moved, {"type": "move", "element_id": "fig", "to_slot": "left"})]
    readings = [_r("v0", "p", [0] * 8), _r("v1", "p", (-0.5 * w_in).tolist())]
    eff = edit_effects(versions, readings)
    assert np.allclose(eff["fig"]["mean_effect"], w_in)
    # a move between equal-salience slots contributes nothing
    moved2 = [{"element_id": "fig", "slot": "center"}, {"element_id": "out", "slot": "bottom"}]
    versions = [_v("v0", "c", 0, base), _v("v1", "c", 1, moved2, {"type": "move", "element_id": "out", "to_slot": "bottom"})]
    assert edit_effects(versions, readings) == {}
