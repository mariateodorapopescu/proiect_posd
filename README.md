# SecureSync

Platformă demonstrativă de documente PDF cu acces controlat prin **OAuth 2.0 / OpenID Connect**, realizată în cadrul cursului *Politici în Sisteme Distribuite* (2026–2027), tema 10: *Controlul accesului la resurse folosind OAuth 2.0*.

> Starea proiectului: componentele demonstrative sunt implementate și au fost verificate local. Seria completă de măsurători, documentul comun și eseurile individuale rămân în lucru.

## Ce face proiectul

- Utilizatorii se autentifică o singură dată (**SSO**) și folosesc două aplicații web: **Documente** și **Portal**.
- API-ul REST (Spring Boot) acceptă doar token-uri valide emise de **Keycloak** și decide accesul pe trei niveluri: *scope* → *rol* → *atribut / proprietar*.
- Un experiment măsoară cât timp mai poate folosi API-ul un utilizator **revocat** (time-to-deny) pentru două strategii de validare: JWT local cu durată scurtă și introspecție la fiecare cerere.
- Rolul **IMPLEMENTATOR** are în Portal tabul **Administrare membri**, pentru atribuirea rolurilor și a departamentelor conturilor existente.

## Arhitectura

Diagrama de componente din propunerea inițială este în [`docs/arhitectura.png`](docs/arhitectura.png). Descrierea implementării curente și diagrama editabilă sunt în [`docs/architecture.md`](docs/architecture.md) și [`docs/components.puml`](docs/components.puml).

```text
Browser: Documente + Portal (React/TypeScript → HTML/CSS/JS)
        │  Authorization Code + PKCE
        ▼
     Keycloak ── PostgreSQL (Keycloak)
        │  token de acces (JWT)
        ▼
  API Spring Boot ── PostgreSQL (documente) + folder PDF-uri
        ▲
Script experiment (Python): revocă sesiunea și măsoară primul refuz
```

Keycloak este singura sursă de autentificare. Aplicațiile au clienți OIDC diferiți și reutilizează aceeași sesiune SSO. Tokenurile sunt păstrate în memoria paginii; doar tranzacția PKCE temporară folosește sessionStorage. PDF-urile se descarcă exclusiv prin API, fără rută publică sau URL extern de fișier.

## Stack

| Strat | Tehnologie |
|---|---|
| Rulare | Docker Compose |
| Server de autorizare | Keycloak 26.8.2, din familia 26.x |
| API | Java 21, Spring Boot 3.5.8, Spring Security (resource server) |
| Bază de date | PostgreSQL 16.11, migrări Flyway |
| Frontend | React și TypeScript, compilate în HTML/CSS/JavaScript, `oidc-client-ts` |
| Experiment | Python 3.12+, `requests`, `matplotlib`; statistici și bootstrap prin biblioteca standard |
| Teste API | JUnit 5, Spring Security Test, MockMvc |

Versiunile exacte sunt fixate în `docker-compose.yml`, `api/pom.xml`, `web/package-lock.json` și `experiment/requirements-lock.txt`. Runnerul Docker pentru experiment folosește Python 3.12.16.

Propunerea inițială menționa și `httpx`, `pandas`, `numpy` și `scipy`. Implementarea actuală nu le folosește: cererile sunt realizate cu `requests`, analiza și bootstrap-ul cu biblioteca standard Python, iar graficele cu `matplotlib`. Nu este necesară instalarea bibliotecilor nefolosite.

## Structura repo-ului

```text
keycloak/      realm-export.json și instrucțiuni de import
api/           aplicația Spring Boot (security/, documents/, teste)
web/           aplicațiile Documente și Portal, cod comun de login
experiment/    scripturi Python pentru măsurarea revocării și datele brute
docs/          diagrame, documentație; documentul comun și eseurile se completează de echipă
scripts/       generarea .env, verificarea sistemului și lansatorul local
.agents/       contractele tehnice pentru întreținerea proiectului
SecureSync.bat lansatorul Windows
```

Pachetele API sunt sub `ro.securesync.api`. Metadatele documentelor folosesc Flyway și validarea schemei; fișierele PDF au un volum privat separat. Datele și rezultatele locale din `.local/` sunt ignorate de Git.

## Cum pornești proiectul

Cerințe: Docker și Docker Compose. Pe Windows, folosește Docker Desktop cu Linux containers.

### Lansator Windows

Dublu clic pe **`SecureSync.bat`** deschide meniul: `1` pentru pornirea completă și deschiderea aplicațiilor, `2` pentru oprire, `3` pentru stare și `0` pentru ieșire. Oprirea păstrează volumele și documentele. Se pot folosi și argumentele:

```powershell
.\SecureSync.bat start
.\SecureSync.bat status
.\SecureSync.bat stop
```

