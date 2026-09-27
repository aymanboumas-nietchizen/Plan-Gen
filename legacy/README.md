# legacy — PLANFGEN v1

This is the v1 engine, preserved exactly as it was at the point v2 began. It
authored room polygons and reconstructed walls afterwards, which is why it
produced an organigramme rather than a plan; `ARCHITECTURE.md` §1 records the
measurements. It is kept here only so v2 output can be A/B compared against it
on the same fixtures, and it is never imported by v2 code — nothing under
`planfgen/` may reference anything under `legacy/`.

`PLANFGEN_project_brief_2.md` is the v1 project brief. It prescribes soft
constraints and room polygons as primary; v2 reverses both. Kept for history.
