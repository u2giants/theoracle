# R8 offline security repair evidence

Scope: invented fixtures only. No employees, company data, renewal/replay,
production installation or live/business acceptance. The 120-second ceiling
remains unchanged.

The requested security review identified three blockers: application-accessible
authority minting, ambiguous signed field boundaries, and forgeable enabled
participation settings. The application now verifies only; Q2b observations
cannot self-authorize. The host signer requires a fixed root-controlled
configuration, a distinct OS identity, exclusively owned key and independent
unexpired grant over the exact purpose-tagged payload. Canonical JSON preserves
field boundaries; complete participation settings retain and reverify proof.
The issuer is pinned against request-time environment substitution.

Offline tests at code checkpoint `c1346549` pass 256 Python checks, including
37 signer-security checks, canonical-wire collision regressions, complete
participation authority and Q2b admission denial/positive cases. S12 verifier
passes seven checks with `live_accepted: false`. The authenticated browser
fixture repair adds two TypeScript authentication tests to the original 38;
all 40 and all seven browser journey cases pass. Exact final-source independent
review and recorded passing tests are required before shipment; this repair
record is not an approval report.

Actual host installation/isolation, Q2b target owner/caller/TLS proof,
W10/R7 timing, native/hosted/browser production proof, stage acceptance and
business acceptance remain separate unproven gates on existing issue #27.
Business questions/reports/grading and employee/company-data work stay closed.
