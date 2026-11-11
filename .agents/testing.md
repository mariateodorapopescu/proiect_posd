# Testing

API: Java21 JAVA_HOME, api/mvnw.cmd test or package. JUnit5/SpringSecurityTest/MockMvc; H2 PostgreSQL mode for integration policy/Flyway tests, temp file roots. Real PostgreSQL is verified separately by Docker. Tests cover both profiles,401/403/200, scope/role/ownership/department, JWT claims, introspection no-cache, file validation/path/symlink and transaction cleanup.

Web: npm ci, npm test (Node test/assert), npm run build (TypeScript+both Vite builds). Meaningful memory-token/session-race/policy tests. Use a real browser for PKCE callback, SSO and displayed document flows.

With the local stack running, npm run test:oidc in web/ uses the real oidc-client-ts request/callback handling and a local HTTP form transport to verify both clients, SSO, nonce and memory-only tokens. It complements protocol tests and does not replace visual browser verification. It reads only synthetic demo .env credentials and never prints tokens.

Experiment: python -m unittest discover -s experiment -p 'test_*.py' -v; Dockerfile runs same suite with Python3.12. CLI smoke --help and optional real data analysis. Never fabricate experimental results.

Full local stack: python scripts/verify-stack.py --strategy jwt|introspection --check-revocation. Reads only demo .env, authenticates with real Code+PKCE, verifies second-client SSO at protocol level, HTTP policies/PDF and revocation. Creates/deletes only its test document. This complements browser checks; don't describe the protocol script as browser UI testing.

Windows launcher: powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/test-launcher.ps1 runs isolated tests with a temporary fake Docker CLI and project path containing spaces. Covers native exit-code propagation, exact project stop/volume preservation, failed-start short-circuit, readiness of all endpoints, NoBrowser, .env preservation/first generation, engine-off stop, BAT invocation from another working directory and invalid actions. No real containers are altered. Separately verify a real SecureSync.bat stop/start -NoBrowser cycle only when the running demo may be interrupted; confirm volumes/data persist and leave the application running.

Members regressions cover scope+role+live authorization, own/service protection, input bounds, preserving unrelated user fields/roles, strict upstream statuses and ambiguous/inherited rollback. Web tests exercise the gate, allowed access payload, privileged-role confirmation and draft equality. python scripts/verify-members.py --strategy jwt|introspection checks the actual local realm with real PKCE and only uniquely named disposable accounts (cleanup in finally), including stale IMPLEMENTATOR tokens after role removal. Existing members/passwords/documents are not changed by that script. Browser tests must additionally verify tab visibility, role/dept save, confirmation and self protection.
