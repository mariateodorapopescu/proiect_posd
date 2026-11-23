# Scenariu de demonstrație (~10 minute)

Scenariul parcurge, în ordine: SSO între două aplicații, controlul accesului, apoi comparația dintre strategiile de revocare (`jwt` și `introspection`), cu măsurătorile din experiment. Timpii sunt estimări de pregătit; se confirmă la prima repetiție completă și se ajustează aici.

Parola conturilor demonstrative este `DEMO_USER_PASSWORD` din `.env`. Nu o afișa pe ecran: ține `.env` închis și scrie parola din memorie sau dintr-un manager de parole.

## 0. Pregătire înainte de prezentare (cu 15–20 minute înainte)

1. **Porturi libere.** `8080` (Keycloak), `8081` (API), `3001` (Documente), `3002` (Portal). Alte aplicații Java pornite local pot ocupa `8080`/`8081` pe IPv6 și cauzează 401 aparent inexplicabil. Verificare:
   ```bash
   lsof -nP -iTCP:8080 -iTCP:8081 -sTCP:LISTEN
   ```
   Trebuie să apară doar procesele Docker.
2. **Stack pornit și API pe `jwt`:**
   ```bash
   docker compose up -d
   docker compose ps
   ```
3. **Verificare rapidă** (rulează o dată, cu 15 minute înainte):
   ```bash
   python scripts/verify-stack.py --strategy jwt --check-revocation
   ```
4. **Documentele de pe ecran:** ferestre separate, nu tab-uri, pentru Documente și Portal. Închide celelalte aplicații care trimit notificări.
5. **Browser curat.** Fereastră nouă, fără sesiuni SSO rămase, ca prima autentificare să ceară parola. Temă la alegere (butonul din antet); testează ambele pe proiector.
6. **Fișier PDF mic** pregătit pentru încărcare (sub 10 MiB).
7. **Graficele deschise** într-un tab separat: `experiment/data/ecdf.png` și, după corectarea legendei, `experiment/data/comparison.png`.
8. **Video de rezervă** (30–60 s) înregistrat o dată, cu pașii 3 și 4 de mai jos, pentru cazul în care stack-ul nu pornește în ziua prezentării.

## 1. SSO între Documente și Portal (~2 minute)

| Pas | Acțiune | Ce se observă |
|---|---|---|
| 1.1 | Deschide Documente (`http://localhost:3001`), apasă **Continuă cu Keycloak**, autentifică-te cu `alice.it`. | Redirect către Keycloak, apoi biblioteca privată. |
| 1.2 | Deschide Portal (`http://localhost:3002`), apasă **Continuă cu Keycloak**. | Revii fără să introduci parola: sesiune SSO comună. Portal arată `alice.it`, departamentul IT, rolul USER. |

**De spus:** două aplicații, doi clienți OIDC publici diferiți, Authorization Code cu PKCE (S256), un singur realm. Tokenurile stau doar în memoria paginii, nu în `localStorage`.

## 2. Controlul accesului (~2 minute)

| Pas | Acțiune | Ce se observă |
|---|---|---|
| 2.1 | În Documente, încarcă PDF-ul pregătit și descarcă-l din listă. | Mesaj de succes; descărcarea trece prin API, fără URL public de fișier. |
| 2.2 | (Opțional) Deconectare, autentificare cu `bob.hr` (HR). | Documentul IT al lui Alice nu apare în lista lui Bob. |
| 2.3 | (Opțional) `admin.demo` (ADMIN). | Poate citi și șterge orice document. |

**De spus:** decizia se ia pe trei niveluri: scope, apoi rol, apoi proprietar sau departament. Fără token API-ul răspunde 401, iar fără rolul potrivit 403.

Dacă timpul e scurt, sari peste 2.2 și 2.3 și menționează că matricea de acces este verificată de `verify-stack.py`.

## 3. Revocare cu `jwt` (~2 minute, din care ~60 s de așteptare)

Strategia implicită validează tokenul local, fără să întrebe Keycloak.

| Pas | Acțiune | Ce se observă |
|---|---|---|
| 3.1 | În Portal, tabul **Contul meu**, apasă **Pornește monitorizarea**. | Contor de cereri acceptate. |
| 3.2 | În Documente apasă **Deconectare SSO**. | Sesiunea din Keycloak este închisă. |
| 3.3 | Revino la Portal și așteaptă. | Monitorul rămâne pe „acceptate” până expiră tokenul (TTL 60 s), apoi arată că API-ul a refuzat abia după expirare. |

