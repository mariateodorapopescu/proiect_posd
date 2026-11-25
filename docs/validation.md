# Validare locală din 11 noiembrie 2026

Validarea de mai jos a fost executată pe proiectul SecureSync local, cu identități demonstrative și baze de date create pentru această implementare.

## Build și teste automate

| Componentă | Comandă executată | Rezultat |
|---|---|---|
| API Java 21 | api/mvnw.cmd -B -ntp package | BUILD SUCCESS, 35 teste, 0 eșecuri/erori/omise, inclusiv administrarea membrilor |
| React | npm test în web/ | 13 teste trecute, inclusiv limita titlului și administrarea membrilor |
| React | npm run build în web/ | TypeScript și ambele builduri Vite trecute |
| Experiment host | python -m unittest discover -s experiment -p test_*.py -v | 25 teste trecute, Python 3.13 |
| Experiment cerință Python 3.12 | docker build și docker run securesync-experiment:local | 25 teste trecute, Python 3.12.16 |
| Containerizare | docker compose up -d --build | Toate cele 6 servicii construite/pornite |
| Configurație | docker compose config --quiet | Trecut |
| Whitespace | git diff --check | Fără erori; Git anunță conversia normală LF/CRLF |

## Integrare reală

`python scripts/verify-stack.py --strategy jwt --check-revocation` și varianta `--strategy introspection` au trecut pe sistemul Docker pornit, cu PostgreSQL real. Au verificat:

- Authorization Code + PKCE cu token emis real și sub/department/rol/scope/audiență corecte;
- SSO la nivel de protocol: aceeași sesiune de autentificare și al doilea client autorizat fără o nouă parolă;
- 401 fără token sau cu token invalid, 403 fără scope ori rol, 200 cu acces permis;
- upload PDF și refuzul unui conținut fals cu MIME PDF, descărcarea identică cu fișierul încărcat;
- vizibilitate pentru proprietar, același departament și ADMIN, refuz pentru alt departament;
- ștergere refuzată pentru alt utilizator, inclusiv din același departament, și ștergere permisă proprietarului;
- absența unei rute publice PDF și revocarea exactă a sesiunii prin Admin API.

Documentele create de script au fost șterse. Separat, exportul final de realm a fost importat într-o bază Keycloak nouă, într-un proiect Compose temporar pe portul 8090. Au trecut autentificarea PKCE, claim-urile de introspecție, ștergerea sesiunii cu 204 și răspunsul inactive ulterior. Proiectul temporar și volumul său au fost eliminate. Această verificare a confirmat că exportul include explicit și scope-ul administrativ necesar, fără intervenții manuale după import.

`npm run test:oidc` a trecut separat cu biblioteca reală `oidc-client-ts` pentru ambii clienți. A creat cererea S256/state/nonce, a procesat callback-ul prin `UserManager.signinRedirectCallback`, a schimbat codul pentru token și a apelat `/api/me` cu 200. Al doilea client a reutilizat sesiunea SSO fără retrimiterea parolei. Au fost verificate claim-urile ID/access token, eliminarea tranzacției și absența utilizatorului dintr-o instanță nouă de stocare în memorie. Transportul HTTP al formularului a rulat local, fără browser; aceasta verifică integrarea bibliotecii, nu aspectul paginii.

## Două măsurători funcționale reale

CLI-ul experimentului a rulat o dată pentru fiecare strategie, cu TTL observat 60 s, 10 cereri de bază, interval de sondare 0,1 s și minimum 5 refuzuri consecutive. S-a păstrat aceeași configurație API și același endpoint; URL-ul API a folosit IPv4 loopback pentru a evita întârzierea de fallback IPv6 de pe host.

| Măsură | JWT local | Introspecție |
|---|---:|---:|
| Repetări valide | 1 | 1 |
| Time-to-deny | 57,8474684 s | 0,009997 s |
| Mediana celor 10 latențe de bază | 7,23935 ms | 11,60175 ms |
| Repetări invalide / cenzurate | 0 / 0 | 0 / 0 |