Pornirea poate lansa Docker Desktop dacă este oprit, creează `.env` numai dacă lipsește, construiește/pornește serviciile și așteaptă răspunsurile HTTP înainte de a deschide Documente și Portal. Pentru pornire fără deschiderea browserului, folosește `.\SecureSync.bat start -NoBrowser`.

### Pornire manuală

Din rădăcina proiectului, în PowerShell:

```powershell
.\scripts\init-env.ps1
docker compose up -d --build
docker compose ps
```

`init-env.ps1` creează `.env` cu parole locale aleatoare și nu suprascrie un fișier existent. Prima construire descarcă imaginile și dependențele și rulează testele API.

Alternativa manuală inițială rămâne disponibilă, inclusiv pe Linux/macOS:

```bash
cp .env.example .env
# Completează toate valorile goale din .env cu secrete locale aleatoare.
docker compose up -d --build
```

Nu porni cu valorile goale din `.env.example`. Dacă imaginile sunt deja construite, `docker compose up -d` este suficient.

Porturile configurate:

| Serviciu | Port | Adresă |
|---|---|---|
| Keycloak | 8080 | http://localhost:8080/admin |
| API | 8081 | http://localhost:8081/api/health |
| Aplicația Documente | 3001 | http://localhost:3001 |
| Portal | 3002 | http://localhost:3002 |

Folosește **localhost** în browser: issuer-ul, redirecturile exacte și originile CORS sunt configurate astfel. Bazele de date nu publică porturi pe host. Configurația HTTP `start-dev` este destinată demonstrației locale, legată de loopback.

Oprire cu păstrarea datelor locale:

```bash
docker compose down
```

Oprire și ștergerea datelor locale, numai când dorești resetarea demonstrației:

```bash
docker compose down -v
```

Opțiunea `-v` șterge bazele de date și toate PDF-urile din volume.

### Utilizatori de test

Realm-ul importat conține utilizatori cu roluri și departamente diferite. Parola comună este valoarea **`DEMO_USER_PASSWORD`** din `.env`; nu este publicată în README. Numele și configurarea sunt documentate și în [`keycloak/README.md`](keycloak/README.md).

| Utilizator | Rol | Departament | Verificare |
|---|---|---|---|
| alice.it | USER | IT | Încarcă și gestionează propriul document |
| carol.it | USER | IT | Citește documentele din același departament |
| bob.hr | USER | HR | Primește 403 pentru documentul IT |
| admin.demo | ADMIN | IT | Citește/șterge orice document, cu scope-ul necesar |
| implementator.demo | USER, IMPLEMENTATOR | IT | Tab de administrare a rolurilor și departamentelor în Portal |
| observer.it | fără USER/ADMIN | IT | Primește 403 în ciuda autentificării |

Utilizatorul consolei Keycloak este `admin`, cu parola din **`KEYCLOAK_ADMIN_PASSWORD`**; este diferit de `admin.demo`.

Importul de startup nu suprascrie un realm existent. Schimbarea exportului sau a parolelor din `.env` nu actualizează automat datele deja importate. Modificările ulterioare se aplică prin Admin Console sau printr-o resetare explicită a datelor demonstrative.

## Politica de acces

| Operație | Scope | Regulă | Răspuns |
|---|---|---|---|
| Listare documente | `documents:read` | `USER` vede documentele proprii și pe cele din departamentul lui, `ADMIN` pe toate | 200 |
| Încărcare | `documents:write` | `USER` sau `ADMIN`; proprietarul și departamentul provin din token | 200 |
| Descărcare | `documents:read` | proprietar, același departament sau `ADMIN` | 200 / 403 |
| Ștergere | `documents:write` | proprietar sau `ADMIN` | 204 / 403 |
| Fără token sau token invalid/expirat | – | refuz | 401 |

Rolul `USER` sau `ADMIN` este obligatoriu pentru operațiile de documente, iar `ADMIN` nu ocolește scope-urile. Un token valid fără scope, rol sau regula necesară produce 403. Resursele inexistente produc 404, iar un formular/conținut PDF invalid 400.

Regula pentru departament este implementată: citirea este permisă pentru același atribut `department` nenul/nevid. Atributul poate fi modificat doar de administratorul Keycloak. Ștergerea rămâne rezervată proprietarului și administratorului, inclusiv între utilizatori din același departament.

Titlul este obligatoriu și limitat la 160 de caractere. PDF-urile au maximum 10 MiB; API-ul verifică MIME-ul, antetul și stocarea sub un nume generat, fără traversarea directoarelor sau symlink-uri. Verificarea antetului nu este analiză completă a PDF-ului sau antivirus.

### Administrarea rolurilor direct în aplicație