**De spus în timpul așteptării:** tokenul este un JWT semnat; API-ul îl verifică local, cu cheile publice din JWKS. Revocarea sesiunii nu îl invalidează. Fereastra de revocare este cel mult TTL-ul tokenului: aici până la 60 s.

Dacă tokenul expiră înainte să pornești monitorul, autentifică-te din nou (monitorul cere cel puțin 3 s de valabilitate).

## 4. Revocare cu `introspection` (~2 minute)

Schimbarea strategiei repornește API-ul și durează ~30 s. Fă-o cât vorbești despre grafice (secțiunea 5) sau înainte de secțiunea 3, dacă preferi ordinea inversă.

```bash
TOKEN_VALIDATION_STRATEGY=introspection docker compose up -d --force-recreate --no-deps api
sleep 30
```

Apoi repetă pașii 1.1, 3.1 și 3.2. De data aceasta monitorul arată refuzul în aproximativ o secundă după **Deconectare SSO**, cu zeci de secunde înainte de expirarea tokenului. API-ul întreabă Keycloak la fiecare cerere (RFC 7662).

La final readu API-ul pe `jwt`, fără comentarii pe linie:

```bash
docker compose up -d --force-recreate --no-deps api
```

## 5. Rezultatele experimentului (~2 minute)

Date din 100 de repetări pe strategie, TTL 60 s, același utilizator și aceleași documente; revocare prin Admin API a sesiunii; sondare la 20 ms. Toate cele 200 de repetări au fost confirmate (0 cenzurate, 0 invalide).

| Metrică | `jwt` | `introspection` |
|---|---|---|
| Timp până la refuz, mediana | 31,9 s (IÎ 95%: 26,7–37,6 s) | 7,6 ms (IÎ 95%: 7,4–7,9 ms) |
| p95 / maxim | 56,8 s / 59,6 s | 9,2 ms / 12,5 ms |
| Latența unei cereri normale, mediana (p95) | 3,9 ms (6,7 ms) | 9,3 ms (14,5 ms) |

Arată `ecdf.png`:
- panoul din dreapta: pentru `jwt`, timpul până la refuz este egal cu durata rămasă a tokenului (toate punctele pe diagonală); pentru `introspection`, refuzul vine la prima cerere, indiferent de durata rămasă;
- cei ~8 ms ai introspecției sunt o cerere HTTP completă, deci limita rezoluției măsurătorii.

Încărcare (k6, rată constantă de cereri, `docker stats`): `jwt` ține Keycloak aproape inactiv (sub 2% CPU) până la 800 de cereri/s. Introspecția încarcă Keycloak (de la 16% CPU la 50 de cereri/s la 43% la 400) și își pierde stabilitatea între 400 și 800 de cereri/s. Cifrele sunt orientative: mediane din 3 repetări, aceeași mașină gazdă.

**Concluzie de spus:** introspecția reduce fereastra de revocare de la ~30 s (în medie) la milisecunde, cu preț în latență, CPU și dependență de disponibilitatea Keycloak. `jwt` este ieftin și independent de Keycloak, dar revocarea este limitată de TTL.

## 6. Limite de spus deschis

- un singur utilizator, Docker local pe loopback, două valori de TTL (60 s pentru tabelul de mai sus, 30 s ca verificare: la `jwt` mediana de 17,1 s, din nou aproape jumătate din TTL);
- se revocă sesiunea prin Admin API; nu sunt acoperite retragerea de roluri sau alte fluxuri de logout;
- Keycloak oprit (o rulare, 50 de cereri/s, 30 s): `jwt` a acceptat în continuare toate cele 1501 de cereri cu token valid, fără schimbarea latenței, pentru că avea deja cheile publice în cache; `introspection` a refuzat toate cererile cu 401, după ~3 s fiecare (timeoutul de conectare). Detalii în `docs/validation.md`.

## Plan B

| Problemă | Ce faci |
|---|---|
| Stack-ul nu pornește sau portul e ocupat | `lsof -nP -iTCP:8080 -iTCP:8081 -sTCP:LISTEN`; oprește procesul străin, apoi `docker compose up -d`. Dacă nu se rezolvă în 2 minute, treci la video. |
| 401 imediat după login | Verifică dacă API-ul rulează (`curl -s http://localhost:8081/api/health`) și dacă nu a rămas alt proces pe `8081`. |
| Tokenul a expirat înainte de monitor | Apasă din nou autentificarea (SSO nu cere parola). |
| Introspecția nu apare după schimbare | Mai așteaptă ~30 s după `--force-recreate`; verifică strategia cu `python scripts/verify-stack.py --strategy introspection`. |
| Nimic nu merge | Redă videoul de rezervă și prezintă `ecdf.png` și tabelul de la secțiunea 5. |
