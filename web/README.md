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
