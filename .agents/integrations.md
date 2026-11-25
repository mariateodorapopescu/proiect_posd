# Integrations

Only Keycloak and PostgreSQL are integrated. No email, external uploads, analytics, messaging or production services.

Keycloak realm securesync has public clients securesync-documente (localhost3001/), securesync-portal (localhost3002/) and securesync-experiment (localhost8765/callback), exact redirects, Code+PKCE S256 only. API confidential client securesync-api authenticates introspection. Client securesync-experiment-admin uses client_credentials with realm-management manage-users/view-users and default scope kc-admin-api (required in26.8). Admin secrets never enter frontend.

securesync-claims maps sub, aud=securesync-api, department, realm_access.roles and preferred_username into access tokens AND introspection. The export defines kc-admin-api explicitly for first import. documents:read/write are optional requested scopes. department profile permits only admin edits. TTL60s, SSO idle1800/max3600.

Compose interpolates .env secrets into Keycloak import placeholders. Import on startup SKIPS existing realms; editing JSON/env does not update imported clients/users. Keep realm config and docs synchronized. issuer localhost8080 differs intentionally from internal keycloak8080 endpoint address.

The export enables self-registration for the `securesync` realm. On an existing realm, turn on **User registration** in **Realm settings → Login**. Registration uses the configured Keycloak form and the existing OIDC clients.

Member management uses confidential securesync-member-admin with client_credentials, default kc-admin-api scope and realm-management manage-users/view-users/view-realm. view-realm is needed for named role lookups. MEMBER_ADMIN_CLIENT_SECRET is only in Keycloak/API environments, never React. MEMBER_ADMIN_BASE_URL/TOKEN_URL select internal Docker endpoints; CLIENT_ID defaults to securesync-member-admin.

Only Portal requests optional members:manage; Documente scopes stay unchanged. The realm exports IMPLEMENTATOR and implementator.demo (USER+IMPLEMENTATOR). Existing installs use python scripts/configure-members.py once before rebuilding; it adds a missing member-service secret, role/scope/client and only a missing demo account, preserving existing accounts/passwords/roles/documents. The setup is local-only and refuses HTTP redirects. Do not reset volumes to install this feature or regrant a deliberately revoked existing account.
