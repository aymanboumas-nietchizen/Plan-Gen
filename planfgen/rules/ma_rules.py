"""
rules/ma_rules.py
=================
Moroccan Building Code (DTU) rules for residential programmes.

All rules here are pre-configured for Moroccan practice:
  - Room minimum areas follow DTU residential norms
  - Corridor minimum width: 1.20 m
  - Facade access for living rooms (sejour) and bedrooms (chambres)
  - Soft elongation penalty: ratio > 2.5 flagged as warning

Usage:
    from planfgen.rules.ma_rules import MA_RULES
    validation = validate_layout(placed, MA_RULES, W, H)
"""

from planfgen.rules.base_rules import (
    FacadeRule,
    MinAreaRule,
    MinWidthRule,
    MaxRatioRule,
    MinCorridorWidthRule,
)


MA_RULES = [
    # --- Hard rules (regulatory compliance) --------------------------------
    # Minimum areas per DTU residential norms
    MinAreaRule("chambre principale", min_area=12.0, hard=True),
    MinAreaRule("chambre",            min_area=9.0,  hard=True),
    MinAreaRule("cuisine",            min_area=6.0,  hard=True),
    MinAreaRule("sdb",                min_area=3.5,  hard=True),
    MinAreaRule("salle de bain",      min_area=3.5,  hard=True),
    MinAreaRule("wc",                 min_area=1.2,  hard=True),
    # Corridor minimum clear width
    MinCorridorWidthRule(hard=True),

    # --- Soft rules (quality guidance — penalise score but don't discard) ---
    # Minimum room widths per DTU norms
    MinWidthRule("séjour",  min_width=3.00, hard=False),
    MinWidthRule("sejour",  min_width=3.00, hard=False),
    MinWidthRule("chambre", min_width=2.70, hard=False),
    MinWidthRule("cuisine", min_width=1.80, hard=False),
    MinWidthRule("sdb",     min_width=1.70, hard=False),
    MinWidthRule("wc",      min_width=1.20, hard=False),
    # Elongated rooms are uncomfortable and hard to furnish
    MaxRatioRule(max_ratio=2.5, hard=False),
    # Living rooms and bedrooms benefit greatly from natural light / views
    FacadeRule(room_types=["séjour", "sejour", "chambre", "salon"], hard=False),
]
