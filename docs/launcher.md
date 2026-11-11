# Pornire și oprire pe Windows

Dublu click pe `SecureSync.bat` din rădăcina proiectului deschide meniul:

- **1 — Pornire completă**: pornește Docker Desktop dacă este necesar, construiește și pornește serviciile, verifică disponibilitatea lor și deschide Documente și Portal în browserul implicit.
- **2 — Oprire completă**: oprește și elimină containerele și rețeaua proiectului SecureSync, păstrând bazele de date, PDF-urile și fișierul `.env`.
- **3 — Stare**: afișează containerele proiectului și adresele aplicațiilor.
- **0 — Ieșire**: închide meniul fără să oprească aplicația.

Se pot folosi și comenzile directe, din orice director:

```bat
SecureSync.bat start
SecureSync.bat stop
SecureSync.bat status
```

Pentru pornire fără deschiderea browserului:

```bat
SecureSync.bat start -NoBrowser
```

Docker Desktop trebuie să fie instalat și configurat pentru Linux containers. Launcherul așteaptă maximum 180 de secunde pornirea motorului Docker. După construirea containerelor, așteaptă maximum 120 de secunde disponibilitatea Keycloak, API, Documente și Portal. Dacă o comandă Docker eșuează, pornirea se oprește și afișează eroarea; codul de ieșire este transmis apelantului.

La prima pornire, `.env` este generat cu parole aleatoare prin `scripts/init-env.ps1`. Un fișier existent nu este suprascris. Prima construire poate dura câteva minute pentru descărcarea dependențelor și rularea testelor API.

Oprirea vizează numai proiectul Compose `securesync`; nu închide motorul Docker Desktop și nu oprește alte proiecte Docker. Nu folosește `down -v`. Ferestrele deja deschise în browser pot rămâne vizibile după oprire, dar aplicația nu mai răspunde până la o nouă pornire.

`SecureSync.bat` este un wrapper pentru `scripts/manage-app.ps1`. Politica de execuție PowerShell este specificată numai pentru procesul pornit de wrapper, fără modificarea configurației Windows. Acțiunile acceptate sunt limitate la meniu, pornire, oprire și stare.

Testele launcherului rulează fără modificarea containerelor reale:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/test-launcher.ps1
```
