# Cerințe și demonstrație

Referința de lucru este propunerea echipei SecureSync, tema 10, din documentul de proiect furnizat. Tabelul leagă cerințele de componentele implementate.

| Cerință | Implementare | Verificare |
|---|---|---|
| Keycloak 26.x și infrastructură comună | realm-export.json, docker-compose.yml | Import inițial și healthcheck |
| Java 21, Spring Boot 3.5, PostgreSQL 16 | api/pom.xml, Dockerfile, Flyway | Teste API, pornire Docker |
| Două aplicații React | web/documente, web/portal, shared | Build și testare în browser |
| Authorization Code + PKCE și SSO | Clienți publici diferiți, S256, realm comun | verify-stack.py și demonstrație browser |
| Token doar în memorie | User store OIDC în memorie | Test dedicat; reload necesită redirect |
| Scope → rol → proprietar/atribut | documents:read/write, USER/ADMIN, department/sub | MockMvc și matrice reală de acces |
| PDF doar prin API | volum privat, endpoint autentificat download | 401 fără token, 403 străin, 200 autorizat |
| Revocare și comparație strategii | profile jwt/introspection, experiment/measure.py | Revocare exactă prin Admin API |
| Cost pe cerere și time-to-deny | samples.csv, runs.csv, analyze.py | Date reale, statistici și bootstrap |
| Pornire unică | docker compose up -d --build | Se construiesc și pornesc toate componentele |

## Parcurs pentru prezentare

Pornește sistemul conform README-ului principal. Încarcă un document cu Alice, verifică accesul din același departament cu Carol și refuzul cu Bob. Arată că un utilizator autentificat fără rol sau scope primește 403, iar fără token primește 401. Arată Portal după login în Documente pentru SSO.

Pentru revocare, păstrează TTL-ul, documentele și parametrii identici. Rulează o serie în modul JWT, schimbă profilul API-ului și rulează seria cu introspecție. Prezintă datele brute, numărul de repetări, măsurătorile p50/p95 și repetările invalide/cenzurate. Distinge demonstrația de funcționare de concluziile statistice.

## Ce redactează echipa

Extensia cerută ulterior adaugă rolul IMPLEMENTATOR și administrarea rolurilor/departamentelor direct în Portal. Este descrisă în [members.md](members.md); USER și ADMIN rămân rolurile de acces la documente ale temei.

Documentul comun, eseurile individuale, interpretarea rezultatelor și concluziile sunt livrabile academice separate. Nu sunt înlocuite de README-uri. Nu atribui automat implementarea generată fiecărui membru; împărțirea responsabilităților rămâne cea convenită de echipă.
