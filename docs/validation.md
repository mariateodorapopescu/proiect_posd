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
