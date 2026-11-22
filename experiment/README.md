# Experimentul de revocare SecureSync

`measure.py` măsoară folosind un singur access token, fără refresh, de la confirmarea
revocării sesiunii Keycloak până la primul răspuns 401/403 urmat de încă patru
refuzuri consecutive. `analyze.py` compară măsurătorile și costul cererilor de bază.
Scripturile nu includ rezultate experimentale precompletate.

## Pregătire

Pornește infrastructura conform README-ului principal și instalează Python 3.12
sau ulterior. Din rădăcina proiectului:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r experiment/requirements.txt
```

Configurează `EXPERIMENT_ADMIN_CLIENT_SECRET` în mediul procesului folosind aceeași
valoare ca pentru clientul confidențial `securesync-experiment-admin` din Keycloak.
Nu transmite secretul printr-un argument CLI și nu îl adăuga în fișiere urmărite de Git.
Serviciul folosește `client_credentials`; conturile utilizatorilor folosesc exclusiv
Authorization Code cu PKCE S256, fără password grant.

Clientul public `securesync-experiment` trebuie să accepte exact
`http://localhost:8765/callback`, iar tokenul să includă `sid`, `sub`, `iat`, `exp`,
issuer-ul realm-ului, audiența `securesync-api` și scope-ul `documents:read`.
Utilizatorul de test trebuie să aibă rolul `USER` sau `ADMIN`.

## Colectare

Cu API-ul pornit în profilul `jwt`:

```powershell
.\.venv\Scripts\python.exe experiment/measure.py --strategy jwt --ttl 60 --runs 5 --output experiment/data/jwt
```

Se deschide browserul pentru autentificare. Scriptul preia codul printr-un server
temporar legat exclusiv de loopback, verifică `state` și schimbă codul folosind
verificatorul PKCE păstrat în memorie. Pentru fiecare repetare se obține o sesiune
nouă; revocarea închide sesiunea SSO, deci poate fi necesară autentificarea din nou.
`measure.py` nu are autentificare automată prin parole stocate în script; autentificarea fără browser există numai în `batch.py`, descrisă mai jos.

Repornește **același API și aceeași bază de date** cu profilul `introspection`,
conform instrucțiunilor principale, și repetă:

```powershell
.\.venv\Scripts\python.exe experiment/measure.py --strategy introspection --ttl 60 --runs 5 --output experiment/data/introspection
```

`--ttl` verifică durata reală `exp - iat`; nu modifică configurația Keycloak.
Pentru intervalul de sondare de 10–50 ms din diagrama temei, folosește de exemplu
`--interval 0.02` (20 ms) la ambele strategii. Valoarea implicită de 100 ms este
potrivită unei verificări rapide, dar are o rezoluție temporală mai mică.
Setează întâi durata în Keycloak pentru un experiment cu alt TTL și obține un
token nou. Parametrii trebuie păstrați identici pentru cele două strategii.
Scriptul verifică profilul efectiv prin `/api/me`; o nepotrivire invalidează
repetarea înainte de revocare.

Pentru un singur test poți furniza un token existent prin variabila de mediu
`SECURESYNC_ACCESS_TOKEN` sau prin `--token-file` către un fișier privat aflat în
afara repository-ului. Nu folosi simultan cele două variante. Un token furnizat
suportă o singură repetare și trebuie să fie încă valid, emis pentru realm-ul și
audiența configurate. Decodarea locală extrage doar metadatele; autentificarea este
verificată de API înainte de apelul administrativ.

## Colectare automată cu repetări multe (`batch.py`)

`measure.py` deschide browserul la fiecare repetare, deci nu este practic pentru serii de
zeci sau sute de repetări. `batch.py` repetă aceeași măsurătoare fără browser. Pentru fiecare
repetare se autentifică într-o sesiune Keycloak nouă (Authorization Code cu PKCE S256,
completând formularul de login local), așteaptă o fracțiune aleatoare din durata de viață a
tokenului și apoi apelează `measure.measure_run` neschimbat: aceleași baze, aceeași revocare,
aceleași reguli `denied` / `censored` / `invalid` și aceleași fișiere `runs.csv` și `samples.csv`.

```powershell
.\.venv\Scripts\python.exe experiment/batch.py --strategy jwt --ttl 60 --runs 100 --interval 0.02 --output experiment/data/jwt
.\.venv\Scripts\python.exe experiment/batch.py --strategy introspection --ttl 60 --runs 100 --interval 0.02 --output experiment/data/introspection
```

- **Faza tokenului.** Cu `--phase random` (implicit), fracțiunile se trag câte una din fiecare
  dintre cele `--runs` intervale egale și se amestecă, astfel încât și o serie mică acoperă
  toată durata de viață. Așteptarea este fracțiunea înmulțită cu durata rămasă minus `--guard`
  (5 s implicit). `--seed` face programul reproductibil. Vârsta tokenului la revocare se
  poate reconstrui din `remaining_at_revoke_s` din `runs.csv`. `--phase none` revocă imediat.