Datele brute și analiza locală sunt în `.local/experiment/`, ignorat de Git. Execuțiile reale au folosit Python 3.13 și requests 2.32.5; compatibilitatea Python 3.12.16 a fost validată separat prin runnerul Docker. Nu sunt salvate tokenuri, secrete sau identificatori de sesiune/utilizator.

Aceste valori confirmă funcționarea măsurării, cu **o singură repetare per strategie**. Nu sunt o comparație statistică, un benchmark de capacitate sau rezultate finale pentru eseu. Pentru raport, echipa trebuie să colecteze mai multe repetări cu parametri controlați și să interpreteze distribuțiile/intervalele de încredere.

## Verificare efectivă în browser

Verificarea interfeței a fost completată ulterior, tot în 11 noiembrie 2026, folosind browserul integrat și conturile demonstrative locale. Au fost observate direct:

- login în Documente prin formularul Keycloak cu `alice.it` și revenirea la biblioteca privată;
- login în Portal cu aceeași sesiune SSO, fără reintroducerea parolei, cu identitatea `alice.it`, departamentul IT și rolul USER;
- încărcarea fișierului demonstrativ `browser-test.pdf` prin selectorul de fișiere și mesajul de succes în interfață;
- descărcarea prin butonul Descarcă și egalitatea SHA256 cu fișierul original: `48d1b44c862a7ebae9078e0079000824e09e2c6f966a9cbac8b766b5f3d0ce55`, 729 bytes;
- probele din Portal cu token (HTTP 200) și fără token (HTTP 401);
- deconectarea SSO, urmată de solicitarea din nou a parolei când Documente inițiază un login nou;
- lipsa documentului IT din lista utilizatorului `bob.hr`;
- afișarea mesajului de expirare și reautentificarea prin sesiunea SSO;
- refuzul în interfață al unui titlu de 161 de caractere, cu mesajul limitei de 160.

Inspecția a identificat o neconcordanță între titlul de maximum 200 de caractere din interfață și limita API/DB de 160. Interfața folosește acum aceeași constantă și aceeași validare comună de 160, acoperite de un test de regresie. Ambele aplicații au fost reconstruite în Docker și verificate în browser după actualizare.

Capturile locale de verificare sunt în `.local/browser-documente-upload.jpg` și `.local/browser-portal-sso.jpg`. Fișierul încărcat conține doar text demonstrativ și poate fi folosit pentru prezentarea aplicației.

## Lansatorul Windows și repornirea completă

Au trecut 10 teste izolate pentru `SecureSync.bat` și `scripts/manage-app.ps1`, executate cu Windows PowerShell 5.1 prin `scripts/test-launcher.ps1`. Sunt verificate transmiterea codurilor de eroare, comportamentul când motorul lipsește, comenzile proiectului corect, păstrarea volumelor și a unui `.env` existent, generarea inițială, verificarea disponibilității și căile cu spații/din alt director de lucru.

Separat, a fost executat ciclul real:

1. `SecureSync.bat status` a afișat cele șase servicii active.
2. `SecureSync.bat stop` a terminat cu cod 0. Nu au rămas containere ale proiectului, iar porturile 3001, 3002, 8080 și 8081 nu au mai răspuns.
3. `SecureSync.bat start`, lansat din alt director de lucru, a construit/pornit toate serviciile, a așteptat răspunsurile HTTP și a deschis adresele Documente și Portal. A terminat cu cod 0.
4. După repornire, în browser au funcționat din nou loginul prin SSO, identitatea și proba API HTTP 200. Documentul demonstrativ a rămas în listă și a fost descărcat din nou cu același SHA256. Numărul de documente a rămas 1 înainte și după oprire/pornire.

Aplicația a fost lăsată pornită, cu profilul JWT și ambele pagini deschise. Capturile finale sunt `.local/browser-documente-final.jpg` și `.local/browser-portal-final.jpg`. Docker Engine era deja pornit în ciclul real. Detectarea unui motor indisponibil a fost verificată izolat; pornirea efectivă a Docker Desktop din stare oprită nu a fost executată, fără oprirea motorului global în această verificare.

## Rolul IMPLEMENTATOR și administrarea membrilor

