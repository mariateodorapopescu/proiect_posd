# SecureSync API

Resource server OAuth 2.0 pentru documente PDF. Aplicația folosește Java 21,
Spring Boot 3.5.8, Spring Security, Spring Data JPA, PostgreSQL și migrări Flyway.
Identitățile, parolele și sesiunile sunt administrate exclusiv de Keycloak.

## Pornire

Din rădăcina proiectului, urmează pașii din `README.md` și pornește Docker Compose.
API-ul ascultă implicit pe portul 8081. Containerul rulează cu utilizatorul
`securesync`, iar PDF-urile sunt păstrate în volumul privat montat la `/data/pdfs`.

Pentru dezvoltare fără container, pornește mai întâi PostgreSQL și Keycloak și
exportă variabilele înainte de `./mvnw spring-boot:run` sau `mvnw.cmd spring-boot:run`.
Spring Boot nu importă automat fișierul `.env` al Docker Compose.

| Variabilă | Semnificație |
|---|---|
| `DB_URL` | JDBC PostgreSQL; implicit `jdbc:postgresql://localhost:5432/securesync` |
| `DB_USER` | Utilizator DB; implicit `securesync` |
| `DB_PASSWORD` | Parola DB, obligatorie |
| `SERVER_PORT` | Port HTTP; implicit `8081` |
| `SPRING_PROFILES_ACTIVE` | `jwt` sau `introspection`; implicit `jwt` |
| `OIDC_ISSUER` | Issuer verificat; implicit `http://localhost:8080/realms/securesync` |
| `OIDC_JWK_SET_URI` | Endpoint JWKS; în Docker se folosește adresa internă `keycloak` |
| `OIDC_AUDIENCE` | Audience necesar; implicit `securesync-api` |
| `OIDC_INTROSPECTION_URI` | Endpoint introspecție; în Docker se folosește adresa internă `keycloak` |
| `INTROSPECTION_CLIENT_ID` | Client confidențial, implicit `securesync-api` |
| `INTROSPECTION_CLIENT_SECRET` | Secret obligatoriu în profilul `introspection` |
| `STORAGE_ROOT` | Director privat, implicit `./storage` |
| `CORS_ORIGINS` | Origini exacte separate prin virgulă; implicit `http://localhost:3001,http://localhost:3002` |
| `MEMBER_ADMIN_BASE_URL` | Admin API pentru realm-ul fix SecureSync; în Docker `http://keycloak:8080/admin/realms/securesync` |
| `MEMBER_ADMIN_TOKEN_URL` | Endpoint pentru tokenul serviciului de administrare; în Docker adresa internă Keycloak |
| `MEMBER_ADMIN_CLIENT_ID` | Client confidențial dedicat, implicit `securesync-member-admin` |
| `MEMBER_ADMIN_CLIENT_SECRET` | Secret numai pe server; dacă lipsește, administrarea membrilor refuză cererile cu 503 |

Nu există conturi de utilizator sau chei de semnare în baza de date a API-ului.
Schema `documents` este creată prin `V1__documents.sql`, apoi Hibernate o validează.

## Endpoint-uri

Trimite token-ul de acces în `Authorization: Bearer <access_token>`.

| Metodă și rută | Scope și rol | Comportament |
|---|---|---|
| `GET /api/health` | Public | Stare și strategia activă |
| `GET /api/me` | Orice token valid pentru API | `sub`, `username`, `department`, `roles`, `scopes`, `strategy` |
| `GET /api/documents` | `documents:read` și `USER` sau `ADMIN` | Documente proprii și din același departament; administratorul vede toate documentele |
| `POST /api/documents` | `documents:write` și `USER` sau `ADMIN` | Multipart cu `title` și `file`; răspunde cu 200 și metadatele documentului |
| `GET /api/documents/{id}/download` | `documents:read` și `USER` sau `ADMIN` | 200 pentru proprietar, același departament sau administrator; altfel 403 |
| `DELETE /api/documents/{id}` | `documents:write` și `USER` sau `ADMIN` | 204 pentru proprietar sau administrator; altfel 403 |
| `GET /api/members?search=&page=0` | `members:manage` și `IMPLEMENTATOR` activ în Keycloak | Maximum 20 de membri per pagină, cu `page` și `hasMore` |
| `PUT /api/members/{id}/access` | `members:manage` și `IMPLEMENTATOR` activ în Keycloak | Actualizează rolurile permise și departamentul unui alt membru; răspunde cu 200 și membrul actualizat |

Un token lipsă, invalid sau expirat produce 401. Lipsa scope-ului, rolului sau
permisiunii asupra documentului produce 403. Un document inexistent produce 404.
Rolul `ADMIN` nu înlocuiește scope-ul necesar operației.

## Administrarea membrilor

Rolul `IMPLEMENTATOR` permite administrarea accesului din tabul dedicat al
Portalului. El nu înlocuiește `USER`/`ADMIN` pentru documente. Cererile de
administrare necesită simultan scope-ul `members:manage`, rolul din token și
confirmarea online că utilizatorul este încă activ și are efectiv rolul
`IMPLEMENTATOR` în Keycloak. Această verificare live se face și în profilul JWT;
un token vechi nu păstrează dreptul de administrare după eliminarea rolului.

Lista returnează `members`, `page` și `hasMore`. Fiecare membru conține numai
`id`, `username`, `department`, `roles` și `enabled`. Căutarea este limitată la
80 de caractere; pagina este un întreg între 0 și 10000. Conturile de serviciu
nu sunt listate și nu pot fi modificate prin aceste endpointuri.