- **Credențiale.** Parola demonstrativă se citește din `DEMO_USER_PASSWORD` din mediu sau din
  `.env` local, numai în memorie, și nu se acceptă ca argument. Se trimite numai către un
  Keycloak de pe loopback și numai către formularul realm-ului configurat. `--keycloak-url`
  trebuie să fie `http://localhost:8080`, ca issuer-ul din token. Utilizatorul implicit este
  `alice.it` (`--username`). Scriptul nu folosește password grant.
- **Durată.** Fiecare repetare JWT durează aproximativ cât TTL-ul (așteptarea plus timpul
  până la refuz), deci 100 de repetări la TTL 60 s înseamnă aproximativ 100 de minute cu un
  singur lucrător. Pentru introspecție, refuzul vine imediat, deci durata este în principal
  așteptarea aleatoare.
- **Paralelism.** `--workers N` (cel mult 16) rulează repetări în paralel și scurtează seria,
  dar adaugă încărcare pe API și Keycloak. Folosește aceeași valoare pentru ambele strategii
  și nu amesteca seriile cu valori diferite. Pentru costul pe cerere rămâne scenariul separat
  de încărcare, nu această serie.
- **Oprire.** O eroare de pregătire (login respins, secret lipsă, TTL mai scurt decât `--guard`)
  oprește seria cu codul 2, fără rezultate inventate. Repetările deja terminate rămân în CSV.
  `invalid` produce tot codul 2, ca la `measure.py`.

## Cost sub încărcare (`loadtest.py` și k6)

Seria din `batch.py` măsoară **cât timp** acceptă API-ul un token revocat. Costul validării se
măsoară separat: `loadtest.py` rulează scenariul k6 `load/k6-api.js` la rate constante de cereri și
citește în paralel `docker stats` pentru containerele `api` și `keycloak`. Ideea: JWT local nu
încarcă Keycloak, introspecția adaugă un apel la Keycloak pentru fiecare cerere.

