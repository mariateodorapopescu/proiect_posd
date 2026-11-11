# Data model

PostgreSQL documents table is created by api/src/main/resources/db/migration/V1__documents.sql. Hibernate validates; do not use ddl-auto update. No local user table; owner_id references external Keycloak sub as a string, not a database FK.

Fields: generated bigint id, title(160), original_filename(200), storage_key unique, owner_id, department(100), size positive, created_at. Consult the SQL/entity for exact constraints before changes. DTO excludes storage_key. Persist PDF files only under STORAGE_ROOT with generated UUID names. Rollback cleanup removes new uploads; deletion removes file after successful DB commit (filesystem failure can leave a private orphan).

Member roles and departments are read/updated in Keycloak only. The IMPLEMENTATOR feature adds no SQL migration and does not rewrite existing document metadata when a user's department changes.
