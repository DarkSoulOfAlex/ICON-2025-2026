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
- [x] Test: logica pura piu' giri completi su server HTTP locale
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

- [x] Orario statico di Torino aggiunto e verificato (19,0 MB, archiviato)

**Ancora aperto:**

- [ ] Copia di sicurezza di `data/` su un secondo supporto (~1,3 GB al giorno)
- [ ] Verifica della copertura dopo il primo giorno pieno

---

## Fase 1 — GTFS statico e base di conoscenza

- [x] `src/gtfs/loader.py`: lettura e validazione dell'archivio, con messaggi che
      nominano file e colonna mancante
- [x] `src/gtfs/calendar.py`: servizi e corse attive in una data di servizio,
      con i due regimi di calendario e gli orari oltre le 24:00
- [x] `src/kb/rules.lp`: base di conoscenza in ASP
  - [x] `trasbordo_ammissibile/3` con tempo minimo dipendente dalla fermata
  - [x] trasbordo a piedi entro soglia, con indice spaziale neutro
  - [x] `accessibile/2` con eccezioni, non monotona
  - [x] `raggiungibile/2` come chiusura transitiva ricorsiva
  - [x] quattro vincoli di integrita', tutti dimostrabilmente violabili
  - [x] negazione stratificata, documentata regola per regola
- [x] `src/kb/engine.py`: wrapper clingo, fatti dal GTFS, `transfers.parquet`
- [x] Curva di complessita' su entrambe le citta': `results/complessita_kb.csv`
      e `results/complessita_kb.png`
- [x] Sezioni "Rappresentazione della conoscenza" e "Complessita' della base di
      conoscenza" in `docs/documentazione.md`
- [x] Test su calendario, orari oltre le 24:00 e base di conoscenza

---

## Fase 0-quater — Raccolta su VM e consolidamento notturno

La raccolta gira su una VM Oracle Ubuntu 24.04 aarch64, sempre accesa. La VM
esegue **solo** raccolta e consolidamento; esperimenti, test e documento restano
sulla macchina di analisi.

- [x] `deploy/requirements-collector.txt`: sei dipendenze, versioni identiche a
      quelle del progetto, verificate come wheel cp312/aarch64
- [x] `deploy/collector.service`: parte al boot senza login
- [x] `deploy/install.sh`: idempotente, non avvia prima della copia dei dati
- [x] `deploy/README_DEPLOY.md`
- [x] Dati preesistenti copiati sulla VM, raccolta avviata e verificata
- [x] Compito pianificato di Windows rimosso
- [x] `src/gtfs/indice_statico.py`: le funzioni dell'indice non stanno piu' nel
      collector, cosi' il consolidamento non deve importarlo
- [x] `deploy/sync.sh`: rsync se c'e', altrimenti tar su ssh
- [x] `deploy/stato.sh`: copertura **reale**, non quella dei soli manifest
- [x] `src/consolida/notturno.py` con `consolidamento.timer` alle 04:00
- [x] Voci 37-42 del registro delle decisioni

**Sulla VM, installato e verificato:**

- [x] Consolidamento installato: `git pull` e `./deploy/install.sh`
- [x] Verificato dopo le prime notti con `./deploy/stato.sh`: il timer e' scattato
      regolarmente, **quattro giornate consolidate per 74 MB di parquet**, e il
      **27 agosto ha copertura reale del 100% su entrambe le citta'**

---

## Fase 2 — Grafo tempo-espanso e ricerca

- [x] `src/delays/interfaccia.py`: contratto del modello dei ritardi piu'
      implementazione sintetica, con il presidio a tre livelli contro l'uso
      accidentale nei risultati
- [x] `src/graph/time_expanded.py`: stato sdoppiato in ATerra e ABordo, finestra
      temporale di 120 minuti, archi da `transfers_<citta>.parquet`
- [x] `src/graph/search.py`: A* e Dijkstra come stesso codice, frontiera di Pareto
      su (arrivo, cambi, minuti a piedi)
- [x] Dimostrazione di ammissibilita' e consistenza nel docstring e nel documento
- [x] Confronto su 50 coppie per citta': `results/ricerca_astar.csv`,
      `results/grafo_finestra.csv`, `results/velocita_archi.csv`,
      `results/ricerca_astar.png`
- [x] Variante non ammissibile a p99,9 come termine di paragone, marcata come
      tale nel codice, nel CSV e nella figura
- [x] Sezione "Ricerca di itinerari" in `docs/documentazione.md`
- [x] Test: A* contro ricerca esaustiva, ammissibilita' per campionamento,
      dominanza di Pareto
- [x] Voci 43-48 del registro delle decisioni

**Risultati principali.** L'euristica ammissibile risparmia il 7,7% degli stati a
Roma e il 3,8% a Torino, ed e' piu' lenta di Dijkstra: e' la conseguenza del
massimo di velocita' imposto dall'ammissibilita' (501 km/h a Torino, 297 a Roma),
che a sua volta viene da orari programmati che dichiarano 400 metri in 3 secondi.
La variante non ammissibile risparmia il 35,8% e il 20,6% e non ha mai perso
l'ottimo sulle 82 interrogazioni risolte, il che non basta a rinunciare alla
garanzia.

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

- [x] `src/planner/robust.py`: composizione delle probabilita' lungo la catena,
      con recupero delle coincidenze perse invece del fallimento secco
- [x] Convoluzione numerica e Monte Carlo, con la misura di errore e costo
- [x] `src/planner/baselines.py`: piu' veloce, meno cambi, margine fisso di 5 min
- [x] Pianificatore che massimizza P(arrivo <= T) sulla frontiera di Pareto
- [x] Misura preliminare che giustifica l'insieme candidato (ampiezza 0,44)
- [x] Griglia dei margini 0-30 min su 40 coppie per citta'
- [x] `results/robusto_griglia_T.csv` e `.png`,
      `results/conv_vs_montecarlo.csv` e `.png`
- [x] Sezione "Pianificazione robusta" in `docs/documentazione.md`
- [x] Test: forma chiusa, concordanza dei metodi, monotonia, guardia sulla massa,
      recupero delle coincidenze, strategie di scelta
- [x] Voci 49-55 del registro delle decisioni

**Risultati principali** (modello dei ritardi SINTETICO, nessuno di questi e' un
risultato sperimentale sui ritardi reali). La coincidenza fra scelta robusta e
scelta piu' veloce scende dall'85-88% a margine nullo al 55-62% a trenta minuti:
e' la dimostrazione che l'ordinamento fra itinerari dipende da T. Il guadagno ha
forma a campana e culmina a 8-10 punti percentuali fra 15 e 20 minuti di margine,
che e' il campo di applicabilita' del metodo. Il Monte Carlo domina la
convoluzione su accuratezza e costo, ma la convoluzione resta perche' e'
deterministica. La baseline del margine fisso e' la peggiore delle tre, perche' si
difende dal rischio sbagliato.

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