Cerințe: [k6](https://grafana.com/docs/k6/latest/set-up/install-k6/) instalat pe host (`k6 version`),
Docker pornit, stack-ul local pornit cu strategia măsurată și parola demonstrativă în `.env`.

```powershell
.\.venv\Scripts\python.exe experiment/loadtest.py --strategy jwt --rates 50,100,200,400,800 --duration 30 --output experiment/data/load
# repornește API-ul cu TOKEN_VALIDATION_STRATEGY=introspection, apoi:
.\.venv\Scripts\python.exe experiment/loadtest.py --strategy introspection --rates 50,100,200,400,800 --duration 30 --output experiment/data/load
```

- **Ce face pentru fiecare rată.** 15 s de măsurare în repaus (CPU de bază), apoi autentificare nouă
  (cod + PKCE, fără browser), verificare prin `GET /api/me` că API-ul rulează strategia cerută și
  `--duration` secunde de sarcină cu tokenul transmis prin variabilă de mediu, nu prin argument.
  Tokenul se cere **după** repaus, ca să fie proaspăt când pornește k6: citirea `docker stats` pe un
  sistem tocmai saturat poate dura secunde, iar un token cerut mai devreme (60 s de viață) ar putea
  expira în ultimele secunde ale sarcinii și ar produce 401 fără legătură cu strategia. Durata plus
  `--guard` trebuie să încapă în durata de viață a tokenului, altfel scriptul se oprește înainte de
  sarcină. Dacă un scenariu steady primește totuși 401/403, scriptul afișează un avertisment.
- **Repetări și ordine.** `--repeats N` repetă toată lista de rate, iar `--shuffle` amestecă ordinea
  în fiecare repetare (reproductibil cu `--seed`). Fiecare rată primește un rând pe repetare în `load.csv`;
  schema fișierului nu se schimbă. Așa efectele de ordine și de încălzire (de exemplu un prim rând mai
  lent după repornirea API-ului) apar ca variație între repetări, nu ca rezultat fals. Dacă ai rulat
  mai devreme sub saturare, repornește și Keycloak (`docker compose restart keycloak`, apoi așteaptă
  un minut) înainte de o serie nouă: după rulări saturate memoria lui rămâne ridicată și poate falsifica
  seria următoare.
- **Încălzire.** Înainte de serie rulează `--warmup-seconds` (20 implicit, 0 o oprește) de sarcină la
  rata mediană (`--warmup-rate`), care nu se înregistrează. Fără ea, prima rată include compilarea JIT
  și inițializarea pool-urilor, iar costul pe cerere la rate mici iese umflat. Folosește aceeași
  încălzire la ambele strategii.
- **Rată fixă.** Executorul `constant-arrival-rate` păstrează rata indiferent de latență. Dacă API-ul
  nu ține pasul, apar `dropped_iterations` și latențe mari în loc ca testul să încetinească tăcut.
- **Rezultat.** O linie în `load.csv` per rată: cereri/s obținute, p50/p95/p99, statusuri, CPU mediu
  în repaus și sub sarcină, **CPU ms per cerere** (`(CPU_sarcină − CPU_repaus)/100 · 1000 / cereri_pe_s`,
  în milisecunde de un nucleu, deoarece `docker stats` raportează 100% per nucleu) și memoria maximă.
- **Endpoint.** Implicit `/api/me`, care izolează validarea tokenului. Cu `--endpoint /api/documents`
  se adaugă politica de acces și baza de date.
- **Keycloak oprit.** `--keycloak-down` repetă cea mai mică rată după serie, cu `docker compose stop
  keycloak`, și îl repornește mereu la final, chiar dacă k6 eșuează, apoi așteaptă să răspundă.
  Se vede ce strategie mai acceptă tokenuri când furnizorul de identitate nu răspunde. Rezultatul
  depinde de cache-ul JWKS al API-ului, deci îl raportezi așa cum iese, nu cum te aștepți.
  Atenție: oprește Keycloak pentru aproximativ un minut, inclusiv pentru celelalte aplicații.
- **401 sub saturare cu introspecție (observat).** La 800 de cereri/s cu `introspection` k6 a numărat mii de 401, deși tokenurile erau valide. Jurnalul API-ului conține, pentru fiecare, `AuthenticationServiceException: I/O error on POST request for ".../token/introspect": too many concurrent streams`; numărul de excepții (5554) a coincis exact cu numărul de 401 din cele două rulări. Clientul HTTP al API-ului către Keycloak cedează la concurență mare, excepția iese din filtrul de securitate, iar redirectul intern către `/error` (care cere autentificare) o transformă în 401, nu în 5xx. Consecințe: (1) rândurile de la ratele care produc astfel de erori nu măsoară doar costul Keycloak, ci și limita acestui client și se raportează ca atare; (2) un 401 nu înseamnă automat refuz de autorizare cu introspecție, de aceea măsurătoarea de revocare cere cinci refuzuri consecutive și rulează fără concurență. Verificare: `docker compose logs --since 30m api | grep -c "AuthenticationServiceException: I/O error"`.
- **Raport.** `python experiment/load_report.py experiment/data/load/load.csv --output experiment/data/load/summary.json --plot experiment/data/load/load.png`
  grupează rândurile `steady` pe strategie și rată (mediană și min–max pe repetări), afișează un tabel
  și costul marginal de CPU pe cerere suplimentară (panta regresiei CPU% față de cereri/s, în
  `--slope-range`, implicit 50–400, sub saturare; 10 · pantă = ms de un nucleu pe cerere). Rândurile
  `keycloak_down` se listează separat. Cu 3 repetări nu se calculează intervale de încredere.
- **Limite.** `docker stats` citește la 1–2 s, deci valorile sunt medii grosiere. Un client k6 pe aceeași
  mașină consumă CPU și el. Notează procesorul, memoria alocată Docker și ce altceva rulează, și repetă
  seria de mai multe ori înainte să tragi concluzii. Fără `docker` disponibil, coloanele de CPU rămân
  goale (nu sunt inventate), iar cele k6 se completează.

## Metoda și fișierele rezultate

1. Verifică identitatea și strategia prin `GET /api/me` și cere documentele de
   `--baseline-requests` ori (implicit 10). Orice răspuns diferit de 200 invalidează
   repetarea. Cererile măsoară costul HTTP complet, inclusiv politica și baza de date.
2. Revocă exclusiv sesiunea `sid` a tokenului prin
   `DELETE /admin/realms/{realm}/sessions/{sid}?isOffline=false`. O confirmare 204
   definește începutul ferestrei. 404 nu este tratat ca revocare reușită.
3. Continuă cererile cu **același token**, fără reautentificare sau refresh.
   Ceasul monoton măsoară latențele și intervalele. Primul refuz se măsoară la
   primirea răspunsului; următoarele patru refuzuri confirmă rezultatul.
   Un 200 resetează secvența de refuzuri.
4. `runs.csv` păstrează o linie per repetare, cu strategia, TTL-ul observat,
   durata rămasă la revocare, latența revocării și rezultatul. `samples.csv`
   păstrează fiecare răspuns HTTP: fază, status, latență și offset față de
   confirmarea revocării. Offseturile de bază sunt negative.

`denied` înseamnă refuz confirmat. `censored` înseamnă că nu s-a obținut o secvență
confirmată înainte de `--max-wait` (implicit 90 secunde). `invalid` înseamnă
eroare de rețea, 5xx, alt răspuns neașteptat, token expirat înainte de revocare sau
verificare de bază eșuată. Aceste situații nu sunt convertite în refuzuri rapide.
Erorile de pregătire, de exemplu secret lipsă, opresc scriptul fără a inventa o
repetare. Un rezultat `invalid` produce codul de ieșire 2.

Nu se salvează parole, secrete, tokenuri, identificatori de utilizator sau de
sesiune. Redirecturile HTTP ale cererilor care poartă tokenuri sunt refuzate.
HTTP fără TLS este acceptat numai pentru loopback; folosește HTTPS pe alt host.

## Analiză

```powershell
.\.venv\Scripts\python.exe experiment/analyze.py experiment/data/jwt experiment/data/introspection --output experiment/data/summary.json --plot experiment/data/comparison.png --ecdf-plot experiment/data/ecdf.png
```

`--ecdf-plot` scrie două grafice: ECDF-ul timpului până la refuz pentru fiecare strategie și TTL, și
timpul până la refuz în funcție de durata rămasă a tokenului la revocare (cu dreapta "refuz exact
la expirare"). Al doilea grafic arată dependența de faza tokenului pentru JWT local și absența ei
pentru introspecție.

Raportul grupează după strategie și TTL, include totalul repetărilor valide,
cenzurate și invalide și raportează p50, p95, p99, minim, maxim și media. p99 este informativ
numai cu aproximativ 100 de repetări confirmate sau mai multe; citește-l împreună cu `n`.
Pentru fiecare grup raportul include și funcția de repartiție empirică (ECDF) a timpului până la
refuz, perechile (durata rămasă la revocare, timp până la refuz) și diferența dintre ele
(`denial_minus_remaining_s`): aproape de 0 înseamnă refuz doar la expirarea tokenului, clar
negativ înseamnă refuz mai devreme. Cu cel puțin
două repetări se calculează intervalul bootstrap de încredere 95% pentru mediana
ferestrei de revocare. Latența de bază este raportată atât pentru toate cererile
200 cumulate, cât și pentru medianele per repetare; bootstrapul latenței resamplează
repetările, nu cererile corelate din aceeași repetare.

Cu repetări cenzurate, cuantilele ferestrei de revocare descriu **doar repetările
cu refuz confirmat**; nu reprezintă o estimare a distribuției complete. O singură
repetare poate verifica funcționarea, însă nu oferă interval bootstrap și nu
justifică o concluzie statistică. Numărul de cereri de bază, concurența, TTL-ul,
setul de documente, resursele Docker și intervalul trebuie menținute comparabile.

Implicit cererile sunt secvențiale, fără concurență. `--interval` reprezintă pauza
după fiecare răspuns, deci rezoluția observată include intervalul și latența HTTP.
Măsurarea nu separă CPU de rețea, baza de date sau validarea tokenului; pentru
throughput sub încărcare folosește `loadtest.py` (k6 și `docker stats`, secțiunea de mai sus),
înregistrând configurația hardware. Aceste scripturi nu pretind un benchmark
concurent sau consum de resurse pe care nu le măsoară.

## Teste automate

```powershell
python -m unittest discover -s experiment -p 'test_*.py' -v
python -m compileall -q experiment
```

Testele folosesc răspunsuri și ceasuri controlate, fără revocarea unor sesiuni reale.
Acoperă confirmarea refuzurilor, revenirea la 200, răspunsuri 403 de bază,
timeout, erori de rețea/5xx, strategie greșită, TTL, validarea metadatelor,
scrierea CSV fără tokenuri și excluderea repetărilor cenzurate/invalide din cuantile.

Pentru verificarea acelorași scripturi în Python 3.12, independent de versiunea
instalată în Windows, din rădăcina proiectului:

```powershell
docker build -t securesync-experiment:local ./experiment
docker run --rm securesync-experiment:local
docker run --rm securesync-experiment:local python --version
```

Imaginea rulează implicit testele, cu un utilizator fără privilegii. Poți înlocui
comanda implicită, de exemplu `python analyze.py --help`. Datele experimentale și
secretele nu sunt incluse în imagine. Baza Docker este fixată prin digest, iar
`requirements-lock.txt` fixează și dependențele tranzitive verificate cu Python
3.12.16. `requirements.txt` enumeră cele două dependențe directe cu versiuni exacte.
Pentru experimentul interactiv folosește
comenzile de pe host: `localhost` și callbackul browserului se referă la host,
iar un container are propriul loopback. Imaginea pentru teste nu schimbă această
configurație de rețea.

Referință: [Keycloak Admin REST API 26.x](https://www.keycloak.org/docs-api/26.0.8/rest-api/).
