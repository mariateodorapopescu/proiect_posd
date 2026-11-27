# Keycloak SecureSync

`realm-export.json` configurează realm-ul `securesync` pentru imaginea Keycloak **26.8.2**. Compose îl montează sub numele `securesync-realm.json`, cerut pentru importul la startup.

## Clienți

| Client | Tip | Flux / redirect |
|---|---|---|
| securesync-documente | public | Code + PKCE S256, http://localhost:3001/ |
| securesync-portal | public | Code + PKCE S256, http://localhost:3002/ |
| securesync-experiment | public | Code + PKCE S256, http://localhost:8765/callback |
| securesync-api | confidențial | Autentifică introspecția, fără login sau service account |
| securesync-experiment-admin | confidențial | client_credentials pentru revocarea sesiunii experimentale |
| securesync-member-admin | confidențial | client_credentials server-only pentru administrarea membrilor prin API |

Password grant și implicit flow sunt dezactivate pentru toți clienții aplicației. Redirecturile și originile sunt exacte. Cele două aplicații cer `openid documents:read documents:write`; experimentul cere numai citire.

Client scope-ul `securesync-claims` adaugă identificatorul `sub`, audiența `securesync-api`, username, `department` și `realm_access.roles`. Mapper-ele includ claim-urile în tokenul de acces și în răspunsul de introspecție. Scope-urile opționale `documents:read` și `documents:write` apar în `scope` numai când sunt cerute. `kc-admin-api` este definit explicit în export pentru ca importul într-o bază nouă să fie complet.

Contul serviciului de experiment are rolurile `manage-users` și `view-users` din `realm-management`. În Keycloak 26.8, clientul are și scope-ul implicit **kc-admin-api**, care adaugă audiența Admin API; rolurile administrative singure nu sunt suficiente. Acest secret rămâne exclusiv în scriptul local de experiment, niciodată în React. Scriptul revocă exact `sid` din tokenul testat.

## Identități și durate

Conturile sunt listate în README-ul principal. Parolele și secretele din export sunt referințe la variabile de mediu, rezolvate la import. `.env` nu intră în Git.

TTL-ul tokenului de acces este **60 s**, sesiunea SSO are idle timeout 1800 s și maxim 3600 s. USER/ADMIN sunt roluri de acces la documente; IMPLEMENTATOR administrează membrii din Portal. `implementator.demo` are USER și IMPLEMENTATOR și folosește parola demonstrativă. `department` este un atribut de profil cu valori IT/HR, vizibil utilizatorului dar editabil numai prin administrare. Nu permite utilizatorilor să își schimbe singuri departamentul.

Portal solicită suplimentar scope-ul opțional `members:manage`; Documente păstrează doar scope-urile documentelor. Clientul `securesync-member-admin` are `manage-users`, `view-users`, `view-realm` și scope-ul `kc-admin-api`. Secretul `MEMBER_ADMIN_CLIENT_SECRET` există numai pe server. API-ul verifică live rolul efectiv IMPLEMENTATOR pentru fiecare cerere de administrare.

Schimbă TTL-ul din Realm settings → Tokens pentru alte măsurători. Obține tokenuri noi și folosește aceeași durată pentru ambele strategii. `--ttl` al experimentului verifică durata reală, nu schimbă Keycloak.

## Persistență și configurare

Importul se execută numai dacă realm-ul nu există. O modificare în export sau regenerarea parolelor din `.env` nu suprascrie un realm existent. Aplică modificările în Admin Console sau resetează explicit volumele demonstrative, cu pierderea datelor.

Exportul activează înregistrarea pentru instalările noi. Pentru un realm
`securesync` deja importat, activează **User registration** din **Realm settings
→ Login**. Documente și Portal deschid formularul de înregistrare configurat în
Keycloak. Conturile noi apar în **Administrare membri**, unde implementatorul
le poate atribui rolurile aplicației și departamentul.

Issuer-ul public este `http://localhost:8080/realms/securesync`. API-ul din Docker folosește `http://keycloak:8080` pentru JWKS și introspecție și verifică în continuare issuer-ul public. Aceste URL-uri au scopuri diferite.

Pentru activarea administrării membrilor într-o instalare existentă, rulează `python scripts/configure-members.py` cu Keycloak pornit, apoi reconstruiește/recreează serviciile. Scriptul adaugă componentele necesare și doar un cont demonstrativ lipsă, păstrând conturile și PDF-urile existente. Vezi [administrarea membrilor](../docs/members.md).

## Tema de login

`themes/securesync/login` pornește de la `keycloak.v2` și preia din `web/shared/style.css` tokenii de culoare (light/dark), sticla cu margine vizibilă, luminile difuze, cheia din siglă, razele de 10 px și 26 px, butoanele și alertele „notice”. Cookie-ul `securesync-theme` setat de aplicații alege tema luminoasă sau întunecată, inclusiv atunci când sistemul are cealaltă temă. Fundalul se pune numai pe `html`, altfel `body` ar acoperi luminile. Dacă schimbi valorile de culoare din `style.css`, actualizează și `securesync.css`.

Compose montează tema read-only, iar `start-dev` nu o ține în cache: după o modificare, reîncarcă pagina de login cu Ctrl+F5.

## Surse tehnice

- [Keycloak Docker](https://www.keycloak.org/getting-started/getting-started-docker)
- [Import și variabile de mediu în realm](https://www.keycloak.org/server/importExport)
- [Endpointuri OIDC și introspecție](https://www.keycloak.org/securing-apps/oidc-layers)
- [Actualizări și scope-ul kc-admin-api](https://www.keycloak.org/docs/latest/upgrading/index.html)
