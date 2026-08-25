# Piano delle fasi

Legenda: `[x]` fatto · `[~]` in corso · `[ ]` da fare · `[!]` bloccato

---

## Vincolo temporale che governa tutto il piano

Il feed GTFS Real-Time e' una fotografia dell'istante: lo storico dei ritardi non
esiste da nessuna parte e va costruito giorno per giorno. Di conseguenza:

- la **Fase 0 e' la priorita' assoluta** e ogni giorno di ritardo nel farla
  partire e' un giorno di dati perso per sempre;
- le **Fasi 1, 2 e la parte di scrittura si possono fare in parallelo** alla
  raccolta, che nel frattempo gira da sola;
- la **Fase 3 non e' avviabile** finche' non c'e' un numero di giorni sufficiente
  a distinguere il giorno della settimana e la fascia oraria. Con meno di due
  settimane piene lo split temporale della Fase 3 non ha abbastanza giorni per
  essere credibile;
- la **Fase 5** consuma tutti i giorni disponibili: piu' tardi si fa, meglio
  esce.

**Data di avvio della raccolta:** 2026-08-25 (Roma e Torino).

---

## Fase 0 — Scaffolding e raccoglitore dati

- [x] Verifica dell'ambiente: Python 3.14.6, wheel disponibili per tutte le
      dipendenze (`clingo` compreso), `git` presente
- [x] `git init`, struttura delle cartelle, `.gitignore`
- [x] `requirements.txt` con versioni fissate e verificate
- [x] `config.yaml` con segnaposto espliciti e validazione che li rifiuta
- [x] `CLAUDE.md`
- [x] `PLAN.md`
- [x] `src/collector/poll_realtime.py`
  - [x] lettura e validazione della configurazione, con tutti gli errori insieme
  - [x] scaricamento con timeout, ritentativi, backoff esponenziale e jitter
  - [x] validazione del payload prima del salvataggio; scarti conservati a parte
  - [x] deduplica dei dump tramite `header.timestamp`
  - [x] manifest giornaliero con una riga per ogni interrogazione, anche fallita
  - [x] archiviazione giornaliera dell'orario statico, confronto tramite .md5
  - [x] cadenza a tick fissi, senza deriva cumulativa
  - [x] log ruotato su file e riepilogo orario
  - [x] uscita ordinata su segnale di terminazione
  - [x] modalita' `--diagnostica` per giudicare un feed prima di adottarlo
- [x] Test: 77 casi, logica pura piu' giri completi su server HTTP locale
- [x] `README.md` con le istruzioni di esecuzione in background
- [x] `docs/decisioni.md` inaugurato

- [x] Scelta delle due citta': Roma (Roma Mobilita') e Torino (GTT)
- [x] Indirizzi dei feed in `config.yaml`, verificati uno per uno
- [x] Raccolta avviata in background

---

## Fase 0-bis — Correzioni dopo la configurazione dei feed reali

- [x] Indirizzi reali di Roma e Torino in `config.yaml`
- [x] Torino corretto da `http://` a `https://`: la porta 80 di GTT non
      accetta connessioni (voce 22 del registro)
- [x] Archiviazione dell'orario statico tramite il file `.md5`, con `index.json`
      che mappa ogni data alla versione valida quel giorno
- [x] `gaps.jsonl`: registro delle finestre senza raccolta, con causa
- [x] Gestione esplicita degli indirizzi non cifrati; credenziali in chiaro
      rifiutate all'avvio
- [x] `scripts/verifica_feed.py`, eseguito su tutti i feed configurati
- [x] Nessun dato da scartare: la raccolta non era mai partita (voce 29)

**Ancora aperto:**

- [ ] **Orario statico di Torino**: manca l'indirizzo. Finche' non c'e', i dump
      real-time di Torino vengono raccolti ma non saranno interpretabili in
      Fase 3, perche' non si potra' risalire agli orari programmati.
- [ ] Copia di sicurezza di `data/` su un secondo supporto (~1,3 GB al giorno)
- [ ] Verifica della copertura dopo il primo giorno pieno

---

## Fase 1 — GTFS statico e base di conoscenza

- [ ] `src/gtfs/loader.py`: lettura di un archivio GTFS in DataFrame (stops,
      routes, trips, stop_times, calendar, calendar_dates, transfers), con
      validazione dei campi obbligatori e messaggi d'errore chiari
- [ ] `src/gtfs/calendar.py`: dato un `service_date`, l'insieme dei trip attivi,
      gestendo `calendar.txt` e le eccezioni di `calendar_dates.txt`
