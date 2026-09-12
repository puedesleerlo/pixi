import math
import numpy as np
from pixie.metrics import d_axes, d_embed, d_total, maker_score, fidelity, RADIUS


def test_d_axes_bounds():
    assert d_axes([0]*8, [0]*8) == 0.0
    assert abs(d_axes([-3]*8, [3]*8) - 1.0) < 1e-12
    assert abs(d_axes([0]*8, [3]+[0]*7) - 3/(6*math.sqrt(8))) < 1e-12


def test_d_embed():
    e = np.zeros(384); e[0] = 1
    f = np.zeros(384); f[1] = 1
    assert d_embed(e, e) == 0.0
    assert abs(d_embed(e, -e) - 1.0) < 1e-12
    assert abs(d_embed(e, f) - 0.5) < 1e-12
    assert d_embed(e, np.zeros(384)) == 0.5


def test_d_total_weighting_and_radius():
    r = d_total([0]*8, [0]*8)
    assert r["d_embed"] is None and r["d_total"] == 0.0 and r["inside_radius"]
    e = np.zeros(384); e[0] = 1
    f = np.zeros(384); f[1] = 1
    r = d_total([0]*8, [3]+[0]*7, e, f)
    da = 3/(6*math.sqrt(8))
    assert abs(r["d_total"] - (0.6*da + 0.4*0.5)) < 1e-12
    assert r["inside_radius"] == (r["d_total"] <= RADIUS)
    r2 = d_total([0]*8, [3]+[0]*7, e, f, cfg={"w_axes": 1.0, "w_embed": 0.0, "radius": 0.1})
    assert abs(r2["d_total"] - da) < 1e-12 and r2["inside_radius"] is False


def test_maker_score():
    assert maker_score([0.1, 0.1])["points"] is None
    assert maker_score([0.1, 0.1, 0.5, 0.5])["points"] == 3      # f = 0.5
    assert maker_score([0.1, 0.1, 0.1, 0.1])["points"] == 1      # f = 1
    assert maker_score([0.9, 0.9, 0.9, 0.9, 0.1])["points"] == 0  # f = 0.2
    assert maker_score([0.1, 0.1, 0.1, 0.9])["points"] == 3      # f = 0.75 inclusive
    assert maker_score([0.1, 0.9, 0.9, 0.9])["points"] == 3      # f = 0.25 inclusive
    s = maker_score([0.1, 0.9, 0.9, 0.9], cfg={"radius": 0.05})
    assert s["points"] == 0 and s["n"] == 4 and s["needs"] == 3


def test_fidelity():
    assert fidelity([]) is None
    assert abs(fidelity([0.2, 0.4]) - 0.7) < 1e-12


# ----------------------------------------------------------------------------- v4 relay metrics
def test_gaps_paired_shift_bet_landed():
    from pixie.metrics import gaps, paired_shift, bet_hit, landed, LANDING_F
    g = gaps([3, 0, 0, 0, 0, 0, 0, 0], [[1, 0, 0, 0, 0, 0, 0, 0], [0, 2, 0, 0, 0, 0, 0, 0]])
    assert g.tolist() == [2.5, -1.0, 0, 0, 0, 0, 0, 0]
    assert gaps([1] * 8, []).tolist() == [0.0] * 8
    prev = {"a": [0] * 8, "b": [1] * 8, "c": [0] * 8}
    cur = {"a": [1] * 8, "b": [2] * 8, "d": [3] * 8}
    d, n = paired_shift(prev, cur)
    assert n == 2 and d.tolist() == [1.0] * 8
    assert paired_shift({"a": [0] * 8}, {"b": [0] * 8}) == (None, 0)
    assert bet_hit(1.0, 2.0) and bet_hit(-0.5, -0.1)
    assert not bet_hit(0.4, 2.0) and not bet_hit(-1.0, 2.0) and not bet_hit(1.0, 0.0) and not bet_hit(0.0, 1.0)
    assert landed(LANDING_F, 2) and landed(0.95, 5)
    assert not landed(0.79, 5) and not landed(0.9, 1) and not landed(None, 5)
