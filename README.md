# Pianificatore robusto su trasporto pubblico locale

Progetto per il corso di Ingegneria della Conoscenza, Universita' di Bari.

Un pianificatore di viaggi che non minimizza l'orario teorico di arrivo ma
massimizza la **probabilita' di arrivare entro un orario dato**, usando la
distribuzione reale dei ritardi appresa da dati raccolti sul campo.

Lo stato di avanzamento e' in [PLAN.md](PLAN.md). Le scelte tecniche e il perche'
sono in [docs/decisioni.md](docs/decisioni.md).

---

## 1. Installazione

Serve Python 3.11 o superiore (verificato su 3.14.6).

### Windows (PowerShell)

```powershell
cd C:\Users\MSI\Desktop\ICON
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install --only-binary=:all: -r requirements.txt
```

Se `Activate.ps1` viene bloccato da PowerShell:
`Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass`

### Linux / macOS

```bash
cd /percorso/del/progetto
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install --only-binary=:all: -r requirements.txt
```

Il flag `--only-binary=:all:` e' importante: impedisce a pip di ripiegare su una
compilazione da sorgente di `clingo` o `pyarrow`, che richiederebbe un toolchain
C++. Meglio un errore immediato che una build di venti minuti destinata a
fallire.

### Verifica

```bash
python -m pytest tests/ -q
```

---

## 2. Configurazione dei feed

Questo e' l'unico passo che richiede un intervento manuale, e va fatto **prima di
tutto il resto**: il feed real-time e' una fotografia dell'istante, lo storico dei
ritardi non esiste da nessuna parte e va costruito giorno per giorno.

### 2.1 Cosa cercare

Per ogni citta' servono due indirizzi.

| Cosa | Come si chiama sulle pagine open data | Serve a |
| --- | --- | --- |
| **GTFS statico** | "GTFS", "GTFS statico", "orario programmato", "static schedule" | conoscere l'orario teorico: fermate, linee, corse, calendario |
| **GTFS-RT TripUpdates** | "GTFS-RT", "TripUpdates", "aggiornamenti corse", "trip updates" | **i ritardi**: e' l'unica fonte, senza non c'e' progetto |
| GTFS-RT VehiclePositions | "VehiclePositions", "posizioni veicoli" | facoltativo, ridondanza in caso i TripUpdates siano poveri |

Dove cercarli: il catalogo **Mobility Database**, **Transit.land**, la sezione
"open data" del sito dell'azienda di trasporto, i portali open data comunali e
regionali.

### 2.2 Verificare i feed PRIMA di adottarli

Molte agenzie pubblicano solo le posizioni dei veicoli, senza i ritardi. Un feed
del genere renderebbe il progetto irrealizzabile, e accorgersene dopo tre
settimane di raccolta significa buttare tre settimane.

Per verificare **tutto quello che c'e' in `config.yaml`** in una volta sola —
orario statico compreso — con conteggi e un esempio decodificato per ogni feed:

```bash
python scripts/verifica_feed.py
python scripts/verifica_feed.py --citta torino
```

Chiude con codice 0 solo se ogni feed configurato e' utilizzabile. Da eseguire
ogni volta che si tocca un indirizzo, e ogni tanto durante la campagna: le
agenzie cambiano gli endpoint senza avvisare.

Per giudicare **un singolo indirizzo** che non e' ancora in configurazione:

```bash
python -m src.collector.poll_realtime --diagnostica "https://indirizzo/del/feed"
```

Stampa cosa contiene davvero il feed e chiude con un giudizio esplicito:

```
  versione GTFS-RT      : 2.0
  entita' totali        : 37
    trip_update         : 37
    vehicle_position    : 0
  timestamp del feed    : 2026-08-24T15:21:16+00:00 (1 s fa)
  stop_time_update      : 111
    con campo 'delay'   : 111
    con orario assoluto : 111

  GIUDIZIO: utilizzabile. I ritardi sono ricavabili dall'orario assoluto su 111 passaggi.
```

Se il giudizio e' `NON utilizzabile`, quel feed non va messo in configurazione:
va cercata un'altra citta'.

### 2.3 Stato attuale della configurazione

[config.yaml](config.yaml) contiene gia' due citta' verificate:

