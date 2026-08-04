"""NIST CSF 2.0 module.

Catalog data (functions / categories / subcategories) lives in
`app.csf.catalog`. Maturity tier definitions and label maps live in
`app.csf.maturity`. The catalog is intentionally code-only (not seeded
into the database) — it is immutable reference data; only the
engagement's *answers* land in `csf_answers` keyed by subcategory code.
"""
