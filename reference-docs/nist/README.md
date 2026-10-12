# NIST CSF 2.0 Reference Tool export (source for crosswalk X2)

- **File:** `csf-2.0-reference-tool-export-2026-10-12.xlsx`
- **sha256:** `d83fbc04ea146e3ed4cacd3594351beab2359ae835669d607228528b43bb31a7`
- **Source:** the NIST CSF 2.0 Reference Tool (CPRT), downloaded by Gene on 2026-10-12. The workbook's own "Generated Date" is 2026-10-12 10:54:09.
- **Its own read-me says:** "This export is a user generated version of the Core versus an official NIST publication." Treat it as such. The terms of use are not stated in the file, so it is labelled "NIST CSF 2.0 Reference Tool export, 2026-10-12" wherever it is used.
- **Contents:** sheet "CSF 2.0" has the columns Function, Category, Subcategory, Implementation Examples and Informative References.
  - 106 subcategories carry SP 800-53 references, as both "SP 800-53 Rev 5.1.1: XX-n" and "SP 800-53 Rev 5.2.0: XX-n" lines.
  - The other informative references (ISO, PCI DSS, CCM, CIS and so on) are third-party and are NOT used.
- **Use:** only the SP 800-53 lines, to compose crosswalk C1 (CSF 2.0 subcategory to SP 800-53 to ATT&CK) with X1 (MITRE CTID Mappings Explorer, SP 800-53 rev5 to ATT&CK 16.1, Apache-2.0). See the design note rev 5 section 12 on #736.
  - Pick the 800-53 revision that matches X1's control set, and disclose any difference.
- **Approved for the repository by Gene,** 2026-10-12 (#736).