Deschide **Portal**, conectează-te cu **`implementator.demo`** și aceeași parolă demonstrativă, apoi alege tabul **Administrare membri**. Caută utilizatorul, bifează USER/ADMIN/IMPLEMENTATOR, alege IT sau HR și apasă **Salvează pentru ...**. Un nou rol ADMIN sau IMPLEMENTATOR cere și **Confirmă modificarea**.

Tabul este rezervat rolului IMPLEMENTATOR și scope-ului `members:manage`, solicitat numai de Portal. `admin.demo` rămâne administrator de documente. Contul curent este protejat împotriva modificării propriului acces, iar conturile de serviciu nu se editează. Membrul se autentifică din nou pentru un token cu noile roluri/departament; documentele existente nu sunt rescrise. Detaliile sunt în [`docs/members.md`](docs/members.md).

Instalările noi importă această configurație automat. Pentru o instalare deja existentă, cu Keycloak pornit, se rulează o dată `python scripts/configure-members.py`, apoi `docker compose up -d --build`. Scriptul completează configurația necesară fără resetarea volumelor, parolelor sau a documentelor.

## Strategii de validare a token-ului

API-ul rulează în două moduri, alese prin profil Spring:

```bash
SPRING_PROFILES_ACTIVE=jwt            # validare locală a JWT (JWKS)
SPRING_PROFILES_ACTIVE=introspection  # introspecție RFC 7662 la fiecare cerere
```

Acestea sunt profilurile API-ului. Pentru instanța Docker Compose, variabila care selectează profilul este **`TOKEN_VALIDATION_STRATEGY`**. Schimbarea în PowerShell se aplică prin recrearea API-ului:

```powershell
$env:TOKEN_VALIDATION_STRATEGY = "introspection"
docker compose up -d --force-recreate --no-deps api
```

Revenire la modul implicit JWT:

```powershell
$env:TOKEN_VALIDATION_STRATEGY = "jwt"
docker compose up -d --force-recreate --no-deps api
Remove-Item Env:TOKEN_VALIDATION_STRATEGY
```

`GET /api/me` arată strategia efectivă. `docker compose restart` nu aplică variabile noi. Ambele profiluri folosesc aceeași bază de date și aceeași politică de acces.

TTL-ul implicit este 60 s. Validarea JWT verifică semnătura, issuer-ul, audiența și expirarea, fără toleranță suplimentară la expirare. Tokenul deja emis poate rămâne acceptat după închiderea sesiunii Keycloak până expiră. Introspecția consultă Keycloak la fiecare cerere, fără cache. Nu există refresh automat care să schimbe tokenul în timpul experimentului.

## Experimentul de revocare **[în lucru]**

Colectarea și analiza sunt implementate; seria completă de măsurători și interpretarea rezultatelor pentru raport rămân în lucru. Instrucțiunile complete sunt în [`experiment/README.md`](experiment/README.md).

Instalează dependențele și încarcă în mediul procesului numai secretul administrativ local, fără a-l afișa:

```powershell
python -m pip install -r experiment/requirements.txt
$line = Get-Content .env | Where-Object { $_ -like 'EXPERIMENT_ADMIN_CLIENT_SECRET=*' }
$env:EXPERIMENT_ADMIN_CLIENT_SECRET = $line.Substring($line.IndexOf('=') + 1)
```

Cu API-ul în modul JWT, exemplul pentru seria propusă de 100 de repetări este:

```powershell
python experiment/measure.py --strategy jwt --ttl 60 --runs 100 --interval 0.02 --output experiment/data/jwt
```

După schimbarea API-ului la introspecție, păstrând aceiași parametri:

```powershell
python experiment/measure.py --strategy introspection --ttl 60 --runs 100 --interval 0.02 --output experiment/data/introspection
python experiment/analyze.py experiment/data/jwt experiment/data/introspection --output experiment/data/summary.json --plot experiment/data/comparison.png
Remove-Item Env:EXPERIMENT_ADMIN_CLIENT_SECRET
```

Pentru o verificare rapidă se poate folosi `--runs 1`. Autentificarea folosește Authorization Code + PKCE. Fiecare repetare revocă sesiunea măsurată și poate necesita o autentificare nouă în browser. `--ttl` verifică durata reală a tokenului, nu modifică Keycloak. Intervalul de 20 ms corespunde sondării de 10–50 ms din diagrama inițială; trebuie păstrat identic pentru ambele strategii.

Definiție: *time-to-deny* = intervalul dintre revocarea sesiunii (apelul Admin API a returnat succes) și primul refuz (401/403) urmat de încă 4 refuzuri consecutive. Se raportează p50, p95, minim, maxim și numărul de repetări. Datele brute se salvează în `experiment/data/` (CSV).