Extensia cerută ulterior în aceeași zi a trecut buildul complet API (35 teste), testele web (13) și buildurile React/Docker. Scriptul `configure-members.py` a configurat instanța existentă fără resetarea datelor și a fost repetat pentru a verifica păstrarea contului/parolei/rolurilor existente. Exportul actualizat a fost verificat separat prin import într-o bază Keycloak nouă: loginul implementator.demo, scope-ul Portal și drepturile clientului tehnic au funcționat; proiectul temporar a fost eliminat.

`python scripts/verify-members.py --strategy jwt` și varianta `--strategy introspection` au trecut fiecare **26 de verificări live**, cu conturi temporare proprii șterse în final. Sunt verificate 401/403, scope-ul și rolul simultan, contul curent/conturile tehnice protejate, intrările invalide, atribuirea și retragerea rolurilor, departamentul, păstrarea profilului, claim-urile tokenului nou și refuzul unui token IMPLEMENTATOR vechi după retragerea rolului live. IMPLEMENTATOR singur nu a primit acces implicit la documente.

În browser au fost observate: lipsa tabului pentru USER, apariția lui pentru implementator.demo, lista reală a membrilor, căutarea, protecția propriului cont și confirmarea rolurilor privilegiate. Atribuirea temporară ADMIN și HR pentru carol.it a fost salvată cu succes prin interfață, apoi USER și IT au fost restabilite tot prin interfață. Captura acestei probe este `.local/members-browser-grant.jpg`.

După revenirea la profilul JWT au trecut din nou integrarea bibliotecii OIDC pentru ambele aplicații și matricea completă de documente din `verify-stack.py`, cu propriul fișier de test șters. Documentul demonstrativ anterior este păstrat. Modificările nu au rescris metadatele PDF-urilor sau schema PostgreSQL. Aplicația este lăsată pornită.

## Validare din 22–23 noiembrie 2026: seriile de revocare, încărcarea și interfața reproiectată

Secțiunea înregistrează doar ce a fost executat în această etapă. Rulările pe stack-ul real au fost făcute pe mașina gazdă (macOS, Docker Desktop), cu conturi demonstrative și baze de date locale. Testele unitare ale experimentului și ale aplicațiilor web au fost rulate separat, într-un mediu Linux temporar, cu o copie a codului.

### Teste automate

| Componentă | Comandă executată | Rezultat |
|---|---|---|
| Experiment | `python3 -m unittest discover -s experiment -p 'test_*.py'` | 80 de teste trecute |
| React | `npm test` în `web/` (copie temporară) | 24 de teste trecute |
| React | `npm run build` în `web/` (copie temporară) | TypeScript și buildurile Vite trecute |

### Integrare reală, ambele strategii

| Comandă | Rezultat |
|---|---|
| `python scripts/verify-stack.py --strategy jwt --check-revocation` | Toate verificările trecute; JWT acceptat imediat după revocare, refuzat după 59,589 s |
| `python scripts/verify-members.py --strategy jwt` | PASS, 26 de verificări |
| `python scripts/verify-stack.py --strategy introspection --check-revocation` | Toate verificările trecute; refuz după 0,013 s |
| `python scripts/verify-members.py --strategy introspection` | PASS, 26 de verificări |

Scripturile au rulat după schimbarea clientului HTTP al introspecției în API (HTTP/1.1, vezi mai jos).

### Seriile de revocare

Comenzi: `python experiment/batch.py --strategy <jwt|introspection> --ttl 60 --runs 100 --workers 4 --interval 0.02 --output experiment/data/<strategie>`, apoi `python experiment/analyze.py` pe cele două directoare. Parametri comuni: TTL 60 s, faza de revocare aleatoare, seed 2026, 4 lucrători, sondare la 20 ms, 10 cereri de bază pe repetare. API-ul a fost recreat între strategii.

