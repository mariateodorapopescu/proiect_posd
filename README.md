# SecureSync

Platformă demonstrativă de documente PDF cu acces controlat prin **OAuth 2.0 / OpenID Connect**, realizată în cadrul cursului *Politici în Sisteme Distribuite* (2026–2027), tema 10: *Controlul accesului la resurse folosind OAuth 2.0*.

> Starea proiectului: în dezvoltare. Secțiunile marcate cu **[de completat]** se actualizează pe măsură ce componentele sunt gata.

## Ce face proiectul

- Utilizatorii se autentifică o singură dată (**SSO**) și folosesc două aplicații web: **Documente** și **Portal**.
- API-ul REST (Spring Boot) acceptă doar token-uri valide emise de **Keycloak** și decide accesul pe trei niveluri: *scope* → *rol* → *atribut / proprietar*.
- Un experiment măsoară cât timp mai poate folosi API-ul un utilizator **revocat** (time-to-deny) pentru două strategii de validare: JWT local cu durată scurtă și introspecție la fiecare cerere.

## Arhitectura

Diagrama de componente este în [`docs/arhitectura.png`](docs/arhitectura.png).

```
Browser: Documente + Portal (HTML/CSS/JS)
        │  Authorization Code + PKCE
        ▼
     Keycloak ── PostgreSQL (Keycloak)
        │  token de acces (JWT)
        ▼
  API Spring Boot ── PostgreSQL (documente) + folder PDF-uri
        ▲
Script experiment (Python): revocă sesiunea și măsoară primul refuz
```

## Stack

| Strat | Tehnologie |
|---|---|
| Rulare | Docker Compose |
| Server de autorizare | Keycloak 26.x |
| API | Java 21, Spring Boot 3.5.x, Spring Security (resource server) |
| Bază de date | PostgreSQL, migrări Flyway |
| Frontend | HTML, CSS, JavaScript, `oidc-client-ts` |
| Experiment | Python 3.12 (`requests`/`httpx`, `pandas`, `numpy`, `scipy`, `matplotlib`) |
| Teste API | JUnit 5, Spring Security Test, MockMvc |

Versiunile exacte se fixează în `docker-compose.yml`, `pom.xml` și `experiment/requirements.txt`.

## Structura repo-ului

```
keycloak/      realm-export.json și instrucțiuni de import
api/           aplicația Spring Boot (security/, documents/, teste)
web/           aplicațiile Documente și Portal, cod comun de login
experiment/    scripturi Python pentru măsurarea revocării și datele brute
docs/          diagrame, documentul comun, eseuri
```

## Cum pornești proiectul

Cerințe: Docker și Docker Compose.

```bash
cp .env.example .env
docker compose up -d
```

Porturi propuse (de confirmat în echipă):

| Serviciu | Port |
|---|---|
| Keycloak | 8080 |
| API | 8081 |
| Aplicația Documente | 3001 |
| Portal | 3002 |

Oprire și ștergerea datelor locale:

```bash
docker compose down -v
```

### Utilizatori de test **[de completat]**

Realm-ul importat va conține utilizatori cu roluri și departamente diferite (de exemplu un `USER` din departamentul IT, un `USER` din HR și un `ADMIN`). Numele și parolele de dezvoltare se documentează în [`keycloak/README.md`](keycloak/README.md). Parolele din repo sunt doar pentru dezvoltare.

## Politica de acces

| Operație | Scope | Regulă | Răspuns |
|---|---|---|---|
| Listare documente | `documents:read` | `USER` vede documentele proprii și pe cele din departamentul lui, `ADMIN` pe toate | 200 |
| Încărcare | `documents:write` | orice `USER` | 200 |
| Descărcare | `documents:read` | proprietar, același departament sau `ADMIN` | 200 / 403 |
| Ștergere | `documents:write` | proprietar sau `ADMIN` | 204 / 403 |
| Fără token sau token invalid | – | refuz | 401 |

Regula exactă pentru departament se stabilește de echipă (**[de completat]**).

## Strategii de validare a token-ului

API-ul rulează în două moduri, alese prin profil Spring:

```bash
SPRING_PROFILES_ACTIVE=jwt            # validare locală a JWT (JWKS)
SPRING_PROFILES_ACTIVE=introspection  # introspecție RFC 7662 la fiecare cerere
```

## Experimentul de revocare **[în lucru]**

```bash
pip install -r experiment/requirements.txt
python experiment/measure.py --strategy jwt --ttl 60 --runs 100
python experiment/analyze.py
```

Definiție: *time-to-deny* = intervalul dintre revocarea sesiunii (apelul Admin API a returnat succes) și primul refuz (401/403) urmat de încă 4 refuzuri consecutive. Se raportează p50, p95, minim, maxim și numărul de repetări. Datele brute se salvează în `experiment/data/` (CSV).

## Testare

```bash
cd api
./mvnw test
```

Testele automate verifică răspunsurile 200, 401 și 403 pe endpoint-urile documentelor. SSO-ul și revocarea se verifică separat, manual și prin scriptul de experiment.

## Echipa

| Membru | Componentă |
|---|---|
| Cristian Calcan | Keycloak și infrastructură (`keycloak/`, `docker-compose.yml`) |
| Ioana Isar | Securitatea API-ului (`api/.../security`) |
| Dragoș Enăchescu | Documente, bază de date și teste (`api/.../documents`, `api/src/test`) |
| Maria-Teodora Popescu | Aplicații web și experiment (`web/`, `experiment/`) |

## Cum lucrăm în Git

1. `main` conține doar cod care pornește. Nu facem push direct pe `main`.
2. Fiecare lucrează pe un branch (`keycloak/realm`, `api/security`, `api/documents`, `web/login`, `experiment/measure`) și deschide un pull request.
3. Un alt membru citește pull request-ul înainte de merge.
4. Commit-uri mici, cu mesaje clare.
5. Nu se urcă secrete, `.env`, fișiere încărcate (`uploads/`) sau date personale.

## Referințe

Lista de referințe a proiectului se păstrează în `docs/`. Eseurile individuale au bibliografii proprii.
