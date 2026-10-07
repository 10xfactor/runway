# Security Policy

Report vulnerabilities privately to security@10xfactor.community (or via GitHub private advisories). Do not open public
issues for them. Expect an acknowledgement within 3 business days.

Design commitments:
- The Console binds to loopback only, checks the Host header, and requires a per-session token.
- Events never contain artifact payloads; free text is redacted. Payload views need `--expose-payloads`.
- The Console makes no non-loopback network requests (enforced by an E2E test).
- Secrets come from the environment; Runway never logs or stores them.
