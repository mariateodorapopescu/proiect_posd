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
Nu există autentificare automată prin parole stocate în script.

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
.\.venv\Scripts\python.exe experiment/analyze.py experiment/data/jwt experiment/data/introspection --output experiment/data/summary.json --plot experiment/data/comparison.png
```

Raportul grupează după strategie și TTL, include totalul repetărilor valide,
cenzurate și invalide și raportează p50, p95, minim, maxim și media. Cu cel puțin
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
throughput sub încărcare folosiți separat un scenariu k6/wrk2 și `docker stats`,
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
