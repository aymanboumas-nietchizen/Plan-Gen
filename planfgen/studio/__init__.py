"""The Streamlit studio.

    streamlit run planfgen/studio/app.py --server.headless true

`render.py` draws the intermediate stages; `app.py` is the page. The stage
selector exists so L1 and L3 can be seen side by side and told apart.
"""

from planfgen.studio.render import partition_svg, topology_svg

__all__ = ["partition_svg", "topology_svg"]
