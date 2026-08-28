"""The Streamlit studio.

    streamlit run planfgen/studio/app.py --server.headless true

`render.py` draws the intermediate stages; `seed.py` turns the typed programme
into a tree and says what that tree will be; `app.py` is the page. The stage
selector exists so L1 and L3 can be seen side by side and told apart.
"""

from planfgen.studio.render import partition_svg, topology_svg
from planfgen.studio.seed import SpineNote, seed_tree, spine_note

__all__ = ["SpineNote", "partition_svg", "seed_tree", "spine_note", "topology_svg"]
