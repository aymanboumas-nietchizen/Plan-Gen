"""
tests/test_rules.py
Unit tests for rules/base_rules.py and rules/ma_rules.py.
"""

import json, os, pytest
from planfgen.core.geometry  import Rect
from planfgen.rules.base_rules import (
    MinAreaRule, MaxRatioRule, MinCorridorWidthRule, FacadeRule,
    validate_layout, RuleResult,
)


# ---------------------------------------------------------------------------
# MinAreaRule
# ---------------------------------------------------------------------------

def test_min_area_hard_fail():
    placed = {"Chambre 1": Rect(0, 0, 2, 3, "Chambre 1")}  # 6 m² < 9 m²
    rule = MinAreaRule("chambre", min_area=9.0, hard=True)
    result = validate_layout(placed, [rule])
    assert result["valid"] is False
    assert len(result["errors"]) == 1

def test_min_area_hard_pass():
    placed = {"Chambre 1": Rect(0, 0, 3, 4, "Chambre 1")}  # 12 m² >= 9 m²
    rule = MinAreaRule("chambre", min_area=9.0, hard=True)
    result = validate_layout(placed, [rule])
    assert result["valid"] is True
    assert len(result["errors"]) == 0

def test_min_area_case_insensitive_match():
    placed = {"CUISINE": Rect(0, 0, 2, 2, "CUISINE")}  # 4 m² < 6 m²
    rule = MinAreaRule("cuisine", min_area=6.0, hard=True)
    result = validate_layout(placed, [rule])
    assert result["valid"] is False

def test_min_area_soft_doesnt_discard():
    placed = {"Chambre 1": Rect(0, 0, 2, 3, "Chambre 1")}  # 6 m² < 9 m²
    rule = MinAreaRule("chambre", min_area=9.0, hard=False)
    result = validate_layout(placed, [rule])
    assert result["valid"] is True       # soft → still valid
    assert result["score_penalty"] > 0  # but penalised

def test_min_area_unmatched_room_type_passes():
    placed = {"SDB": Rect(0, 0, 2, 2, "SDB")}  # 4 m² — but rule is for "chambre"
    rule = MinAreaRule("chambre", min_area=9.0, hard=True)
    result = validate_layout(placed, [rule])
    assert result["valid"] is True


# ---------------------------------------------------------------------------
# MaxRatioRule
# ---------------------------------------------------------------------------

def test_max_ratio_fail_soft():
    placed = {"NarrowRoom": Rect(0, 0, 10, 1, "NarrowRoom")}  # ratio=10 > 2.5
    rule = MaxRatioRule(max_ratio=2.5, hard=False)
    result = validate_layout(placed, [rule])
    assert result["valid"] is True       # soft
    assert len(result["warnings"]) == 1

def test_max_ratio_pass():
    placed = {"Room": Rect(0, 0, 4, 3, "Room")}  # ratio=1.33 < 2.5
    rule = MaxRatioRule(max_ratio=2.5, hard=False)
    result = validate_layout(placed, [rule])
    assert len(result["warnings"]) == 0


# ---------------------------------------------------------------------------
# MinCorridorWidthRule
# ---------------------------------------------------------------------------

def test_corridor_too_narrow():
    placed = {"Couloir": Rect(0, 0, 5, 0.8, "Couloir")}  # min(5,0.8)=0.8 < 1.2
    rule = MinCorridorWidthRule(hard=True)
    result = validate_layout(placed, [rule])
    assert result["valid"] is False

def test_corridor_ok():
    placed = {"Couloir": Rect(0, 0, 5, 1.5, "Couloir")}  # min(5,1.5)=1.5 >= 1.2
    rule = MinCorridorWidthRule(hard=True)
    result = validate_layout(placed, [rule])
    assert result["valid"] is True

def test_couloir_name_variations():
    """Hall and dégagement should also be checked."""
    placed = {"Hall entrée": Rect(0, 0, 5, 0.9, "Hall entrée")}
    rule = MinCorridorWidthRule(hard=True)
    result = validate_layout(placed, [rule])
    assert result["valid"] is False


# ---------------------------------------------------------------------------
# FacadeRule
# ---------------------------------------------------------------------------

def test_facade_rule_pass():
    placed = {"Séjour": Rect(0, 0, 4, 4, "Séjour")}  # touches left wall
    rule = FacadeRule(room_types=["séjour"], hard=False)
    result = validate_layout(placed, [rule], W=12, H=9)
    assert len(result["warnings"]) == 0

def test_facade_rule_fail_soft():
    placed = {"Séjour": Rect(4, 3, 3, 3, "Séjour")}  # centre of envelope
    rule = FacadeRule(room_types=["séjour"], hard=False)
    result = validate_layout(placed, [rule], W=12, H=9)
    assert result["valid"] is True
    assert len(result["warnings"]) == 1


# ---------------------------------------------------------------------------
# validate_layout — aggregate behaviour
# ---------------------------------------------------------------------------

def test_validate_empty_rules_always_valid():
    placed = {"Any": Rect(0, 0, 5, 5, "Any")}
    result = validate_layout(placed, [])
    assert result["valid"] is True
    assert result["score_penalty"] == 0.0

def test_penalty_accumulates_per_soft_violation():
    placed = {
        "R1": Rect(0, 0, 10, 1, "R1"),  # ratio=10, warning
        "R2": Rect(0, 2, 10, 1, "R2"),  # ratio=10, warning
    }
    rule = MaxRatioRule(max_ratio=2.5, hard=False)
    result = validate_layout(placed, [rule])
    assert result["score_penalty"] > 0
    assert result["score_penalty"] <= 1.0


# ---------------------------------------------------------------------------
# MA_RULES integration
# ---------------------------------------------------------------------------

def test_ma_rules_apartment_fixture():
    """7-room apartment at correct sizes should have 0 hard violations."""
    path = os.path.join(os.path.dirname(__file__), "fixtures", "apartment_7rooms.json")
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    from planfgen.core.generator import generate_layout
    from planfgen.rules.ma_rules  import MA_RULES
    prog = data["programme"]
    adjs = [tuple(a) for a in data["adjacencies"]]
    W, H = 12.0, 9.0
    # Try several seeds, expect at least some to be valid
    valid_count = 0
    for seed in range(20):
        placed = generate_layout(prog, adjs, W, H, seed=seed)
        result = validate_layout(placed, MA_RULES, W=W, H=H)
        if result["valid"]:
            valid_count += 1
    assert valid_count > 0, "No valid layouts found across 20 seeds with MA_RULES"
