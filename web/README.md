# Aplicațiile SecureSync

Două aplicații React 19 + TypeScript + Vite folosesc aceeași integrare OIDC,
cu clienți Keycloak diferiți. Interfața Documente încarcă, listează, descarcă și
șterge PDF-uri exclusiv prin API. Portal afișează identitatea confirmată de API
și permite compararea răspunsurilor pentru cereri cu și fără token.

Portal include și tabul **Administrare membri**, disponibil numai conturilor
cu rolul `IMPLEMENTATOR` și scope-ul `members:manage`. Acesta listează conturile
existente, permite căutare și paginare și salvează explicit rolurile
`USER` / `ADMIN` / `IMPLEMENTATOR` și departamentul `IT` / `HR`.

## Rulare locală

Din `web/`, cu Node 22.14+:

```powershell
npm ci
npm run dev:documente
# În alt terminal:
npm run dev:portal
```

URL-uri implicite: Documente `http://localhost:3001/`, Portal
`http://localhost:3002/`, API `http://localhost:8081`, Keycloak
`http://localhost:8080/realms/securesync`. Pentru sistemul complet se folosește
Docker Compose din rădăcina proiectului.

Variabilele opționale din `web/.env` sunt `VITE_AUTHORITY`, `VITE_API_URL`,
`VITE_DOCUMENTE_URL` și `VITE_PORTAL_URL`. Variabilele Vite sunt publice și nu
trebuie să conțină secrete. În Docker acestea sunt argumente de build;
`APP_NAME=documente` sau `APP_NAME=portal` alege aplicația servită pe portul 80.

## Autentificare și SSO

Clienți publici: `securesync-documente`, `securesync-portal`. Folosim
Authorization Code cu PKCE S256. Callback-ul de login și cel de logout sunt
la rădăcina fiecărei origini. Fiecare login folosește un nonce aleator nou,
verificat de bibliotecă la procesarea ID tokenului. Cerem scope-urile
`openid documents:read documents:write`, iar Portal cere suplimentar
`members:manage`; identitatea și departamentul sunt mapate explicit de scope-ul
implicit `securesync-claims`, fără dependență de scope-ul standard `profile`.
Tokenurile și utilizatorul OIDC sunt exclusiv în
`InMemoryWebStorage`; numai tranzacția temporară `state` / nonce / PKCE verifier
este ținută în `sessionStorage`, pentru revenirea după redirect.

Nu folosim `localStorage`, nu persistăm tokenurile și nu reînnoim automat
tokenul. La expirare sau la 401 pentru sesiunea curentă, interfața cere o nouă
autentificare. Un 401 pentru o cerere veche nu închide o sesiune mai nouă.
După reîncărcare, tokenul din memorie dispare; butonul Autentificare inițiază un
nou redirect, iar Keycloak poate refolosi sesiunea SSO.

Verificare manuală SSO: autentificare în Documente, deschidere Portal,
Autentificare în Portal; Keycloak trebuie să revină fără solicitarea parolei.
Verificare logout: Deconectare SSO apoi autentificare în cealaltă aplicație;
Keycloak trebuie să ceară parola. Un JWT deja emis poate rămâne acceptat până
la expirare în profilul local `jwt`, conform experimentului proiectului.

Politica este aplicată de API. Ascunderea sau dezactivarea butoanelor este
doar feedback UI, nu un mecanism de autorizare. Încărcarea are validare de
format și dimensiune în browser, apoi validare independentă în API.
Titlul documentului este obligatoriu și poate avea cel mult 160 de caractere,
aceeași limită fiind aplicată în API și baza de date.

## Administrarea membrilor

Contul demonstrativ `implementator.demo` are rolurile `USER` și `IMPLEMENTATOR`
și folosește parola demonstrativă configurată în `.env`. După autentificarea
în Portal, selectează **Administrare membri**, caută membrul și alege rolurile
și departamentul. **Salvează pentru …** aplică modificarea; atribuirea unui
nou rol ADMIN sau IMPLEMENTATOR cere întâi revizuirea și confirmarea explicită.

ADMIN administrează documentele. IMPLEMENTATOR administrează drepturile
membrilor; pentru acces la documente are nevoie și de USER sau ADMIN. Contul
curent este afișat protejat și nu își poate modifica propriile drepturi.
API-ul verifică separat drepturile curente la fiecare cerere de administrare.
Rolul sau scope-ul din interfață nu înlocuiește această verificare.

Modificările se păstrează în memorie când schimbi taburile Portalului. Căutarea,
paginarea și actualizarea listei cer confirmare dacă există modificări nesalvate.
După salvare, destinatarul se autentifică din nou pentru a obține claim-urile
actualizate. Documentele existente nu își schimbă automat departamentul.
O eroare de serviciu cere reîncărcarea listei pentru verificarea stării reale;
interfața nu pretinde că operațiile Keycloak sunt o tranzacție atomică.

## Monitor de revocare în Portal

Tabul **Contul meu** din Portal include secțiunea **Cât mai este acceptat tokenul tău?**.
Monitorul trimite la fiecare secundă `GET /api/me` cu tokenul curent, ținut doar în memorie, și
afișează valabilitatea rămasă, numărul de cereri și o cronologie a răspunsurilor (✓ acceptat,
✕ refuzat, ! fără răspuns sau eroare). Nu folosește `request()`: acolo un 401 închide sesiunea
locală, iar monitorul trebuie să continue cu același token.

Un refuz se confirmă după trei răspunsuri consecutive 401 sau 403; un 200 resetează seria, iar
erorile de rețea sau 5xx nu confirmă și nu anulează refuzul. Rezultatul distinge:

