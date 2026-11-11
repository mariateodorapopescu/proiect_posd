# Architecture

SecureSync is a standalone local educational document-access system. Java21/SpringBoot3.5.8 API in api/ (ro.securesync.api; security,documents,common), two React/Vite entry apps in web/ (documente,portal), Keycloak26.8.2 and two PostgreSQL16 databases. All services start with docker-compose.yml.

Read docs/architecture.md for the diagram and contracts. API uses Spring Security resource-server with jwt (default) or introspection profiles. Files are private in /data/pdfs and metadata uses JPA+Flyway (ddl-auto validate). Frontend tokens remain in memory; PKCE transaction state alone uses sessionStorage. No local user/password authentication exists.

The members feature adds a Portal tab and API members/ package backed by the Keycloak Admin REST API. It creates no local user table. A dedicated confidential service client stays server-only; each management request checks the caller's current Keycloak role in addition to token authorization. See docs/members.md and decisions/0001-members-management.md.

Browser issuer is http://localhost:8080/realms/securesync. Internal JWKS/introspection URLs use keycloak:8080. API is localhost8081, browser apps localhost3001/3002; ports are loopback only. See integrations.md before changing URLs/clients.