Se revocă exact sesiunea `sid`, iar cererile continuă cu același token. Erorile de rețea/5xx sunt repetări invalide, nu refuzuri rapide; depășirea ferestrei de observare este raportată separat ca rezultat cenzurat. Analiza poate calcula bootstrap pentru mediană când există suficiente repetări.

Verificarea locală a produs **o repetare validă per strategie**: aproximativ 57,85 s pentru JWT și 0,010 s pentru introspecție, la TTL 60 s. Datele acestei verificări sunt în `.local/experiment/`, ignorat de Git. Aceste valori confirmă mecanismul de măsurare; nu reprezintă seria de 100 de repetări sau o concluzie statistică finală. Vezi [`docs/validation.md`](docs/validation.md).

## Testare

Testele API se rulează cu Java 21 și `JAVA_HOME` către JDK 21. Pe Windows:

```powershell
cd api
.\mvnw.cmd test
cd ..
```

Pe Linux/macOS, din `api/`, se poate folosi `./mvnw test` (cu permisiune de execuție pentru wrapper).

Testele automate verifică răspunsurile 200, 401 și 403 pe endpoint-urile documentelor. SSO-ul și revocarea se verifică separat, manual și prin scriptul de experiment.

Pentru frontend și experiment, din rădăcina proiectului:

```powershell
cd web
npm ci
npm test
npm run build
# Cu stack-ul local pornit:
npm run test:oidc
cd ..
python -m unittest discover -s experiment -p "test_*.py" -v
python scripts/verify-stack.py --strategy jwt --check-revocation
python scripts/verify-members.py --strategy jwt
```

După schimbarea profilului, verificările `verify-stack.py` și `verify-members.py` se rulează cu `--strategy introspection`. Primul script creează și șterge propriul document de test, iar al doilea creează și șterge numai propriile conturi temporare.

Validarea executată include **35 teste API, 13 teste web și 25 teste de experiment**, buildurile și integrarea cu PostgreSQL/Keycloak reale. Suita de experiment a trecut și în runnerul Docker Python 3.12.16. Testul OIDC folosește biblioteca reală și verifică ambele aplicații, callback-ul PKCE, nonce-ul și SSO-ul. Verificarea membrilor creează numai conturi temporare proprii, le șterge în final și verifică inclusiv refuzul unui token IMPLEMENTATOR vechi după retragerea rolului.

Au fost verificate și în browser autentificarea, SSO-ul între Documente și Portal și încărcarea/descărcarea unui PDF; hash-ul SHA-256 al fișierului descărcat a coincis cu cel încărcat. Lansatorul Windows a trecut 10 teste izolate și un ciclu real de oprire/pornire, cu păstrarea documentului și descărcarea lui identică după repornire. Detaliile și limitele verificărilor sunt păstrate în [`docs/validation.md`](docs/validation.md).

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

Documentație tehnică pentru implementare:

- [Keycloak Docker](https://www.keycloak.org/getting-started/getting-started-docker)
- [Importul realm-ului și variabilele de mediu](https://www.keycloak.org/server/importExport)
- [Endpointuri OIDC și introspecție](https://www.keycloak.org/securing-apps/oidc-layers)
- [oidc-client-ts](https://authts.github.io/oidc-client-ts/)

## Demonstrație

1. Deschide Documente și apasă **Autentificare**. Conectează-te cu `alice.it`.
2. Încarcă un PDF de maximum 10 MiB, cu titlu de maximum 160 de caractere, apoi descarcă-l din listă.
3. Deschide Portal în același browser și apasă Autentificare. Sesiunea SSO permite revenirea fără reintroducerea parolei; Portal afișează identitatea primită de API.
4. Verifică separat, prin logout/login, accesul lui `carol.it`, `bob.hr` și `admin.demo`. Ștergerea este rezervată proprietarului și administratorului.
5. În Portal, verifică cererea cu token și cererea fără token. Fără token se primește 401.

Tokenurile rămân în memoria paginii. După reîncărcare, autentificarea inițiază un nou redirect și poate reutiliza sesiunea SSO. TTL-ul de 60 s este scurt în mod intenționat pentru experiment; dacă expiră în timpul demonstrației, folosește din nou autentificarea.

## Documentație și validare

Vezi [documentația proiectului](docs/README.md), [arhitectura](docs/architecture.md), [API](api/README.md), [Keycloak](keycloak/README.md), [aplicațiile web](web/README.md), [experimentul](experiment/README.md), [lansatorul Windows](docs/launcher.md) și [validarea executată](docs/validation.md).

Documentul comun și eseurile individuale se redactează de echipă pe baza implementării și a măsurătorilor proprii. Responsabilitățile și regulile Git de mai sus rămân cele din propunerea echipei.