- **refuzat înainte de expirare**: tokenul era încă valabil, deci sesiunea a fost revocată sau
  drepturile au fost retrase;
- **refuzat după expirare**;
- **acceptat până la expirare**: monitorul se oprește cu 1,5 s înainte, pentru că aplicația
  se deconectează la expirare. Cu validarea locală JWT, aceasta este comportamentul așteptat.

Interfața nu află când a fost revocată sesiunea; vede doar răspunsurile API-ului. Demonstrație:
pornește monitorul, apoi în alt tab apasă „Deconectare SSO” în Documente sau închide sesiunea
din consola Keycloak. Cu `TOKEN_VALIDATION_STRATEGY=introspection` refuzul apare în aproximativ o
secundă; cu `jwt`, tokenul rămâne acceptat până expiră. Monitorul este o demonstrație, nu o
măsurătoare: rezoluția este de o secundă, iar măsurătorile reale sunt în `experiment/`.
Logica este în `shared/monitor-policy.mjs`, acoperită de `tests/monitor.test.mjs`; interfața
nu a fost verificată automat într-un browser.

## Aspect, teme și structura codului

Stilurile sunt într-un singur fișier, `shared/style.css`, organizat pe secțiuni (tokeni,
bază, butoane, formulare, layout, componente, Portal, responsive, mișcare redusă).
Culorile sunt variabile CSS definite o singură dată cu `light-dark()`: interfața urmează
tema sistemului, iar butonul din antet ciclează între „Sistem”, „Luminoasă” și
„Întunecată”. Alegerea se păstrează în cookie-ul `securesync-theme` (un an, `SameSite=Lax`,
`Secure` pe HTTPS), nu în `localStorage`: cookie-urile nu țin cont de port, așa că Documente
(3001) și Portal (3002) folosesc aceeași temă. Cookie-ul conține doar „light” sau „dark”;
„Sistem” îl șterge. Tokenurile rămân numai în memorie, conform `.agents/security.md`.
Pe subdomenii diferite ar fi nevoie de atributul `Domain`.
Logica ciclului este în `shared/theme-policy.mjs`, acoperită de `tests/theme.test.mjs`.

Direcția vizuală este „aerisit și plutitor”: bară laterală de sticlă cobalt, secțiuni-panouri
de sticlă pe lumini difuze animate, un singur font de sistem cu titluri groase (fără fonturi
descărcate). Pagina de intrare are o scenă 3D făcută numai din CSS (`shared/Scene.tsx`:
o cheie extrudată, un inel în orbită și trei documente de sticlă, înclinate ușor după cursor).
Sticla are mereu margine vizibilă (3:1, verificat în teste) și fundal opac unde
`backdrop-filter` nu e suportat; mișcarea se oprește la `prefers-reduced-motion`. Sigla este
în `shared/KeyMark.tsx`. Variantele anterioare sunt în istoricul git și în `web/design-alt/`.
Contrastul perechilor de culori, în ambele teme, este verificat automat de
`tests/contrast.test.mjs` (4,5:1 pentru text, 3:1 pentru marginile de sticlă).

Accesibilitate: link „Sari la conținut”, inel de focus cu contrast peste 4,5:1 pe ambele
teme, perechile de culori text/fundal verificate la cel puțin 4,5:1 și respectarea
`prefers-reduced-motion`. Contrastul s-a calculat o dată cu un script, nu cu un audit
automat în browser (Lighthouse/axe), deci un astfel de audit rămâne de făcut.

Componentele sunt separate pe fișiere: `main.tsx` (aplicația și antetul), `Documents.tsx`,
`Portal.tsx`, `Members.tsx`, `RevocationMonitor.tsx`, `ThemeToggle.tsx`, `KeyMark.tsx`, plus `ui.ts` pentru
helperele comune.

## Validare

```powershell
npm test
npm run build
# Cu întregul stack local pornit și Python 3.12+ disponibil:
npm run test:oidc
```

`build` verifică tipurile și construiește separat ambele aplicații. Testele
folosesc runner-ul Node și acoperă absența tokenurilor persistente după reload,
izolarea sesiunilor, identificarea callback-urilor, limitele PDF și mesajele
pentru erorile HTTP. Regresiile pentru membri verifică rolul și scope-ul necesare,
scope-ul suplimentar exclusiv în Portal, lista permisă de roluri/departamente,
detectarea modificărilor și revizuirea noilor privilegii. Testele unitare
nu demonstrează SSO-ul sau revocarea în sistemul complet.

`test:oidc` verifică biblioteca OIDC instalată cu configurația reală a
aplicațiilor: generează Authorization Code + PKCE S256, autentifică utilizatorul
local de test prin HTTP, apoi `UserManager` procesează callback-ul și schimbă
codul. Verifică nonce-ul, identitatea, claim-urile personalizate, API 200,
eliminarea tranzacției și absența tokenurilor după simularea reloadului.
Portal trebuie să refolosească sesiunea SSO fără o nouă trimitere de credențiale.
Parola se citește în memorie din `.env` al proiectului; tokenurile și codurile
nu sunt afișate sau scrise în fișiere. Se folosește numai instanța demonstrativă
locală. Acest test de protocol și bibliotecă nu verifică randarea, comportamentul
browserului sau accesibilitatea vizuală. Se poate seta `PYTHON` pentru alegerea
executabilului Python.

Integrarea folosește [oidc-client-ts](https://authts.github.io/oidc-client-ts/),
inclusiv `UserManager` și `InMemoryWebStorage`; bibliotecile sunt incluse în
bundle, fără CDN în browser.