- [ ] `src/kb/rules.lp`: base di conoscenza in ASP
  - [ ] `trasbordo_ammissibile/3` con tempo minimo dipendente dalla fermata
  - [ ] trasbordo a piedi fra fermate distinte entro una soglia di distanza
  - [ ] `accessibile/2` per utenti a ridotta mobilita', con le sue eccezioni
  - [ ] `raggiungibile/2` come chiusura transitiva ricorsiva
  - [ ] vincoli di integrita' che scartino i trasbordi incoerenti
  - [ ] ricorsione e negazione stratificata evidenti e commentate
- [ ] `src/kb/engine.py`: wrapper su clingo, materializza
      `data/processed/transfers.parquet`
- [ ] Misura di atomi generati, tempo di grounding e di solving al crescere del
      numero di fermate, annotata in `docs/decisioni.md`
- [ ] Test per `calendar.py` e per l'engine su un GTFS giocattolo

---

## Fase 2 — Grafo tempo-espanso e ricerca

- [ ] `src/graph/time_expanded.py`: stato `(fermata, istante, numero di cambi)`;
      archi di permanenza a bordo, discesa e trasbordo, cammino a piedi
- [ ] Documentazione della rappresentazione scelta e del costo in memoria
- [ ] `src/graph/search.py`: A* mono-criterio con euristica geografica, con
      dimostrazione dell'ammissibilita' nel docstring
- [ ] Ricerca multi-criterio: frontiera di Pareto su (orario di arrivo, numero di
      cambi, minuti a piedi)
- [ ] Misura di nodi espansi e tempo per query; confronto A* contro Dijkstra
- [ ] Test su casi costruiti a mano con risultato noto

---

## Fase 3 — Modello dei ritardi

**Prerequisito: almeno due settimane di raccolta continua.**

- [ ] Script di trasformazione dei dump `.pb` in
      `data/processed/observations.parquet`, con deduplica delle osservazioni
      ripetute dello stesso passaggio
- [ ] `src/delays/features.py`: linea, fascia oraria, giorno della settimana,
      posizione lungo la corsa, ritardo alle fermate precedenti della stessa
      corsa; meteo storico da Open-Meteo facoltativo
- [ ] Controllo esplicito e documentato che nessuna feature contenga
      informazione futura rispetto al momento della pianificazione
- [ ] `src/delays/model.py`: predizione della DISTRIBUZIONE del ritardo
  - [ ] baseline empirica per (linea, fascia oraria)
  - [ ] regressione quantile su piu' quantili
  - [ ] un terzo modello, con motivazione della scelta
  - [ ] valutazione con pinball loss e CRPS
- [ ] Protocollo: validazione incrociata annidata (5 fold esterni, 3 interni)
      PIU' split temporale; entrambi riportati con media e deviazione standard
- [ ] `src/delays/calibration.py`: reliability diagram e indice di calibrazione

---

## Fase 4 — Pianificatore robusto e baseline

- [ ] `src/planner/robust.py`: P(arrivo <= T) componendo le distribuzioni lungo
      la catena delle coincidenze
  - [ ] metodo per convoluzione numerica
  - [ ] metodo per campionamento Monte Carlo
  - [ ] misura dell'errore di approssimazione fra i due e del costo
        computazionale
  - [ ] ricerca dell'itinerario che massimizza la probabilita'
- [ ] `src/planner/baselines.py`: piu' veloce sull'orario teorico; meno cambi;
      margine fisso di 5 minuti su ogni coincidenza
- [ ] Argomentazione del perche' l'obiettivo probabilistico non e' riducibile a
      una penalizzazione del tempo di viaggio

---

## Fase 5 — Backtesting e risultati

- [ ] `src/eval/backtest.py`: itinerario generato con SOLO l'informazione
      disponibile prima della partenza, verificato sulle osservazioni reali
- [ ] `src/eval/metrics.py`: coincidenze perse, ritardo reale all'arrivo, arrivi
      entro l'orario promesso, calibrazione delle probabilita' dichiarate
- [ ] Griglia: almeno 100 coppie origine-destinazione x tutti i giorni
      disponibili x tutte le strategie x almeno 2 citta'
- [ ] Risultati grezzi in `results/` come CSV
- [ ] `src/eval/report.py`: tabelle con media e deviazione standard per ogni
      combinazione, piu' i grafici. Nessun output per singolo run

---

## Fase 6 — Documentazione

- [ ] `docs/documentazione.md`
  - [ ] introduzione e problema
  - [ ] base di conoscenza: rappresentazione, regole, complessita' con i numeri
        misurati in Fase 1
  - [ ] ricerca: stato, euristica e sua ammissibilita', risultati
  - [ ] modello probabilistico: scelte, iperparametri e come sono stati scelti,
        risultati con media e deviazione standard
  - [ ] pianificatore robusto
  - [ ] valutazione sperimentale con tutte le tabelle
  - [ ] conclusioni, limiti e **risultati negativi**
  - [ ] riferimenti
