# Istruzioni permanenti

Questo file vale per ogni sessione di lavoro su questo repository. Va letto per
intero prima di scrivere codice.

## Cos'e' questo progetto

Progetto per il corso di Ingegneria della Conoscenza (ICon), Universita' di Bari.
Due studenti, budget complessivo circa 50 ore. Esame individuale e orale: ogni
scelta tecnica deve essere difendibile a voce da entrambi.

**Obiettivo.** Un pianificatore di viaggi sul trasporto pubblico locale che,
invece di minimizzare l'orario teorico di arrivo, massimizza la PROBABILITA' di
arrivare entro un orario dato, tenendo conto della distribuzione reale dei
ritardi appresa da dati raccolti sul campo.

**Domanda di ricerca.** Un itinerario scelto massimizzando P(arrivo <= T) perde
meno coincidenze di un itinerario scelto minimizzando l'orario teorico, a parita'
di tempo di viaggio nominale?

## Vincoli di valutazione

Sono i criteri con cui il progetto viene giudicato. Ogni decisione deve essere
compatibile con tutti e quattro.

1. **La base di conoscenza deve contenere regole vere.** Ricorsione, eccezioni,
   vincoli di integrita'. Non un database interrogato con pattern matching. Se
   una regola ASP potrebbe essere sostituita da una query SQL, non e' una regola.
2. **Ogni risultato sperimentale e' una media su piu' run/giorni/istanze, con
   deviazione standard.** Mai una singola matrice di confusione, mai un singolo
   run. Se un numero compare nella documentazione senza la sua variabilita',
   e' un numero da rifare.
3. **Fuori perimetro:** NLP, riconoscimento di immagini, sistemi di
   raccomandazione.
4. **Niente clustering** a meno che non sia strettamente necessario al problema.

## Stack tecnico: chiuso

Python 3.11+ (verificato su 3.14.6), ambiente virtuale `venv`.

`pandas`, `numpy`, `scipy`, `scikit-learn`, `matplotlib`, `clingo`,
`gtfs-realtime-bindings`, `protobuf`, `pyarrow`, `pytest`, `PyYAML`, `tzdata`.

**Non aggiungere altre dipendenze senza chiedere.** In particolare: niente
`requests` (per HTTP si usa `urllib.request` della libreria standard), niente
framework, niente database, niente Docker, niente notebook come deliverable.

Le versioni in `requirements.txt` sono fissate in modo esatto e verificate come
installabili da wheel: installare sempre con `--only-binary=:all:`.

## Come si lavora

- **Una fase alla volta.** Al termine di ogni fase ci si ferma, si riassume e si
  aspetta il via libera. Non si anticipano le fasi successive.
- **Prima di ogni fase si propone un piano in punti** e si aspetta conferma.
- **Se una scelta ha implicazioni sulla valutazione d'esame, si segnala invece di
  deciderla da soli.**
- **Non si inventano URL, dataset, numeri o risultati.** Se manca un dato, si
  chiede. Un numero riportato nella documentazione deve essere stato misurato da
  un comando che si puo' rieseguire.

## Registro delle decisioni

Ogni decisione tecnica non ovvia (un iperparametro, una soglia, una struttura
dati, un'approssimazione) va annotata in `docs/decisioni.md` con questo formato:

```
### <numero>. <titolo>
**Decisione.** Cosa si e' scelto.
**Alternative considerate.** Cosa si e' scartato.
**Motivo.** Perche', in modo verificabile.
**Come si potrebbe verificare.** L'esperimento o la misura che confermerebbe o
smentirebbe la scelta.
```

E' la parte piu' importante del progetto: e' cio' che si porta all'orale.

## Convenzioni di codice

- **Docstring e commenti in italiano**, e devono spiegare il **perche'**, non il
  **cosa**. `# incrementa il contatore` e' rumore; `# i duplicati gonfierebbero
  la numerosita' campionaria della Fase 3` e' informazione.
- Nomi di funzioni, variabili e parametri in italiano. I nomi che vengono dal
  formato GTFS (`trip_id`, `stop_times`, `service_date`) restano in inglese,
  perche' tradurli renderebbe illeggibile il confronto con la specifica.
- Annotazioni di tipo ovunque; `from __future__ import annotations` in testa.
- **La logica pura sta separata dall'I/O.** Le funzioni che calcolano non devono
  leggere file ne' aprire connessioni: e' cio' che le rende collaudabili. Le
  dipendenze esterne (tempo, rete, casualita') si iniettano come parametri con un
  valore predefinito, mai catturate come default valutato alla definizione.
- Test `pytest` per ogni funzione pura non banale. I test non toccano la rete
  esterna: se serve un server, si avvia in locale nel test.
- Righe entro 100 caratteri.

## Commit

Granulari: un commit per unita' di lavoro compiuta. Messaggi in italiano,
all'imperativo o al sostantivo, in minuscolo, senza punto finale. Esempi:

```
struttura iniziale del repository e gitignore
collector: deduplica dei dump per header.timestamp
test: copertura del ciclo di raccolta con server locale
```

Non si committa in blocco a fine fase.

## Struttura del repository

```
CLAUDE.md              questo file
PLAN.md                piano delle fasi con stato di avanzamento
README.md              come eseguire tutto
requirements.txt
config.yaml            indirizzi dei feed, parametri, citta' configurate
data/raw/rt/           dump grezzi del feed real-time (fuori da git)
data/raw/gtfs/         archivi GTFS statici (fuori da git)
data/processed/        dati derivati (fuori da git)
src/collector/         raccolta dei dati sul campo
src/gtfs/              lettura dell'orario statico e del calendario
src/kb/                base di conoscenza in ASP
src/graph/             grafo tempo-espanso e ricerca
src/delays/            modello probabilistico dei ritardi
src/planner/           pianificatore robusto e baseline
src/eval/              backtesting, metriche, report
tests/
results/               CSV e grafici degli esperimenti (DENTRO git)
docs/decisioni.md      registro delle scelte tecniche
docs/documentazione.md documento finale
```

`results/` e' versionato di proposito: i risultati sperimentali sono il
deliverable valutato, non artefatti rigenerabili a piacere.
