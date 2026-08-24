"""L8 — `document/`: getting a plan off the screen and onto a page.

Only the SVG preview exists so far. DXF, IFC and the Grasshopper bridge are
later sessions; the preview is here early because a plan you cannot look at is
a plan you cannot check.
"""

from planfgen.document.preview import PALETTE, to_svg

__all__ = ["PALETTE", "to_svg"]
