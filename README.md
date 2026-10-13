# Open Unifi

Le novità dei siti dell'Università di Firenze in un posto solo, con **notifiche push**
quando qualcosa viene pubblicato o modificato.

Open Unifi controlla periodicamente le pagine pubbliche dei siti UniFI (news dei corsi,
pagine di orari, calendari, tirocini, regolamenti) e la **bacheca pubblica degli appelli
ESSE3**. Ogni volta che compare un contenuto nuovo, o cambia un testo, una data o un
allegato, salva una nuova versione e avvisa chi è iscritto.

> Progetto indipendente e non ufficiale, non affiliato all'Università degli Studi di Firenze.

## Cosa fa

- **Feed unico** di news e modifiche, con ricerca nel testo e filtri per fonte e tipo.
- **Cronologia e differenze**: per ogni contenuto si vede esattamente cosa è cambiato
  (testo parola per parola, allegati aggiunti, sostituiti o rimossi, testo dei PDF).
- **Appelli d'esame** dalla bacheca pubblica di ESSE3 (senza login): data, orario,
  finestra di iscrizione, docenti. Notifica quando escono nuovi appelli o cambia una data.
- **Notifiche gratuite**:
  - **Web Push** (PWA): Android e computer subito; iPhone dopo "Aggiungi alla schermata
    Home" (iOS 16.4+), con guida passo passo nell'app.
  - **Bot Telegram** opzionale, più un eventuale canale pubblico.
- **Preferenze per iscritto**, senza account: fonti da seguire, parole chiave
  (cercate ovunque), solo novità o anche modifiche, silenzio notturno o riepilogo giornaliero.
  Se escono tanti aggiornamenti insieme arriva un solo messaggio riassuntivo.
- **Link utili e contatti** organizzati in gruppi, con ricerca istantanea.
- **RSS** di tutte le fonti o di una sola.
- **Pannello admin** (`/admin`): iscritti e statistiche, salute delle fonti, aggiunta di
  nuove fonti con anteprima, link utili, annunci con invio di notifica, avvisi quando
  una fonte smette di funzionare.

## Fonti incluse

Corso di Laurea in Medicina e Chirurgia: news (con archivio), orario delle lezioni,
calendario esami di laurea, pagine AFP/tirocini dal I al VI anno, ADE, calendario
esami, per laurearsi, tutorato, norme e regolamenti, organizzazione; appelli ESSE3
dei corsi B240 e B120. Altre fonti si aggiungono dal pannello admin: i siti dei corsi
UniFI usano lo stesso CMS, quindi di solito basta l'URL.

## Architettura

```
backend/   FastAPI + SQLite (un solo container)
  app/scraper/   fetch educato, parser a selettori CSS, ESSE3, rilevazione modifiche
  app/notify/    Web Push (VAPID), bot Telegram (long polling), filtri e orari
  app/routers/   API pubblica, iscrizioni anonime, admin
frontend/  PWA React + Vite + Tailwind (service worker in public/sw.js)
deploy/    istruzioni per il Caddy condiviso con WeRace e Halo
```

Il primo controllo di ogni fonte è una *baseline*: salva quello che c'è già senza
notificare. Dal secondo in poi ogni novità genera una notifica.

## Sviluppo

```bash
# backend
cd backend
python -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
OPENUNIFI_DATA_DIR=./data OPENUNIFI_ADMIN_PASSWORD=dev uvicorn app.main:app --reload
pytest

# frontend (proxy /api verso :8000)
cd frontend && npm install && npm run dev
```

Comandi utili: `python -m app.cli run [slug...]` controlla le fonti subito,
`python -m app.cli hash-password` genera l'hash per la password admin.

## Deploy

Vedi [deploy/DEPLOY.md](deploy/DEPLOY.md): stesso server e stesso Caddy (Let's Encrypt)
di WeRace Timing e Halo F1.
