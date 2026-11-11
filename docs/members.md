# Administrarea membrilor în Portal

Rolul **IMPLEMENTATOR** oferă acces la tabul **Administrare membri** din Portal. USER și ADMIN păstrează drepturile de acces la documente; pentru documente, un IMPLEMENTATOR are nevoie și de USER sau ADMIN.

## Cum îl folosești

1. Deschide http://localhost:3002/ și deconectează contul anterior, dacă este necesar.
2. Autentifică-te cu **implementator.demo**. Parola este aceeași parolă demonstrativă, `DEMO_USER_PASSWORD` din `.env`.
3. Deschide **Administrare membri**.
4. Caută un utilizator, bifează rolurile dorite și alege IT sau HR.
5. Apasă **Salvează pentru ...**. Pentru un nou rol ADMIN sau IMPLEMENTATOR, verifică rezumatul și apasă **Confirmă modificarea**.

Rolurile disponibile sunt USER, ADMIN și IMPLEMENTATOR, minimum unul. Pentru revenirea la membru obișnuit, păstrează USER și debifează celelalte roluri. Contul cu care ești conectat este protejat: nu îți poți modifica propriile roluri sau departamentul din acest tab.

Membrul căruia i-ai schimbat accesul se deconectează și se autentifică din nou pentru un token cu noile claim-uri. Documentele vechi își păstrează proprietarul și departamentul salvat la încărcare. Dacă rolul de IMPLEMENTATOR este retras, cererile de administrare sunt refuzate imediat de verificarea online, chiar cu un JWT încă neexpirat.

Conturile USER sau ADMIN fără IMPLEMENTATOR nu afișează acest tab. `admin.demo` rămâne administrator de documente. Conturile de serviciu nu sunt afișate/editabile. Crearea și ștergerea conturilor și schimbarea parolelor nu fac parte din acest tab.

## API și integrare

`GET /api/members?search=&page=0` întoarce maximum 20 de membri și un indicator de pagină următoare. `PUT /api/members/{uuid}/access` primește rolurile și departamentul. Ambele cer scope-ul `members:manage`, rolul IMPLEMENTATOR și confirmarea live în Keycloak a dreptului curent.

API-ul comunică cu Keycloak prin clientul confidențial `securesync-member-admin`. Secretul rămâne pe server, iar permisiunile tehnice sunt manage-users/view-users/view-realm plus scope-ul kc-admin-api. Modificările sunt limitate la rolurile aplicației și atributul department; celelalte date ale profilului sunt păstrate. Nu există o nouă tabelă de utilizatori în PostgreSQL.

Operațiile Keycloak multiple nu sunt o tranzacție atomică. La eșec, API-ul încearcă să restaureze starea inițială și raportează indisponibilitatea sau conflictul. Reîncarcă lista pentru a verifica starea efectivă înainte de o nouă încercare. Blocarea modificărilor este locală instanței API din Compose.

## Instalare existentă

Instalările noi importă rolul, clienții și contul demonstrativ din export. Pentru o bază Keycloak deja existentă, cu serviciul pornit:

```powershell
python scripts/configure-members.py
docker compose up -d --build
```

Scriptul local adaugă un secret tehnic lipsă în `.env` și configurează numai componentele necesare. Nu resetează volume, PDF-uri, parole sau rolurile conturilor existente. Un cont implementator.demo existent este păstrat, inclusiv dacă rolul i-a fost retras intenționat. Bootstrap-ul folosește credențialele administrative locale numai în acel proces; acestea nu sunt transmise aplicațiilor React sau API-ului.
