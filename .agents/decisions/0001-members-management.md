# IMPLEMENTATOR administration through Portal

User request: manage member roles inside the application. Add IMPLEMENTATOR separately from document ADMIN and use a server-mediated Keycloak integration. Identity remains in Keycloak; no SQL user mirror is introduced.

Portal requires members:manage plus IMPLEMENTATOR. API also verifies the caller's current effective role/enabled state online, preventing a stale JWT from retaining member administration. This additional check affects only member administration, preserving the document JWT/introspection revocation experiment.

A dedicated service client has manage-users/view-users/view-realm and kc-admin-api. Browser clients never receive its secret or admin service token. Only three app roles and IT/HR are editable; own and technical accounts are protected. Existing accounts cannot be created/deleted or assigned passwords through this feature.

Keycloak Admin REST writes are separate operations. Snapshot/restore and postcondition checks reduce partial-failure risk but do not make the operation atomic. A local mutation lock matches the current single-API Compose deployment; multi-instance use needs separate concurrency design.