| Măsură | JWT local | Introspecție |
|---|---:|---:|
| Repetări confirmate / cenzurate / invalide | 100 / 0 / 0 | 100 / 0 / 0 |
| Timp până la refuz, mediana (IÎ 95% bootstrap) | 31,859 s (26,654–37,574 s) | 7,649 ms (7,438–7,857 ms) |
| p95 / p99 / maxim | 56,827 s / 58,794 s / 59,601 s | 9,220 ms / 10,489 ms / 12,483 ms |
| Timp până la refuz minus durata rămasă a tokenului | 1,8–39,0 ms | între −59,2 s și −4,9 s (refuz înainte de expirare) |
| Latența cererilor de bază, mediana (p95) | 3,890 ms (6,689 ms) | 9,255 ms (14,526 ms) |

Observații: la JWT toate punctele stau pe diagonala „timp până la refuz = durată rămasă”, deci API-ul nu aplică toleranță de ceas; ipoteza inițială a unei toleranțe de 60 s nu s-a confirmat. La introspecție, valoarea de ~8 ms este rezoluția măsurătorii (o cerere HTTP completă), nu o întârziere de propagare. Datele brute (`runs.csv`, `samples.csv`) și `summary.json`, `comparison.png`, `ecdf.png` sunt în `experiment/data/`, ignorat de Git.

### Testul de încărcare (k6 și `docker stats`)

Scenariu cu rată constantă de cereri pe endpoint-ul `/api/me`, ratele 50, 100, 200, 400 și 800 de cereri/s, 3 repetări pe rată, cu încălzire și pauză între rulări. Valorile sunt mediane și orientative (n = 3, aceeași mașină gazdă pentru generator, API și Keycloak).

| Rată (cereri/s) | 50 | 100 | 200 | 400 | 800 |
|---|---:|---:|---:|---:|---:|
| JWT: p95 (ms) | 5,6 | 3,8 | 2,1 | 2,6 | 2,2 |
| Introspecție: p95 (ms) | 10,3 | 7,7 | 5,1 | 7,8 | 415 |
| Introspecție: CPU Keycloak (%) | 16 | 25 | 20 | 43 | 94 |

Cu JWT, CPU-ul Keycloak a rămas de cel mult 2% la toate ratele. La 800 de cereri/s, introspecția a pierdut 334 de cereri; punctul de saturare este între 400 și 800 de cereri/s. Constatarea este despre ordinul de mărime, nu un benchmark de capacitate.

### Constatare în timpul testelor: HTTP/2 în clientul de introspecție

La 800 de cereri/s cu introspecție au apărut mii de răspunsuri 401 (3465 și 2089 în două rulări), deși tokenurile erau valide. Logurile au arătat excepții „too many concurrent streams” în clientul HTTP al introspecției (JDK HttpClient cu HTTP/2), pe care Spring Security le raporta ca 401; numărul excepțiilor din log (5554) a coincis cu suma 401-urilor din cele două rulări. S-a fixat versiunea HTTP/1.1 în `SecurityConfiguration`; după schimbare, rulările la 400 și 800 de cereri/s au avut 0 erori. Schimbarea nu a fost însoțită de un test unitar nou.

### Keycloak oprit (`loadtest.py --keycloak-down`)

Comenzi: `python experiment/loadtest.py --strategy <jwt|introspection> --rates 50 --keycloak-down --output experiment/data/keycloak-down-<strategie>`, cu API-ul recreat înainte de fiecare strategie. Scriptul rulează întâi 30 s la 50 de cereri/s (după 20 s de încălzire), apoi oprește Keycloak, repetă 30 s și îl repornește.

| Strategie | Faza | Cereri efectuate | 200 | 401 | 5xx | Cereri pierdute | p50 | p95 |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| JWT local | Keycloak pornit | 1501 | 1501 | 0 | 0 | 0 | 3,1 ms | 6,4 ms |
| JWT local | Keycloak oprit | 1501 | 1501 | 0 | 0 | 0 | 3,6 ms | 6,3 ms |
| Introspecție | Keycloak pornit | 1501 | 1501 | 0 | 0 | 0 | 5,7 ms | 8,5 ms |
| Introspecție | Keycloak oprit | 1057 | 0 | 1057 | 0 | 444 | 3004 ms | 3010 ms |

