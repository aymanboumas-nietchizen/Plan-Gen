# -*- coding: utf-8 -*-
"""Export the families and types loaded in the open Revit document to JSON.

Open the agency template (.rte) or any project in Revit 2025, then click
PLANFGEN > Familles > Exporter familles. A JSON file is written next to the
document (or to the Desktop for an unsaved template) and its path shown.

Only names and a few dimensions leave Revit: category, family, type, and for
doors, windows and walls the width / height / thickness parameters when the
type carries them. That list is what PLANFGEN's family-key mapping table is
built from (ARCHITECTURE.md section 0, "The output target").

Written for both pyRevit engines (IronPython 2.7 and CPython 3): no f-strings.
"""
import io
import json
import os

from Autodesk.Revit.DB import (
    BuiltInCategory,
    BuiltInParameter,
    ElementType,
    FilteredElementCollector,
    UnitUtils,
    UnitTypeId,
)
from pyrevit import forms, revit

DOC = revit.doc

CATEGORIES = [
    ("portes", BuiltInCategory.OST_Doors),
    ("fenetres", BuiltInCategory.OST_Windows),
    ("mobilier", BuiltInCategory.OST_Furniture),
    ("mobilier_systeme", BuiltInCategory.OST_FurnitureSystems),
    ("agencement", BuiltInCategory.OST_Casework),
    ("sanitaires", BuiltInCategory.OST_PlumbingFixtures),
    ("equipements", BuiltInCategory.OST_SpecialityEquipment),
    ("murs", BuiltInCategory.OST_Walls),
    ("sols", BuiltInCategory.OST_Floors),
    ("escaliers", BuiltInCategory.OST_Stairs),
    ("garde_corps", BuiltInCategory.OST_StairsRailing),
    ("pieces_etiquettes", BuiltInCategory.OST_RoomTags),
]

DIMENSIONS = [
    ("largeur", BuiltInParameter.DOOR_WIDTH),
    ("hauteur", BuiltInParameter.DOOR_HEIGHT),
    ("largeur_fenetre", BuiltInParameter.WINDOW_WIDTH),
    ("hauteur_fenetre", BuiltInParameter.WINDOW_HEIGHT),
    ("epaisseur", BuiltInParameter.WALL_ATTR_WIDTH_PARAM),
    ("largeur_type", BuiltInParameter.FAMILY_WIDTH_PARAM),
    ("hauteur_type", BuiltInParameter.FAMILY_HEIGHT_PARAM),
]


def metres(value):
    return round(UnitUtils.ConvertFromInternalUnits(value, UnitTypeId.Meters), 4)


def name_of(element):
    try:
        return element.Name
    except Exception:
        return ""


def family_of(element_type):
    try:
        return element_type.FamilyName or ""
    except Exception:
        return ""


def dimensions_of(element_type):
    out = {}
    for key, bip in DIMENSIONS:
        param = element_type.get_Parameter(bip)
        if param is not None and param.HasValue:
            try:
                out[key] = metres(param.AsDouble())
            except Exception:
                pass
    return out


def export():
    result = {
        "source": DOC.Title,
        "revit": DOC.Application.VersionNumber,
        "is_template": DOC.IsFamilyDocument is False and DOC.PathName.lower().endswith(".rte"),
        "categories": {},
    }
    for label, category in CATEGORIES:
        types = (
            FilteredElementCollector(DOC)
            .OfCategory(category)
            .WhereElementIsElementType()
            .ToElements()
        )
        rows = []
        for element_type in types:
            if not isinstance(element_type, ElementType):
                continue
            rows.append(
                {
                    "famille": family_of(element_type),
                    "type": name_of(element_type),
                    "dimensions": dimensions_of(element_type),
                }
            )
        rows.sort(key=lambda r: (r["famille"], r["type"]))
        result["categories"][label] = rows
    return result


def target_path():
    folder = os.path.dirname(DOC.PathName) if DOC.PathName else ""
    if not folder:
        folder = os.path.join(os.path.expanduser("~"), "Desktop")
    stem = os.path.splitext(os.path.basename(DOC.PathName or DOC.Title))[0]
    return os.path.join(folder, stem + "_familles_planfgen.json")


data = export()
path = target_path()
with io.open(path, "w", encoding="utf-8") as handle:
    text = json.dumps(data, indent=2, ensure_ascii=False)
    if not isinstance(text, type(u"")):
        text = text.decode("utf-8")
    handle.write(text)
counts = ", ".join(
    "{0} {1}".format(len(rows), label) for label, rows in data["categories"].items() if rows
)
forms.alert("Familles exportees : {0}\n\n{1}".format(counts, path), title="PLANFGEN")
