"""The Rhino side of the bridge.

`planfgen_component.py` is a GhPython script, not a module of the engine: it
imports `Rhino.Geometry`, which only exists inside Rhino, so nothing here is
imported by `planfgen` and nothing here is covered by the test suite. What IS
tested is the document it consumes — see `document/gh.py` and `tests/test_gh.py`.
"""