| Citta' | trip_updates | vehicle_positions | orario statico |
| --- | --- | --- | --- |
| **roma** (Roma Mobilita') | OK, ritardi espliciti nel campo `delay` | OK | OK, con `.md5` |
| **torino** (GTT) | OK, ritardi espliciti nel campo `delay` | OK | **MANCANTE** |

**Resta da trovare l'orario statico di Torino.** Finche' manca, i dump real-time
di Torino vengono raccolti ma non saranno interpretabili in Fase 3, perche' non
si potra' risalire agli orari programmati. Cercarlo sul portale open data del
Comune di Torino o di GTT (voce "GTFS" o "orario programmato") e incollarlo in
`url_gtfs_statico` sotto `torino`.

Dopo ogni modifica alla configurazione:

```bash
python -m src.collector.poll_realtime --verifica-config
```

Finche' resta anche un solo segnaposto fra i feed obbligatori, il collector si
rifiuta di partire e dice quale campo manca. E' voluto: l'errore piu' costoso in
questo progetto e' scoprire dopo tre giorni di non aver raccolto nulla.

Una prova a vuoto, che esegue un solo giro e termina:

```bash
python -m src.collector.poll_realtime --una-volta --verboso
```

---

## 3. Far girare la raccolta in background

> **La raccolta di questo progetto NON gira piu' su Windows.** E' stata spostata
> su una VM Ubuntu sempre accesa, dopo aver misurato sul PC una copertura reale
> del 7,2%: la macchina si spegne e si sospende, e in ventidue ore di calendario
> aveva raccolto novantacinque giri su millecentoventidue attesi. Le istruzioni
> per la VM sono in [deploy/README_DEPLOY.md](deploy/README_DEPLOY.md); dal PC si
> usano `deploy/sync.sh` per scaricare i dati e
> `ssh vm-icon '~/icon/deploy/stato.sh'` per controllare la raccolta.
>
> Quanto segue resta valido per chi volesse raccogliere in locale, ed e' il
> motivo per cui non e' stato cancellato.

La raccolta deve restare attiva 24 ore su 24 per settimane. Il processo
sopravvive da solo agli errori di rete e riparte pulito dopo un'interruzione: il
compito del sistema operativo e' solo riavviarlo dopo un riavvio della macchina o
un arresto anomalo.

### 3.1 Windows — Utilita' di pianificazione

Il file [docs/collector_windows.xml](docs/collector_windows.xml) contiene un
compito gia' pronto e verificato su questa macchina. Prima di importarlo va
controllato in due punti:

1. i due elementi `<UserId>`, che devono contenere l'utente restituito da
   `whoami` (qui: `rottame\alex`). Se non corrispondono, `schtasks` risponde
   **"Accesso negato"**;
2. `<Command>` e `<WorkingDirectory>`, se il progetto non si trova in
   `C:\Users\MSI\Desktop\ICON`.

```powershell
# Dalla cartella del progetto, in un PowerShell NORMALE (non serve amministratore)
schtasks /create /tn "RaccoltaTPL" /xml "docs\collector_windows.xml"
schtasks /run /tn "RaccoltaTPL"
```

**Il file deve restare in UTF-16.** `schtasks` rifiuta un XML in UTF-8 con
l'errore "impossibile passare a un'altra codifica". Se un editor lo risalva in
UTF-8, riconvertirlo con:

```powershell
$t = Get-Content docs\collector_windows.xml -Raw
[IO.File]::WriteAllText((Resolve-Path docs\collector_windows.xml), $t, [Text.Encoding]::Unicode)
```

Il compito e' configurato per essere autoriparante:

- parte all'accesso dell'utente;
- **riprova ogni 5 minuti all'infinito**, e la politica `IgnoreNew` fa si' che il
  tentativo venga ignorato se il processo e' gia' in esecuzione. In pratica, se
  il processo muore per qualsiasi motivo, entro cinque minuti riparte da solo;
- non ha limite di durata e non si ferma quando il portatile va a batteria.

Usa `pythonw.exe` invece di `python.exe`, quindi non apre nessuna finestra: il
log finisce solo in `logs\collector.log`.

Per fermarlo, controllarlo, rimuoverlo:

```powershell
schtasks /query /tn "RaccoltaTPL" /v /fo LIST | Select-String "Stato","Ultimo"
schtasks /end    /tn "RaccoltaTPL"
schtasks /delete /tn "RaccoltaTPL" /f
```

**Attenzione al risparmio energetico.** Un portatile che va in sospensione non
raccoglie. Prima di lasciarlo andare per settimane, impostare la sospensione su
"mai" quando e' collegato alla corrente (Impostazioni → Sistema → Alimentazione).
Le ore perse compaiono come buchi nei dati e vanno dichiarate nella
documentazione.

### 3.2 Linux — systemd (unita' utente)

Creare `~/.config/systemd/user/raccolta-tpl.service` sostituendo il percorso:

```ini
[Unit]
Description=Raccolta GTFS Real-Time per il progetto ICon
After=network-online.target

[Service]
Type=simple
WorkingDirectory=/percorso/del/progetto
ExecStart=/percorso/del/progetto/.venv/bin/python -m src.collector.poll_realtime
Restart=always
RestartSec=30

[Install]
WantedBy=default.target
```

```bash
systemctl --user daemon-reload
systemctl --user enable --now raccolta-tpl
systemctl --user status raccolta-tpl
journalctl --user -u raccolta-tpl -f
```

**Passo necessario**, altrimenti l'unita' si ferma alla disconnessione:

```bash
loginctl enable-linger "$USER"
```

### 3.3 macOS (e Linux, soluzione rapida)

```bash
cd /percorso/del/progetto
nohup .venv/bin/python -m src.collector.poll_realtime >/dev/null 2>&1 &
echo $! > .collector.pid
```

Per fermarlo: `kill "$(cat .collector.pid)"`. Il processo intercetta il segnale
ed esce fra un giro e l'altro, senza lasciare file scritti a meta'.

`nohup` non fa ripartire il processo dopo un riavvio: per una raccolta di
settimane su macOS conviene un agente `launchd` con `KeepAlive`.

---

## 4. Controllare che stia davvero raccogliendo

Le ultime righe del log, riepilogo orario compreso:

```bash
tail -n 20 logs/collector.log        # Linux / macOS / Git Bash
Get-Content logs\collector.log -Tail 20   # PowerShell
```

Il riepilogo ha questa forma:

```
[bari] ultima ora: 58 salvati, 2 duplicati, 0 errori (rete 0, http 0, non validi 0), 11.4 MB, copertura 100.0%
```

Quanti dump ci sono oggi:

```bash
find data/raw/rt -name '*.pb' | wc -l                          # Linux / macOS / Git Bash
(Get-ChildItem data\raw\rt -Recurse -Filter *.pb).Count        # PowerShell
```

**Cosa guardare.** La copertura deve stare vicino al 100%. Se scende, la colonna
`esito` del manifest giornaliero dice perche':

```
data/raw/rt/<citta>/<AAAA-MM-GG>/_manifest.csv
```

Contiene una riga per **ogni** interrogazione, anche fallita: e' il denominatore
che rende calcolabile la copertura, e va riportato nella documentazione come
indicatore di qualita' del dataset.

Molti `duplicato` non sono un problema: significano che l'agenzia rigenera il
feed meno spesso di quanto noi lo interroghiamo. Molti `payload_non_valido`
invece si': i payload rifiutati sono conservati in `_scarti/` per poter capire
cosa stia arrivando davvero.

---

## 5. Dove finiscono i dati

```
data/raw/rt/<citta>/<AAAA-MM-GG>/trip_updates/<HHMMSS>.pb
data/raw/rt/<citta>/<AAAA-MM-GG>/vehicle_positions/<HHMMSS>.pb
data/raw/rt/<citta>/<AAAA-MM-GG>/_manifest.csv        una riga per interrogazione
data/raw/rt/<citta>/<AAAA-MM-GG>/_scarti/<tipo>/<HHMMSS>.bin
data/raw/rt/<citta>/gaps.jsonl                        finestre senza raccolta
data/raw/rt/<citta>/_battito.json                     ultima raccolta riuscita
data/raw/gtfs/<citta>/<AAAA-MM-GG>.zip                revisioni dell'orario
data/raw/gtfs/<citta>/index.json                      data -> orario valido
```

Le date sono **locali della citta'**, non UTC, perche' la `service_date` del GTFS
e' un concetto in ora locale.

### `index.json` — quale orario vale in quale giorno

L'orario statico di Roma cambia quasi ogni giorno e i `trip_id` non sono stabili
nel tempo: un dump real-time e' interpretabile solo insieme alla versione
dell'orario in vigore **quel** giorno. `index.json` tiene questa mappa:

```json
{
  "giorni": {
    "2026-08-25": {"file": "2026-08-25.zip", "md5": "e328ed0e...", "origine": "scaricato"},
    "2026-08-26": {"file": "2026-08-25.zip", "md5": "e328ed0e...", "origine": "invariato"}
  },
  "versioni": {"e328ed0e...": {"file": "2026-08-25.zip", "prima_data": "2026-08-25"}}
}
```

Nei giorni senza modifiche non viene scritto un nuovo archivio, solo un marcatore
che punta al precedente. In Fase 3 la funzione `versione_valida(indice, data)`
risolve anche le date scoperte, applicando la regola "vale l'ultima revisione
precedente".

### `gaps.jsonl` — quando NON abbiamo raccolto

Una riga JSON per ogni finestra senza raccolta:

```json
{"citta":"roma","inizio":"...","fine":"...","durata_secondi":21600,"causa":"processo_non_attivo"}
```

Le cause sono `processo_non_attivo` (il collector era spento: rilevato al riavvio
dal confronto con `_battito.json`) e `errori_di_rete_prolungati` (il collector
girava ma nessun feed rispondeva per oltre `soglia_interruzione_secondi`).

Serve a due cose: **escludere quelle finestre dal backtesting** — senza, una
coincidenza mai osservata verrebbe scambiata per una coincidenza persa — e
**dichiarare onestamente la copertura** nella documentazione.

### Copia di sicurezza

`data/` e' fuori da git: e' troppo grande e ricostruibile solo raccogliendolo di
nuovo, cosa che per definizione non e' possibile.

Volume misurato: un giro completo sulle due citta' pesa **910 KB**, cioe' circa
**1,3 GB al giorno** grezzi, piu' ~48 MB per ogni revisione dell'orario di Roma.
Su trenta giorni sono nell'ordine dei 40 GB. **Fatene una copia di sicurezza su
un secondo supporto**: se si perde, si perde il progetto.
