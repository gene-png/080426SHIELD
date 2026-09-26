# 2026-09-26: the ZT discarded-target disclosure agrees in number with the codes it lists (#452)

Branch `track2/zt-target-disclosure-number`, from `main` at `c39e6c8`.

- **Both surfaces, in one change**, as #452 requires. The client's PDF
  (`zt/exporters.py::_gap_plan_caption`) and the dashboard
  (`lib/dashboards/zt.ts::targetNote`) say "applied to that row instead" for
  one code, and "those rows" for more.
- **Tests.**
  - A singular Python test pins the caption.
  - A singular parity pin in `zt.test.ts` is transcribed from the Python.
  - The fully-overridden-branch test used one code and asserted "those rows",
    pinning the defect. Its expected string now says "that row"; that is the
    only change to it.
  - A revert on either side alone goes red on that side.
- **The shape sweep** ("a fixed plural over a count or list that can be one")
  found four more. They are filed rather than fixed: #682 (the CSF playbook
  export, client-facing) and #683 (three admin screens).
- Client-visible copy: condition 6.