Actualizarea primește JSON de forma:

```json
{"roles":["USER","ADMIN"],"department":"IT"}
```

Lista de roluri trebuie să conțină cel puțin un rol distinct din `USER`,
`ADMIN`, `IMPLEMENTATOR`, iar departamentul trebuie să fie `IT` sau `HR`.
Identificatorul membrului este un UUID, nu un nume sau un segment de cale.
Accesul propriu nu poate fi modificat prin acest tab (403), pentru a păstra un
implementator disponibil. Rolurile de realm care nu aparțin acestei liste sunt
păstrate, la fel și câmpurile/atributele profilului. Rolurile gestionate moștenite
din grupuri/compozite necesită administrarea asocierii respective în Keycloak;
API-ul refuză cu 409 un rezultat care nu corespunde accesului efectiv solicitat.

Clientul confidențial folosește `client_credentials`, scope-ul `kc-admin-api`
și permisiunile Keycloak `view-users`, `manage-users`, `view-realm`. Browserul
primește doar rezultatul operației, niciodată secretul sau tokenul acestui client.
Timeout-ul conexiunilor este de trei secunde, redirecturile nu sunt urmate și
statusurile diferite de 200 pentru citire/token sau 204 pentru scriere sunt
tratate ca erori. Tokenul serviciului poate fi reutilizat până aproape de
expirare, dar dreptul live al implementatorului nu este memorat în cache.

Operațiile Admin REST multiple nu formează o tranzacție atomică. Scrierile
sunt serializate în instanța API, iar o eroare declanșează restaurarea încercată
a rolurilor gestionate și a profilului original. Dacă restaurarea nu reușește,
se înregistrează eroarea fără credențiale și clientul primește 503 cu instrucțiunea
de a reîncărca lista. Modificările simultane făcute direct de un administrator
extern în Keycloak nu sunt coordonate de această blocare locală.

Membrii trebuie să obțină un token nou pentru ca rolurile/departamentul noi să
apară în Documente/Portal. Schimbarea departamentului nu rescrie metadatele
documentelor deja încărcate. Nu există endpointuri noi pentru parole, ștergerea
sau crearea utilizatorilor.

Metadatele returnate sunt `id`, `title`, `originalFilename`, `ownerId`,
`department`, `size` și `createdAt`. Cheia de stocare și calea locală nu sunt expuse.
`ownerId` și `department` provin din token; câmpurile trimise de client nu le pot
suprascrie. Pentru încărcare este necesar un atribut `department` nevid.
Absența departamentului nu acordă acces la documentele altor utilizatori.

## Fișiere private

Fișierele sunt accesibile numai prin endpoint-ul autentificat de descărcare.
Nu există rută statică sau URL public pentru directorul PDF. Numele de stocare
au forma `doc_<UUID>.pdf`; numele original este folosit numai ca metadată și
nume de descărcare, după eliminarea căii și a caracterelor de control.

Se acceptă fișiere nevide cu MIME `application/pdf`, antet `%PDF-` și cel mult
10 MiB. Aceasta este verificarea de format aplicată, fără parsarea completă a
structurii PDF. Directorul real și numele generate sunt verificate la citire
și ștergere; referințele cu traversal și linkurile simbolice sunt refuzate.
Un upload eșuat sau o tranzacție anulată elimină fișierul nou. Ștergerea fișierului
are loc după commit-ul ștergerii metadatelor; o eroare de filesystem se înregistrează
în jurnal și poate lăsa un fișier privat orfan, fără acces prin API.

## Validarea token-urilor

Profilul `jwt` verifică semnătura RSA prin JWKS, issuer-ul, audience-ul,
subiectul și expirarea token-ului. Toleranța temporală este explicit zero,
pentru a nu adăuga o fereastră ascunsă experimentului de expirare. Serviciile
Docker de pe aceeași gazdă folosesc același ceas.

Profilul `introspection` apelează Keycloak pentru fiecare cerere, fără cache sau
revenire la validarea locală. După răspunsul activ sunt verificate issuer-ul,
audience-ul, subiectul, expirarea și `nbf`, dacă există. Rolurile din
`realm_access.roles` și scope-urile sunt mapate identic în ambele strategii.
Timeout-urile pentru conexiune și citire sunt de trei secunde.

## Teste

În PowerShell, din `api/`, cu `JAVA_HOME` îndreptat către un JDK 21:

```powershell
.\mvnw.cmd -B -ntp test
.\mvnw.cmd -B -ntp package
```

Pe Linux/macOS:

```sh
sh ./mvnw -B -ntp test
```

Testele folosesc JUnit 5, Spring Security Test, MockMvc, Mockito și o bază H2
temporară în modul PostgreSQL. Rulează migrarea Flyway reală și validează schema.
Nu folosesc Keycloak, date persistente sau parole reale. Acoperă ambele profiluri,
răspunsurile 401/403/200, ordinea scope/rol/politică, filtrarea pe departament,
proprietatea, CORS, formatul și dimensiunea PDF, traversal, symlink-uri și
curățarea fișierelor când persistarea eșuează sau tranzacția este anulată.

Testele locale de token folosesc un decoder controlat pentru a verifica lanțul
HTTP și testează separat validatorii de claims; verificarea semnăturii reale,
SSO și revocarea efectivă necesită sistemul Docker complet.
