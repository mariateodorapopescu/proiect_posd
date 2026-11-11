# Domain

Users are Keycloak OIDC subjects, never locally persisted accounts. Realm roles USER/ADMIN drive document access; IMPLEMENTATOR manages member roles and departments through Portal. IMPLEMENTATOR does not implicitly grant document access: USER or ADMIN is still required for documents. Documents have ownerId=sub and department captured from the uploader's token, plus title/original filename/size/time/internal storage key.

Document titles are required and limited to 160 characters after trimming, consistently in the upload UI, API and database.

Scopes documents:read/write are required even for ADMIN. Scope and role are checked first; reads permit owner, same nonempty department, or ADMIN. Deletes permit owner or ADMIN. Lists include only documents the actor may read. Upload department is taken from verified claims, never the request.

401 means unauthenticated/invalid/expired token.403 means authenticated but policy denied.200 allowed reads/uploads,204 successful delete,404 missing resource,400 invalid input. The experiment compares session revocation versus access-token expiry with the same token and no refresh. It does not measure role-change propagation.

Member management requires scope members:manage and IMPLEMENTATOR. Existing regular members may be assigned a nonempty subset of USER/ADMIN/IMPLEMENTATOR and IT/HR. Own-account changes and service-account changes are forbidden. No member creation, password reset or member deletion is exposed in this tab. New role/department claims require a new user token; existing documents retain their stored department and owner.
