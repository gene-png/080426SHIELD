# 2026-09-26: every technique in the ATT&CK workbook links to its MITRE page (#647)

Branch `track2/attack-workbook-fields`, from `main` at `e851e59`.

## What changed

- **`catalog.technique_url(code)`** returns MITRE's page for a catalogue
  technique, a sub-technique's dot becoming a slash. A code the catalogue does
  not carry raises `KeyError`. The test compares every catalogue id against the
  `mitre-attack` external reference in the committed STIX subset, so the rule
  cannot agree with itself.
- **The Coverage, Gaps and Unscored sheets link each technique code** in column
  A. A stored gap code outside the catalogue is printed unlinked.

## What #647 asked for that was already on `main`

#647 was recorded against `43bfa99`. #494 (`7436c23`) landed after that and
before this branch: the Rationale column, the three tool lists and the coverage
percentage's definition are in all three renderers, and the DOCX/PDF gap
heading already says it is the first fifty by code and that the XLSX carries
all of them (#480).

## Left as it is

- **Notes stays.** It has a writer, the technique panel's Notes box, which
  PATCHes `notes`. It is empty in the live test because no consultant wrote a
  note. Dropping it would drop notes where they exist; that is Gene's call.
- **The DOCX and PDF gap tables are not linked.** #647 asked for the workbook,
  and those tables carry at most fifty codes that the XLSX Gaps sheet repeats
  with links. The exporter says so at `_link_technique`.