Cu JWT, API-ul a acceptat în continuare toate cererile cu token valid, fără modificarea latenței. Cu introspecție, toate cererile au fost refuzate cu 401 (fail-closed), fiecare după ~3 s, valoare coerentă cu timeoutul de conectare de 3 s configurat în clientul de introspecție; k6 nu a mai putut ține rata de 50 de cereri/s (35,2 obținute, 444 de iterații pierdute). Nu au apărut 5xx: indisponibilitatea serverului de autorizare ajunge la client ca 401, nu ca 503, ceea ce este o limită de observabilitate, nu doar de securitate.

Limite: o singură rulare, o singură rată (50 de cereri/s), timp de 30 s. Rezultatul JWT depinde de faptul că API-ul avea deja cheile publice (JWKS) în cache de la încălzire; API-ul nu a fost repornit cât timp Keycloak era oprit. O instanță nou pornită fără Keycloak nu a fost testată.

### Variația TTL: 30 s față de 60 s

Seriile s-au repetat cu durata tokenului setată la 30 s în realm (`kcadm.sh update realms/securesync -s accessTokenLifespan=30`), cu aceiași parametri (100 de repetări pe strategie, 4 lucrători, sondare la 20 ms, seed 2026, faza aleatoare). După serii, TTL-ul a fost readus la 60 s, iar `verify-stack.py --strategy jwt --check-revocation` a arătat din nou un time-to-deny de 59,925 s.

| Strategie | TTL | Timp până la refuz, mediana (IÎ 95%) | p95 | Maxim | Refuz față de expirare |
|---|---:|---|---:|---:|---|
| JWT local | 60 s | 31,859 s (26,654–37,574 s) | 56,827 s | 59,601 s | la 1,8–39,0 ms după |
| JWT local | 30 s | 17,064 s (14,753–19,642 s) | 28,278 s | 29,633 s | la 4,1–46,1 ms după |
| Introspecție | 60 s | 7,649 ms (7,438–7,857 ms) | 9,220 ms | 12,483 ms | înainte de expirare |
| Introspecție | 30 s | 7,604 ms (7,356–7,949 ms) | 11,506 ms | 17,164 ms | înainte de expirare |

Cu JWT, mediana este aproape jumătate din TTL în ambele cazuri (0,53 și 0,57), iar fereastra maximă observată este TTL-ul; cu introspecție, TTL-ul nu schimbă timpul până la refuz. Nu a fost rulată o a treia valoare (300 s).

### Date excluse din analiza finală

Fișierele `runs.csv` sunt scrise în mod adăugare, deci rulările repetate în același director se acumulează. În directoarele brute au rămas rânduri care nu fac parte din seriile raportate: 36 de repetări `introspection` cu TTL 60 s, rulate între orele 23:00 și 23:04 UTC, în afara seriei de 100 (care s-a încheiat la 20:21 UTC), și 42 de repetări `jwt` marcate invalide (`token_ttl_differs_from_requested_ttl`), rulate cu `--ttl 30` înainte de schimbarea TTL-ului în Keycloak. Analiza finală a folosit copii filtrate în `experiment/data/clean/` (câte 100 de repetări pe grup, toate confirmate); datele brute nu au fost modificate.

### Ce nu a fost validat în această etapă

Verificarea în browser a interfeței reproiectate (teme, monitor, Lighthouse) și un al treilea TTL (300 s) nu au fost executate la data acestei secțiuni.

## Validare din 25 noiembrie 2026

- Au trecut cele 30 de teste web, verificarea TypeScript și buildurile pentru Documente și Portal. Testul de regresie simulează revenirea cu Înapoi când browserul restaurează pagina și verifică păstrarea tranzacției PKCE pentru Înainte.
- În browser, ambele aplicații au deschis formularele Keycloak de conectare și înregistrare. După revenirea cu Înapoi, acțiunile au fost din nou disponibile. `npm run test:oidc` a confirmat separat loginul și reutilizarea sesiunii SSO.
- Un test HTTP local a trimis formularul de înregistrare cu un cont temporar, a schimbat codul prin PKCE și a apelat `/api/me` cu 200. Contul a primit 403 la listarea documentelor și a apărut în căutarea de membri a implementatorului cu rolurile aplicației și departamentul neatribuite. Contul temporar a fost șters.
