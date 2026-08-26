# Registro delle decisioni tecniche

Ogni voce risponde a quattro domande: cosa si e' scelto, cosa si e' scartato,
perche', e con quale misura la scelta si potrebbe confermare o smentire.

Le voci sono numerate in ordine cronologico e non vengono rinumerate: se una
decisione viene rivista, si aggiunge una voce nuova che cita quella superata.

---

## Fase 0 — Scaffolding e raccolta dati

### 1. La raccolta dati precede tutto il resto

**Decisione.** La Fase 0 e' l'unica cosa realizzata prima di qualsiasi altra
parte del progetto, KB e pianificatore compresi.

**Alternative considerate.** Costruire prima la base di conoscenza e il grafo
tempo-espanso, che sono le parti "nobili" per un corso di Ingegneria della
Conoscenza, e occuparsi dei dati in un secondo momento.

**Motivo.** Un feed GTFS Real-Time e' una fotografia dell'istante presente:
nessuna agenzia pubblica lo storico dei ritardi. Il dataset su cui si reggono la
Fase 3 e la Fase 5 non esiste finche' non lo costruiamo giorno per giorno, e ogni
giorno in cui il collector non gira e' un giorno perso in modo definitivo. La KB
e il grafo, al contrario, si possono scrivere in qualunque momento perche' il
GTFS statico e' scaricabile quando si vuole.

**Come si potrebbe verificare.** Contare, a fine progetto, i giorni di raccolta
effettivamente usati nella griglia sperimentale della Fase 5. Se fossero meno di
quelli disponibili sul calendario del progetto, la differenza misurerebbe
esattamente il costo di aver ritardato l'avvio.

---

### 2. Python 3.14.6 invece di ripiegare su una versione piu' conservativa

**Decisione.** Si usa l'interprete gia' presente sulla macchina, Python 3.14.6.

**Alternative considerate.** Installare Python 3.12, che al momento e' la
versione con il supporto piu' ampio nell'ecosistema scientifico.

**Motivo.** Il rischio concreto era l'assenza di wheel precompilate per `cp314`
su Windows, in particolare per `clingo` (che altrimenti richiederebbe CMake e
MSVC) e per `pyarrow`. Il rischio e' stato verificato invece che ipotizzato, con
`pip install --only-binary=:all: --dry-run`: esistono wheel `cp314` per tutte e
dodici le dipendenze. Verificato anche a livello funzionale, non solo di
installazione: `clingo.Control` risolve un programma di prova, il roundtrip
protobuf di un `FeedMessage` conserva i ritardi, e `zoneinfo` risolve
`Europe/Rome`.

**Come si potrebbe verificare.** Rieseguire `pip install --only-binary=:all: -r
requirements.txt` in un venv pulito. Se una qualsiasi wheel sparisse dall'indice,
il comando fallirebbe subito invece di avviare una compilazione.

---

### 3. Versioni delle dipendenze fissate in modo esatto

**Decisione.** `requirements.txt` usa `==` su tutte le dipendenze dirette, e
l'installazione avviene sempre con `--only-binary=:all:`.

**Alternative considerate.** Intervalli di versione (`>=`), che invecchiano
meglio e riducono i conflitti.

**Motivo.** Il deliverable valutato di questo progetto e' una campagna
sperimentale. Un intervallo di versioni renderebbe i numeri riportati nella
documentazione non riproducibili da chi legge: una risoluzione diversa delle
dipendenze puo' cambiare il comportamento di `scikit-learn` o di `pandas` fra una
minor e l'altra. Il flag `--only-binary` trasforma l'assenza di una wheel in un
errore immediato invece che in una compilazione da sorgente di venti minuti
destinata a fallire.

**Come si potrebbe verificare.** Installare il progetto in due venv puliti a
distanza di mesi e confrontare `pip freeze`: devono coincidere sulle dipendenze
dirette.

---

### 4. `tzdata` dichiarata esplicitamente pur essendo una dipendenza indiretta

**Decisione.** `tzdata` compare in `requirements.txt` anche se `pandas` la
installerebbe comunque su Windows.

**Alternative considerate.** Lasciarla implicita; oppure evitare `zoneinfo` e
lavorare con l'ora locale della macchina.

**Motivo.** Windows non include il database IANA dei fusi orari, quindi la
`zoneinfo` della libreria standard non funzionerebbe senza. Il nostro codice ne
dipende **direttamente**: la `service_date` del GTFS e' un concetto in ora locale
e va calcolata correttamente anche nei giorni di cambio dell'ora legale. Una
dipendenza diretta lasciata implicita si rompe silenziosamente il giorno in cui
la dipendenza intermedia smette di richiederla.

**Come si potrebbe verificare.** Disinstallare `tzdata` in un venv di prova: il
collector deve continuare a raccogliere, emettendo un avviso e ripiegando sul
fuso di sistema (comportamento previsto e collaudato), non interrompersi.

---

### 5. `urllib.request` invece di `requests`

**Decisione.** Tutto l'HTTP passa dalla libreria standard.

**Alternative considerate.** `requests`, che offre timeout separati per
connessione e lettura, gestione trasparente delle sessioni e un'API piu' comoda.

**Motivo.** `requests` non fa parte dello stack autorizzato per il progetto, e
introdurlo per una manciata di chiamate GET non lo giustifica. La conseguenza
tecnica va dichiarata: `urllib` espone un solo parametro `timeout`, che copre le
operazioni sul socket senza distinguere fra connessione e lettura. Nel nostro
caso e' accettabile perche' il timeout complessivo (20 s) e' comunque molto
inferiore all'intervallo di polling (60 s), quindi una risposta lenta non puo'
far slittare il tick successivo.

**Come si potrebbe verificare.** Misurare, sul manifest di una giornata reale, la
distribuzione del tempo di risposta del feed. Se la coda superasse i 20 s con
frequenza non trascurabile, il timeout unico diventerebbe un problema e la
decisione andrebbe rivista.

---

### 6. Si raccolgono `trip_updates` e `vehicle_positions`

**Decisione.** Per ogni citta' si interrogano entrambi i feed; solo
`trip_updates` e' obbligatorio.

**Alternative considerate.** Solo `trip_updates`, che e' l'unica fonte
effettivamente necessaria; oppure anche `service_alerts`.

**Motivo.** `trip_updates` e' indispensabile perche' contiene i ritardi.
`vehicle_positions` costa poco spazio e serve da ridondanza: se dopo due
settimane i `trip_updates` di un'agenzia si rivelassero poveri o intermittenti,
dalle posizioni si potrebbero ricostruire i passaggi, mentre a posteriori non si
puo' recuperare nulla. `service_alerts` e' stato escluso perche' spiegherebbe
solo gli outlier e rischia di restare inutilizzato, allargando la Fase 3.

**Come si potrebbe verificare.** A fine raccolta, contare quante osservazioni di
ritardo si ottengono dai soli `trip_updates` e quante se ne otterrebbero
integrando le posizioni. Se il secondo numero non fosse significativamente
maggiore, la ridondanza sarebbe stata spazio sprecato.

---

### 7. Dump salvati non compressi, in `.pb`

**Decisione.** I dump vengono scritti cosi' come arrivano, senza `gzip`.

**Alternative considerate.** `.pb.gz`, che ridurrebbe l'occupazione di circa due
terzi.

**Motivo.** Lo spazio disponibile (565 GB liberi) non e' il vincolo stringente, e
la deduplica per `header.timestamp` riduce gia' il volume alla sola informazione
nuova. File non compressi si leggono piu' velocemente nella Fase 3, che deve
attraversare decine di migliaia di dump, e restano ispezionabili singolarmente
senza passaggi intermedi.

**Come si potrebbe verificare.** Misurare il volume reale dopo il primo giorno di
raccolta e proiettarlo sulla durata prevista della campagna. Se superasse una
decina di GB per citta', la compressione tornerebbe conveniente. **Questo numero
va misurato e annotato qui appena la raccolta parte.**

---

### 8. Raggruppamento dei dump per data locale della citta'

**Decisione.** La cartella giornaliera usa la data nel fuso orario dell'azienda
di trasporto, non la data UTC; il manifest conserva entrambi gli istanti.

**Alternative considerate.** Raggruppare per data UTC, che e' immune ai fusi e ai
cambi d'ora.

**Motivo.** La `service_date` del GTFS e' definita in ora locale. Raggruppando per
data locale, la cartella di un giorno contiene esattamente le osservazioni di
quel giorno di servizio e il join della Fase 3 non deve ricostruire nulla. Con la
data UTC, ogni giornata italiana sarebbe spezzata su due cartelle.

**Come si potrebbe verificare.** Contare, in Fase 3, quante osservazioni cadono
fuori dalla `service_date` a cui la cartella le assegna. Con il raggruppamento
locale devono essere solo quelle delle corse a cavallo della mezzanotte, che il
GTFS rappresenta con orari oltre le 24:00.

---

### 9. Sottocartella per tipo di feed

**Decisione.** Il percorso e'
`data/raw/rt/<citta>/<data>/<tipo_feed>/<HHMMSS>.pb`, con il tipo come cartella e
non come suffisso del nome file.

**Alternative considerate.** `<HHMMSS>_trip_updates.pb` nella cartella del
giorno, piu' aderente alla struttura indicata nella specifica iniziale.

**Motivo.** La Fase 3 legge solo i `trip_updates`. Una cartella dedicata rende la
selezione una questione di percorso invece che di filtro sul nome del file, il
che elimina un'intera classe di errori silenziosi, e tiene ogni cartella attorno
al migliaio di file invece che al doppio.

**Come si potrebbe verificare.** Se in Fase 3 comparisse anche una sola
osservazione proveniente da un `vehicle_positions` letto per sbaglio, la
separazione per cartella non starebbe funzionando.

---

### 10. Deduplica dei dump tramite `header.timestamp`

**Decisione.** Se il `header.timestamp` del feed appena scaricato coincide con
quello dell'ultimo salvato, il dump non viene scritto; il manifest registra
comunque l'interrogazione con esito `duplicato`. Se il feed non valorizza quel
campo, si conserva tutto.

**Alternative considerate.** Salvare sempre; oppure confrontare l'impronta
SHA-256 dell'intero payload.

**Motivo.** Le agenzie rigenerano il feed con una cadenza propria (tipicamente
30-120 s) non sincronizzata con la nostra, quindi interrogando ogni 60 s capita
spesso di riottenere la stessa fotografia. Il punto non e' risparmiare disco: se
conservassimo i duplicati, la Fase 3 conterebbe piu' volte la stessa osservazione
e **gonfierebbe artificialmente la numerosita' campionaria** su cui si calcolano
medie e deviazioni standard, che e' precisamente il vizio metodologico che i
vincoli di valutazione vietano. L'impronta dell'intero payload e' stata scartata
perche' alcuni feed includono campi che cambiano a ogni generazione pur senza
portare informazione nuova. Nel caso di `header.timestamp` assente si preferisce
il duplicato all'osservazione persa, perche' il secondo errore e' irreversibile.

**Come si potrebbe verificare.** Confrontare, su una giornata, il numero di
passaggi distinti `(trip_id, stop_id, service_date)` estratti dai dump salvati con
quello che si otterrebbe salvando tutto: devono coincidere. Se il secondo fosse
maggiore, la deduplica starebbe scartando informazione vera.

**Aggiornamento del 2026-08-25: il risparmio di spazio non si e' verificato.**
Sui primi 13 giri di raccolta reale, cioe' 52 interrogazioni fra Roma e Torino su
entrambi i feed, gli esiti sono stati **52 `salvato` e 0 `duplicato`**: nessuna
delle due agenzie ha mai ripresentato lo stesso `header.timestamp` a un minuto di
distanza. Entrambe rigenerano il feed piu' spesso di quanto lo interroghiamo,
quindi su queste due citta' la deduplica **non elimina nulla** e la proiezione di
1,34 GB al giorno della voce 28 va presa per intera, senza sconti.

Il campione e' pero' piccolo e tutto diurno (16 minuti attorno alle 13:30 di un
martedi'). Nelle ore notturne, con poche corse in servizio, e' plausibile che il
feed resti fermo piu' a lungo e qualche duplicato compaia: la misura va rifatta
su una giornata intera prima di considerarla definitiva.

La decisione **resta corretta**, ma per una ragione sola invece che due. Il
risparmio di spazio era un beneficio atteso e non si e' materializzato; la tutela
metodologica contro il doppio conteggio in Fase 3 resta intera, ed e' quella che
giustifica la scelta: se un giorno una delle due agenzie rallentasse la propria
cadenza di rigenerazione, senza deduplica ci ritroveremmo a contare piu' volte la
stessa osservazione mentre calcoliamo medie e deviazioni standard, e non ce ne
accorgeremmo. Una tutela che costa nulla e non serve quasi mai e' comunque una
tutela.

Va registrato come **risultato negativo misurato**, ed e' materia per la sezione
del documento sulle scelte di progetto: il beneficio che avevamo attribuito alla
deduplica era una previsione non verificata, e la verifica l'ha smentita.

---

### 11. Validazione semantica del payload, oltre al parsing protobuf

**Decisione.** Un payload e' accettato solo se non inizia come un documento di
markup, se `ParseFromString` riesce, **e** se `header.gtfs_realtime_version` e'
valorizzato.

**Alternative considerate.** Fidarsi del solo `ParseFromString`.

**Motivo.** Il terzo controllo sembra ridondante, dato che
`gtfs_realtime_version` e' un campo *required* di proto2, ma non lo e': **e' stato
verificato sperimentalmente che protobuf applica il vincolo dei campi obbligatori
solo in scrittura**. In lettura accetta senza protestare un messaggio che ne e'
privo, restituendo una stringa vuota. Il test
`test_un_protobuf_senza_versione_non_e_un_feed_gtfs_rt` costruisce quei byte a
mano proprio perche' l'API Python si rifiuterebbe di serializzarli, mentre un
server malconfigurato puo' restituirli. Senza questi controlli il rischio
concreto e' accumulare settimane di file `.pb` che in Fase 3 si rivelano pagine
HTML di errore, quando non c'e' piu' modo di rimediare.

**Come si potrebbe verificare.** Contare le righe con esito `payload_non_valido`
nei manifest. Se fossero piu' di una frazione trascurabile, il feed andrebbe
ispezionato guardando i file conservati in `_scarti/`.

---

### 12. I payload rifiutati vengono conservati

**Decisione.** Un payload che non supera la validazione finisce in
`_scarti/<tipo_feed>/<HHMMSS>.bin`, non viene buttato.

**Alternative considerate.** Scartarlo registrando solo l'evento nel log.

**Motivo.** Se un giorno il feed cambia formato o l'agenzia introduce
un'autenticazione, vogliamo poter capire **cosa** e' arrivato, non solo sapere che
era illeggibile. Il costo e' trascurabile perche' questi casi devono essere rari
per costruzione.

**Come si potrebbe verificare.** Alla prima anomalia, aprire un file di
`_scarti/` deve bastare a diagnosticare la causa senza dover riprodurre il
problema.

---

### 13. Manifest giornaliero con una riga per ogni interrogazione

**Decisione.** Ogni interrogazione, riuscita o fallita, scrive una riga in
`_manifest.csv` con istante UTC e locale, tipo di feed, esito, stato HTTP,
tentativi, byte, `header.timestamp`, numero di entita' e file prodotto.

**Alternative considerate.** Registrare solo i salvataggi; oppure affidarsi al
solo file di log.

**Motivo.** Senza le righe di fallimento manca il **denominatore**: la copertura
della raccolta (quota di interrogazioni andate a buon fine) non sarebbe
calcolabile a posteriori. La copertura e' un indicatore di qualita' del dataset
che va riportato nella documentazione, perche' qualifica tutti i risultati
sperimentali che ne dipendono. Un CSV e' preferibile al log perche' e'
direttamente leggibile in `pandas` senza doverlo interpretare.

**Come si potrebbe verificare.** Per ogni giornata, il numero di righe del
manifest deve essere pari a (giri effettuati x feed configurati). Uno scarto
segnalerebbe interrogazioni non registrate, quindi una copertura sovrastimata.

---

### 14. Snapshot giornaliero dell'orario statico, archiviato solo se cambia

**Decisione.** Il collector scarica il GTFS statico una volta al giorno per
citta', ne calcola lo SHA-256 e conserva l'archivio solo quando l'impronta e'
diversa dall'ultima. Lo stato del controllo sta in un file JSON su disco.

**Alternative considerate.** Scaricare il GTFS statico una volta sola all'inizio
del progetto; oppure a fine campagna; oppure ogni giorno conservando tutto.

**Motivo.** E' la decisione con l'impatto piu' alto di tutta la Fase 0. Gli
identificativi di corsa del feed real-time hanno senso **solo** rispetto alla
versione dell'orario statico in vigore quel giorno, e le agenzie ripubblicano
l'orario ogni poche settimane cambiando i `trip_id`. Con un solo scaricamento a
fine campagna, una parte dei dump gia' raccolti diventerebbe impossibile da
interpretare e i giorni corrispondenti andrebbero buttati. Conservare solo le
revisioni distinte tiene il costo a pochi MB per revisione invece che per giorno.
Lo stato su file, e non in memoria, evita di riscaricare decine di MB a ogni
riavvio del processo.

**Come si potrebbe verificare.** In Fase 3, misurare la quota di
`(trip_id, service_date)` del real-time che trova corrispondenza nell'orario
statico archiviato per quel giorno. Deve restare vicina al 100% anche a cavallo
di una revisione dell'orario; con un unico snapshot crollerebbe.

---

### 15. Cadenza a tick fissi invece di attesa dopo il lavoro

**Decisione.** L'istante del giro successivo si calcola come
`prossimo_tick += intervallo`, non come "dormi 60 secondi dopo aver finito". Se un
giro sfora, i tick arretrati vengono saltati per riallinearsi.

**Alternative considerate.** `time.sleep(60)` al termine di ogni giro.

**Motivo.** La seconda forma somma la durata di ogni scaricamento all'attesa,
facendo scivolare l'istante di campionamento di parecchi minuti nell'arco di una
giornata. Il campionamento smetterebbe di essere regolare proprio mentre lo
dichiariamo tale, e la cadenza effettiva diventerebbe dipendente dalla latenza
del server dell'agenzia.

**Come si potrebbe verificare.** Calcolare, sul manifest di una giornata, media e
deviazione standard dell'intervallo fra interrogazioni consecutive: la media deve
restare a 60 s senza deriva fra la prima e l'ultima ora.

---

### 16. Nessun ritentativo sugli errori HTTP 4xx

**Decisione.** I 4xx interrompono subito la sequenza di tentativi; i 5xx e gli
errori di rete vengono ritentati con backoff esponenziale e jitter.

**Alternative considerate.** Ritentare in modo uniforme su qualunque errore.

**Motivo.** Un 401 o un 404 non si risolvono riprovando fra due secondi:
insistere significherebbe solo martellare il server dell'agenzia con richieste
che sappiamo destinate a fallire, e ai loro occhi saremmo indistinguibili da un
client difettoso. Il jitter sul backoff evita che, dopo un guasto comune (per
esempio la rete di casa che cade), tutte le citta' ritentino nello stesso
identico istante.

**Come si potrebbe verificare.** Contare i tentativi per esito nel manifest: le
righe con `stato_http` 4xx devono avere `tentativi` pari a 1.

---

### 17. I segnaposto in `config.yaml` impediscono l'avvio

**Decisione.** Il collector si rifiuta di partire se un indirizzo obbligatorio
inizia ancora con `INSERIRE_QUI_`, e riporta **tutti** i problemi trovati insieme,
non solo il primo.

**Alternative considerate.** Emettere un avviso e proseguire saltando le citta'
incomplete.

**Motivo.** L'errore piu' costoso possibile in questo progetto e' credere di
star raccogliendo e scoprire dopo tre giorni che non e' vero: quei giorni non
tornano. Un avvio rumorosamente fallito e' preferibile a una raccolta
silenziosamente vuota. L'accumulo dei problemi serve a chi compila il file la
prima volta, che altrimenti li scoprirebbe uno per volta.

**Come si potrebbe verificare.** `--verifica-config` su un file con segnaposto
deve uscire con codice 2 e nominare ogni campo mancante.

---

### 18. Interrogazione sequenziale delle citta'

**Decisione.** Le citta' vengono interrogate una dopo l'altra nello stesso
thread.

**Alternative considerate.** Un pool di thread per interrogarle in parallelo.

**Motivo.** Con due o tre citta' e un timeout di 20 s, il caso peggiore resta
ampiamente dentro l'intervallo di 60 s, e il codice sequenziale non ha stato
condiviso da proteggere: e' piu' semplice da leggere, da collaudare e da
difendere all'orale. Il parallelismo si giustificherebbe solo con molte piu'
citta'.

**Come si potrebbe verificare.** Misurare la durata dei giri sul manifest. Se il
log iniziasse a riportare tick saltati, il sequenziale non basterebbe piu'.

---

### 19. Ripiego sul fuso di sistema quando il fuso IANA non e' disponibile

**Decisione.** Se `ZoneInfo` non riesce a risolvere il fuso configurato, il
collector emette un avviso e continua usando il fuso locale della macchina,
invece di interrompersi.

**Alternative considerate.** Considerarlo un errore fatale, per non produrre dati
con una data di servizio potenzialmente sbagliata.

**Motivo.** I due errori non sono simmetrici. Perdere ore di raccolta e' un danno
permanente; una data di servizio calcolata con il fuso sbagliato e' un errore
sistematico, visibile nel log e correggibile a posteriori perche' il manifest
conserva comunque l'istante UTC di ogni interrogazione.

**Come si potrebbe verificare.** Disinstallare `tzdata` in un venv di prova: la
raccolta deve proseguire con un avviso, e gli istanti UTC nel manifest devono
restare corretti.

---

### 20. Compito Windows autoriparante, in UTF-16 e con `UserId` esplicito

**Decisione.** L'esecuzione in background su Windows usa un compito
dell'Utilita' di pianificazione con trigger all'accesso, ripetizione ogni 5
minuti senza scadenza e `MultipleInstancesPolicy=IgnoreNew`.

**Alternative considerate.** Un semplice trigger all'avvio senza ripetizione;
oppure lasciare una finestra di terminale aperta.

**Motivo.** La combinazione ripetizione + `IgnoreNew` e' un meccanismo
autoriparante: finche' la raccolta e' viva il nuovo avvio viene ignorato, e
appena il processo muore per qualsiasi motivo il tentativo successivo lo fa
ripartire entro cinque minuti. Servono inoltre `ExecutionTimeLimit=PT0S` (il
valore predefinito di Windows terminerebbe il processo dopo 3 giorni, nel bel
mezzo della campagna) e le due opzioni sulle batterie disattivate (su un
portatile la raccolta si fermerebbe staccando l'alimentatore).

Due dettagli sono stati scoperti provando davvero a importare il compito, non
dedotti: **`schtasks` rifiuta un XML in UTF-8** con l'errore "impossibile passare
a un'altra codifica", quindi il file deve restare in UTF-16 (ed e' marcato
`-text` in `.gitattributes` perche' git non lo normalizzi); e **senza l'elemento
`<UserId>`** in `<Principal>` e in `<LogonTrigger>` la creazione fallisce con
"Accesso negato". Il compito e' stato creato ed eliminato con successo su questa
macchina come verifica.

**Come si potrebbe verificare.** Terminare a mano il processo di raccolta e
controllare che entro cinque minuti ne compaia uno nuovo, con la continuita' del
manifest a confermarlo.

---

### 21. Dipendenze esterne iniettate come parametri, mai catturate come default

**Decisione.** Rete, attesa e casualita' sono parametri delle funzioni che le
usano (`apri`, `dormi`, `casuale`, `esiste`), risolti **dentro** il corpo quando
valgono `None`.

**Alternative considerate.** Usarle direttamente, e nei test sostituire l'intero
modulo con `monkeypatch`.

**Motivo.** E' cio' che rende collaudabile la logica senza toccare la rete e
senza attese reali: i test verificano che un 404 non venga ritentato e che le
attese fra tentativi crescano, in millisecondi. La risoluzione dentro il corpo
invece che come valore predefinito del parametro non e' un dettaglio stilistico:
un default valutato alla definizione catturerebbe per sempre la funzione
originale, rendendo impossibile sostituirla dall'esterno. Il collector aveva
inizialmente `apri=urllib.request.urlopen` come default ed e' stato corretto
proprio per questo.

**Come si potrebbe verificare.** I 46 test della Fase 0 girano in circa 5 secondi
e senza rete esterna. Se un test iniziasse a fallire per indisponibilita' di un
servizio, l'iniezione non starebbe piu' funzionando.

---

## Fase 0-bis — Correzioni dopo la configurazione dei feed reali

### 22. I feed di Torino sono in HTTPS, non in HTTP

**Decisione.** Gli indirizzi GTT in `config.yaml` usano `https://`.

**Alternative considerate.** Usare gli indirizzi `http://` come inizialmente
indicati, adattando il collector a tollerare il traffico in chiaro.

**Motivo.** Gli indirizzi in `http://` **non sono raggiungibili**. Verificato il
2026-08-25: il nome `percorsieorari.gtt.to.it` risolve correttamente
(89.184.107.11), ma la connessione TCP sulla porta 80 scade dopo ~15 s, mentre
sulla porta 443 si stabilisce in 0,1 s. Non e' un blocco locale della porta 80:
nello stesso momento `example.com:80` risponde istantaneamente. Con `http://`
entrambi i feed fallivano con `timed out`; con `https://` restituiscono 382
entita' e 2.190 `stop_time_update`, di cui 1.420 con il campo `delay` e 770 con
l'orario assoluto.

**Come si potrebbe verificare.** `python scripts/verifica_feed.py --citta torino`
deve chiudere con esito OK su entrambi i feed. Un ritorno a `http://`
riprodurrebbe il timeout.

---

### 23. L'orario statico si confronta tramite il file `.md5`, non riscaricandolo

**Decisione.** Il controllo giornaliero scarica prima il file `.md5` pubblicato
accanto all'archivio e, se l'impronta coincide con quella gia' archiviata, non
scarica nulla e registra solo un marcatore. Quando il `.md5` manca (Torino) o non
e' raggiungibile, si ripiega sullo scaricamento dell'archivio e sul confronto
della sua impronta. Sostituisce il meccanismo SHA-256 della voce 14.

**Alternative considerate.** Scaricare ogni giorno l'intero archivio e
confrontarne l'impronta, come faceva la versione precedente; oppure fidarsi
dell'intestazione HTTP `Last-Modified`.

**Motivo.** L'archivio di Roma pesa **48,5 MB** e cambia quasi ogni giorno.
Scaricarlo per scoprire che non e' cambiato costerebbe 48 MB al giorno di banda
per nulla; il `.md5` ne costa 59. `Last-Modified` e' stato scartato perche' molti
server lo aggiornano a ogni rigenerazione anche quando il contenuto e' identico,
quindi non distinguerebbe una revisione vera da una ripubblicazione. La scelta di
MD5 non e' crittografica ma di interoperabilita': e' l'impronta che l'agenzia
pubblica, e usarne un'altra renderebbe impossibile il confronto senza scaricare.

**Come si potrebbe verificare.** Il test
`test_se_il_md5_e_invariato_l_archivio_non_viene_scaricato` controlla che nei
giorni senza modifiche l'indirizzo dell'archivio non venga mai interrogato. Sul
campo: in `logs/collector.log`, le righe "orario statico invariato" non devono
essere accompagnate da 48 MB di traffico.

---

### 24. `index.json` mappa ogni data alla versione dell'orario valida quel giorno

**Decisione.** Ogni citta' ha `data/raw/gtfs/<citta>/index.json` con due sezioni:
`giorni`, che associa ogni data di servizio al file dell'orario in vigore quel
giorno, e `versioni`, che elenca le revisioni distinte con la loro impronta. Nei
giorni senza modifiche viene scritto solo un marcatore che punta all'archivio
precedente, senza duplicarlo.

**Alternative considerate.** Dedurre la versione valida dal nome dei file
archiviati, ordinandoli per data.

**Motivo.** La deduzione dai nomi funziona finche' non ci sono buchi. Ma il
collector puo' restare fermo per giorni, e in quel caso non esiste alcun file per
le date scoperte: senza una mappa esplicita la Fase 3 dovrebbe reimplementare la
regola "vale l'ultima revisione precedente", che e' esattamente il genere di
logica che non si vuole duplicare in due punti. La funzione `versione_valida`
implementa quella regola una volta sola, con i suoi test.

**Come si potrebbe verificare.** In Fase 3, misurare la quota di
`(trip_id, service_date)` del real-time che trova corrispondenza nell'orario
indicato da `index.json` per quel giorno. Deve restare vicina al 100% anche a
cavallo di una revisione.

---

### 25. Registro delle interruzioni in `gaps.jsonl`

**Decisione.** Ogni citta' ha `data/raw/rt/<citta>/gaps.jsonl`, una riga JSON per
ogni finestra senza raccolta, con inizio, fine, durata e causa. Le cause sono
`processo_non_attivo` (rilevata al riavvio confrontando l'istante corrente con il
battito lasciato dal processo precedente) e `errori_di_rete_prolungati` (nessun
feed raggiungibile per oltre `soglia_interruzione_secondi`, predefinito 300 s).

**Alternative considerate.** Ricostruire le interruzioni a posteriori dai buchi
nel manifest giornaliero.

**Motivo.** Dal manifest si vede l'assenza di righe, ma non se ne conosce la
causa, e soprattutto non si distingue "il collector era spento" da "il collector
girava e il feed non rispondeva": sono due situazioni diverse per il backtesting.
Senza questa distinzione, una coincidenza che risulta persa potrebbe essere
semplicemente una coincidenza mai osservata, e la valutazione sperimentale ne
uscirebbe falsata in un modo non rilevabile a posteriori.

La finestra viene scritta solo quando si **richiude**, perche' prima non se ne
conosce la fine; se il processo muore mentre una finestra e' aperta, il battito
su disco resta fermo all'ultimo successo e sara' l'avvio successivo a
registrarla. E' il motivo per cui il battito viene aggiornato solo sui giri
riusciti.

La soglia di 300 s (cinque tick) esiste per non trasformare ogni errore isolato
in una riga: un tick perso e recuperato subito e' rumore, non un buco nei dati.

**Come si potrebbe verificare.** Terminare il collector, attendere dieci minuti e
riavviarlo: deve comparire una riga con causa `processo_non_attivo` e durata pari
all'attesa. La somma delle durate in `gaps.jsonl`, rapportata al periodo di
raccolta, e' la copertura da dichiarare nella documentazione.

---

### 26. Gli indirizzi in chiaro sono ammessi, le credenziali in chiaro no

**Decisione.** Un feed servito in `http://` viene accettato, ma segnalato
all'avvio e in `--verifica-config`. Se pero' la stessa citta' dichiara delle
`intestazioni_http` non vuote, la configurazione viene **rifiutata**.

**Alternative considerate.** Rifiutare qualunque indirizzo non cifrato; oppure
accettarlo senza dire nulla.

**Motivo.** Rifiutare del tutto significherebbe rinunciare in partenza a
un'agenzia che pubblichi solo in chiaro, e i dati di un feed di trasporto
pubblico sono pubblici per definizione: il rischio e' la manomissione lungo il
percorso, non la riservatezza. Le credenziali sono un altro discorso: una chiave
d'accesso spedita in chiaro per settimane e' un regalo alla rete, e un rifiuto
all'avvio costa molto meno che accorgersene dopo. Nella configurazione attuale
nessun indirizzo e' in chiaro (vedere voce 22), ma il controllo resta perche' la
prossima agenzia potrebbe esserlo.

**Come si potrebbe verificare.** Il test
`test_credenziali_su_http_sono_rifiutate` copre il caso; `--verifica-config`
elenca gli indirizzi non cifrati.

---

### 27. Uno script di verifica separato dal collector

**Decisione.** `scripts/verifica_feed.py` scarica una volta ogni feed
configurato, lo decodifica **contando le entita' per conto proprio** invece di
riusare il riepilogo del collector, e stampa un esempio decodificato.

**Alternative considerate.** Usare solo `--diagnostica` del collector, che fa
qualcosa di simile.

**Motivo.** Il doppio conteggio e' voluto: se il numero prodotto dallo script e
quello prodotto dal collector divergessero, sarebbe il segnale che il parser del
collector sta contando qualcosa di diverso da quello che crediamo. Un errore di
quel tipo, scoperto in Fase 3, invaliderebbe settimane di dati. L'esempio
decodificato serve a capire come la singola agenzia popola i campi, cosa che i
conteggi non dicono: e' cosi' che si e' visto che Torino fornisce `delay` su
1.420 passaggi ma l'orario assoluto solo su 770, e che nei `trip_update` di
Torino manca il `route_id`, presente invece nei `vehicle_positions`, che quindi
in Fase 3 andra' recuperato dall'orario statico.

Il giudizio e' differenziato per tipo di feed: un `vehicle_positions` non
contiene TripUpdate per definizione, e giudicarlo con il metro dei `trip_updates`
lo dichiarerebbe inutilizzabile proprio quando funziona come deve. La prima
versione dello script aveva questo difetto ed e' stata corretta.

**Come si potrebbe verificare.** `python scripts/verifica_feed.py` deve chiudere
con codice 0 e "Tutti i feed configurati sono utilizzabili".

---

### 28. Volume misurato della raccolta

**Decisione.** Si conferma il salvataggio non compresso deciso alla voce 7, ma il
numero che li' mancava ora e' misurato.

**Motivo.** Un giro completo (2 citta' x 2 feed) pesa **910 KB**: Roma 735 KB di
`trip_updates` e 100 KB di `vehicle_positions`, Torino 66 KB e 28 KB. A 1440 giri
al giorno la proiezione **grezza** e' di **1,34 GB al giorno**, cioe' circa
**40 GB su 30 giorni**, prima della deduplica. Su 565 GB liberi resta ampiamente
sostenibile, ma non e' trascurabile: e' l'ordine di grandezza che rende
obbligatoria una copia di sicurezza fuori dal disco di lavoro.

L'archivio statico di Roma pesa 48,5 MB per revisione; con un cambio quasi
quotidiano, sono circa 1,5 GB al mese in piu'.

**Come si potrebbe verificare.** Dopo il primo giorno pieno, confrontare
l'occupazione reale con la proiezione: la differenza misura il risparmio della
deduplica per `header.timestamp`. Se l'occupazione reale superasse i 2 GB al
giorno, la compressione scartata alla voce 7 andrebbe riconsiderata.

---

### 29. Nessun dato raccolto da scartare

**Decisione.** La cartella `data/raw/_scartato/` non e' stata creata, perche' non
c'era nulla da spostarci.

**Motivo.** Al momento della richiesta di correzione (2026-08-25) lo stato
verificato era: nessun processo Python attivo, nessun compito pianificato
registrato, `logs/collector.log` di 0 byte, `data/raw/` contenente i soli file
`.gitkeep`, e `config.yaml` ancora pieno di segnaposto `INSERIRE_QUI_` che il
validatore rifiuta all'avvio. La raccolta non era quindi mai partita. Va aggiunto
che il collector non ha mai gestito i feed *service alerts*: i tipi supportati
sono sempre stati solo `trip_updates` e `vehicle_positions`, quindi non avrebbe
potuto raccogliere avvisi testuali nemmeno con gli indirizzi sbagliati.

**Come si potrebbe verificare.** `git log` mostra che `config.yaml` e' passato
dai segnaposto agli indirizzi reali in un unico commit, senza raccolte
intermedie; il primo `_manifest.csv` presente su disco e' del 2026-08-25.

---

## Fase 1 — GTFS statico e base di conoscenza

### 30. Indice spaziale a griglia per la regola del cammino

**Decisione.** La regola del trasbordo a piedi confronta soltanto le fermate che
si trovano nella stessa cella di una griglia regolare o in una delle otto
adiacenti. Il lato della cella e' posto **uguale** alla soglia di cammino, non e'
un parametro indipendente.

**Alternative considerate.** Confrontare tutte le coppie di fermate; oppure
precalcolare le distanze in Python e passarle come fatti.

**Motivo.** Il confronto esaustivo istanzia un numero quadratico di atomi: sulle
8.301 fermate di Roma sono circa 69 milioni di coppie, e il grounding non termina
in tempo utile. Precalcolare le distanze in Python era l'altra via, ma avrebbe
spostato fuori dalla base di conoscenza proprio la regola che decide quali coppie
siano trasbordi, riducendo la KB a un'interrogazione su una tabella gia'
calcolata: esattamente cio' che il progetto deve evitare.

Il vincolo lato = soglia e' cio' che rende l'indice **semanticamente neutro**: due
fermate a distanza inferiore alla soglia non possono cadere in celle non
adiacenti, quindi nessun trasbordo puo' sfuggire al confronto. Un lato piu'
piccolo romperebbe la garanzia.

Va dichiarato che non si tratta di clustering nel senso escluso dai vincoli di
valutazione: non c'e' nulla di appreso, nessun centroide, nessuna funzione
obiettivo, nessuna dipendenza dai dati oltre le coordinate. E' un'indicizzazione
deterministica, l'equivalente spaziale di un indice su una colonna.

**Come si potrebbe verificare.** E' stato verificato in due modi. Il test
`test_l_indice_spaziale_non_altera_i_trasbordi_derivati` confronta gli insiemi
derivati con e senza indice sul GTFS giocattolo; la misura di complessita' ripete
il confronto sui dati reali a 50, 150 e 400 fermate per entrambe le citta'. In
tutti i casi gli insiemi sono risultati identici. Il risparmio misurato cresce da
1,4 a 10,1 volte nell'intervallo esaminato.

---

### 31. Identificativi interi e coordinate in metri

**Decisione.** Gli identificativi GTFS delle fermate diventano interi progressivi
prima di entrare nel programma logico, e le coordinate geografiche diventano metri
interi su una proiezione equirettangolare locale centrata sul baricentro delle
fermate della citta'.

**Alternative considerate.** Usare gli identificativi testuali come costanti ASP e
le coordinate in micro-gradi, calcolando il fattore di conversione dentro la
regola.

**Motivo.** Sono entrambi cambi di rappresentazione, non di conoscenza: la
corrispondenza fra identificativi e' biunivoca e viene conservata in memoria, e la
proiezione e' un cambio di unita' di misura, l'analogo del conservare gli orari in
secondi anziche' come `HH:MM:SS`. Il guadagno sugli identificativi e' di velocita'
nel grounding. Sulle coordinate il guadagno e' che la regola di distanza puo'
essere scritta in aritmetica intera semplice, senza dover conoscere la latitudine:
in gradi il rapporto fra un grado di longitudine e uno di latitudine dipende dal
coseno della latitudine, e portarlo dentro la regola avrebbe richiesto una
costante precalcolata comunque, con in piu' l'illeggibilita'.

L'errore della proiezione equirettangolare, sulla scala di una citta' e a
distanze dell'ordine dei 250 metri, e' inferiore al metro: irrilevante rispetto
alla discretizzazione in bande decisa alla voce 32.

**Come si potrebbe verificare.** Confrontare, su un campione di coppie, la
distanza calcolata sul piano proiettato con la distanza geodetica: lo scarto deve
restare sotto il metro alle distanze rilevanti.

---

### 32. Tempo di cammino discretizzato in bande

**Decisione.** Il tempo di cammino non e' proporzionale alla distanza ma assume
quattro valori, secondo la banda di distanza in cui la coppia ricade. La regola
seleziona il minimo fra i tempi delle bande che contengono la distanza, usando un
aggregato `#min`.

**Alternative considerate.** Calcolare la radice quadrata della distanza al
quadrato e dividere per una velocita'.

**Motivo.** In aritmetica intera la radice quadrata si esprime generando un
candidato per ogni valore possibile e vincolandolo, il che moltiplicherebbe il
grounding per il numero di metri della soglia: 251 istanze per ogni coppia
candidata, cioe' due ordini di grandezza di costo in piu' per una precisione che
non serve. Un tempo di trasbordo ha senso al mezzo minuto, non al metro.

E' una scelta di modello dichiarata, non un'approssimazione subita, e resta
interna alla base di conoscenza: le bande sono fatti ASP, e cambiarle significa
cambiare quattro righe di `rules.lp`.

**Come si potrebbe verificare.** Raffinare le bande a passi di 25 metri e
misurare quanto cambino i tempi minimi derivati e il costo di grounding. Se i
tempi cambiassero in modo apprezzabile, la discretizzazione sarebbe troppo
grossolana.

---

### 33. Campionamento per prossimita' dal baricentro geometrico

**Decisione.** Le sottoreti della curva di complessita' sono le N fermate piu'
vicine a un centro fisso, e il centro e' la fermata piu' vicina al baricentro
geometrico di tutte le fermate della citta', calcolato dai dati.

**Alternative considerate.** Campionamento casuale uniforme; oppure un centro
scelto a mano, per esempio la stazione principale.

**Motivo.** Cinquanta fermate estratte a sorte fra le 8.301 di Roma finirebbero
sparse su tutta la citta', a chilometri l'una dall'altra, e non genererebbero
quasi nessun trasbordo a piedi: la curva misurerebbe il costo di un problema che
non somiglia a quello vero. Il campionamento per prossimita' conserva la densita'
reale della rete. Ha inoltre la proprieta' di essere monotono, cioe' un campione
piu' grande contiene quello piu' piccolo, senza la quale i punti della curva non
sarebbero confrontabili fra loro.

Il centro derivato dai dati anziche' scelto a mano rende la misura riproducibile e
dichiarabile: per Roma e' la fermata 70841, S. SABA/AVENTINO, per Torino la 962,
Fermata 1873 - PUGLIA C.3.

Il limite va dichiarato: i risultati valgono per porzioni connesse e dense di
rete e non sono estrapolabili a un campione sparso di pari cardinalita'. La
misura sull'intera rete lo conferma, perche' produce meno atomi di quanti la
curva ne avrebbe fatti prevedere.

**Come si potrebbe verificare.** Ripetere la curva con campionamento casuale: ci
si attende un numero di trasbordi per fermata molto piu' basso e una crescita
degli atomi quasi lineare, perche' la chiusura transitiva non troverebbe
componenti connesse di dimensione apprezzabile.

---

### 34. Vincoli di integrita' scelti perche' possano essere violati

**Decisione.** Dei vincoli inizialmente formulati ne sono stati mantenuti quattro
e scartati due. Gli scartati vietavano il trasbordo di una fermata con se stessa e
imponevano la simmetria del cammino.

**Alternative considerate.** Tenerli tutti, dato che non costano nulla.

**Motivo.** La costruzione della regola `candidata` rende quei due vincoli
impossibili da violare per definizione: nessun dato, per quanto malformato, puo'
farli scattare. Un vincolo che non puo' mai essere violato non e' logica, e'
commento travestito da logica, e in sede d'esame sarebbe un punto debole invece
che un punto di forza. I quattro mantenuti corrispondono ciascuno a un difetto
documentato dei GTFS pubblicati: grado implausibile per coordinate mancanti, tempo
dichiarato piu' breve del cammino, banchina accessibile in stazione non
accessibile, tempo di trasbordo nullo.

**Come si potrebbe verificare.** Ciascuno dei quattro ha un test che costruisce il
dato che lo viola e verifica che il programma diventi insoddisfacibile, e che
torni soddisfacibile disattivando i soli vincoli. I due scartati non sarebbero
collaudabili in questo modo, ed e' precisamente la ragione per cui sono stati
tolti.

---

### 35. La materializzazione per la Fase 2 escludera' la chiusura transitiva

**Decisione.** `transfers.parquet` contiene la relazione `trasbordo_ammissibile`
con i suoi attributi, non la chiusura `raggiungibile`. La chiusura resta
calcolabile su richiesta, tramite un interruttore del programma logico.

**Alternative considerate.** Materializzare anche la chiusura, dato che il grafo
tempo-espanso potrebbe volerla.

**Motivo.** La misura di complessita' mostra che la chiusura transitiva genera fra
il 70% e il 93% degli atomi alle dimensioni maggiori, mentre la relazione
effettivamente consumata dal grafo tempo-espanso e' quella dei trasbordi diretti,
che cresce linearmente e si attesta su circa cinque trasbordi per fermata a Roma e
tre a Torino. Materializzare la chiusura costerebbe un ordine di grandezza in piu'
per rispondere a domande che il pianificatore pone di rado.

Il fatto che la scelta si possa compiere a valle, disattivando un interruttore
invece di riformulare le regole, e' una conseguenza diretta della natura
dichiarativa della rappresentazione ed e' argomento da portare all'orale.

**Come si potrebbe verificare.** In Fase 2, contare quante volte il grafo
tempo-espanso interroghi effettivamente la raggiungibilita' globale. Se il numero
fosse alto, converrebbe materializzarla.

---

### 36. Risultato negativo: Roma non dichiara accessibilita' ne' stazioni

**Decisione.** Le regole sull'accessibilita' e il livello di stazione della
gerarchia dei tempi restano nella base di conoscenza, pur non ricevendo fatti
utili da Roma.

**Motivo.** Verificato sui dati del 2026-08-26: tutte le 8.301 fermate di Roma
dichiarano `wheelchair_boarding` uguale a zero, cioe' "informazione non
disponibile", e lo stesso vale per tutte le 179.177 corse; nessuna fermata di
Roma dichiara una `parent_station`. La conseguenza e' che sull'intera rete di
Roma la base di conoscenza deriva **zero** trasbordi accessibili. Torino si
comporta diversamente: 2.722 fermate accessibili, 1.075 esplicitamente non
accessibili, e 7.382 trasbordi accessibili derivati su 21.130; ma anche li'
soltanto due fermate su 7.073 appartengono a una stazione.

Sommato al fatto che nessuna delle due citta' pubblica `transfers.txt`, questo
significa che l'eredita' difettibile a tre livelli, sul campo, opera quasi
ovunque sul solo terzo livello. Le regole restano perche' la base di conoscenza e'
scritta per il formato GTFS e non per due archivi particolari, e su un'azienda
che pubblichi quei campi entrerebbero in funzione senza modifiche; ma sarebbe
disonesto presentarle come funzionanti su questi dati, e vengono percio' dichiarate
come tali nel documento.

**Conseguenza operativa.** Ogni risultato sull'accessibilita' nelle fasi
successive andra' riferito alla sola Torino, mai alla media delle due citta'.

**Come si potrebbe verificare.** Aggiungere al progetto una terza citta' che
pubblichi `transfers.txt` e una gerarchia di stazioni, e osservare che i primi due
livelli della gerarchia entrino in funzione senza modificare `rules.lp`.

---

## Fase 0-quater — Spostamento della raccolta su VM

### 37. La raccolta si sposta su una VM sempre accesa

**Decisione.** Il collector gira su una VM Oracle Ubuntu 24.04 aarch64 e non piu'
sul PC di lavoro. La VM esegue **soltanto** la raccolta e il consolidamento
notturno; esperimenti, test e scrittura del documento restano sul PC.

**Alternative considerate.** Tenere la raccolta sul PC configurando il risparmio
energetico perche' non vada mai in sospensione.

**Motivo.** La copertura reale misurata sul PC e' stata del **7,2%**: in ventidue
ore di calendario, novantacinque giri su millecentoventidue attesi, con 20,4 ore
registrate in `gaps.jsonl` come interruzioni. La causa non era il software ma la
macchina, che si spegne e si sospende. Configurare il risparmio energetico
avrebbe risolto il caso della sospensione ma non quello dello spegnimento
volontario, e avrebbe legato la campagna sperimentale all'abitudine di non
spegnere il computer per due settimane.

La divisione dei ruoli e' altrettanto deliberata. Duplicare l'ambiente completo
sulla VM avrebbe significato installare `clingo`, `scikit-learn`, `matplotlib`,
`scipy` e `pytest` su una macchina che non li usa, e soprattutto avrebbe creato
un secondo posto in cui gli esperimenti possono essere eseguiti, con il rischio
di risultati prodotti su due macchine diverse e non confrontabili.

**Divergenza fra i due ambienti, dichiarata.** La VM usa CPython 3.12 su aarch64,
il PC CPython 3.14.6 su x86-64. Le **versioni dei pacchetti sono identiche**
(vedere la voce 38), quindi la divergenza si riduce alla versione minore
dell'interprete e all'architettura. Nessun risultato sperimentale viene prodotto
sulla VM: la VM raccoglie e consolida, cioe' esegue trasformazioni deterministiche
di formato, mentre ogni numero che finisce nel documento e' calcolato sul PC. La
riproducibilita' resta percio' intatta.

**Come si potrebbe verificare.** Confrontare la copertura reale calcolata da
`deploy/stato.sh` prima e dopo lo spostamento. Sul PC era del 7,2%; sulla VM deve
restare vicina al 100% salvo interruzioni dichiarate in `gaps.jsonl`.

---

### 38. Dipendenze della VM: sottoinsieme, ma versioni identiche

**Decisione.** `deploy/requirements-collector.txt` elenca sei pacchetti invece di
dodici, con le **stesse versioni esatte** di `requirements.txt`.

**Alternative considerate.** Riusare `requirements.txt` per intero; oppure
allentare i vincoli di versione se qualcuno non fosse esistito per aarch64.

**Motivo.** Il collector importa dalla libreria standard piu' `yaml` e
`google.transit`; il consolidamento aggiunge `pandas`, `pyarrow` e `numpy`. Il
resto non serve. Prima di scrivere qualunque cosa e' stato verificato, con una
risoluzione mirata alla piattaforma di destinazione, che tutte e sei le versioni
esistano come wheel `cp312` per `manylinux aarch64`: PyYAML e protobuf su
`manylinux2014`, pandas su `manylinux_2_24`, numpy su `manylinux_2_27`, pyarrow
su `manylinux_2_28`, gtfs-realtime-bindings come pacchetto puro. Il tag piu'
restrittivo richiede glibc 2.28 e Ubuntu 24.04 ne ha la 2.39.

Non e' stato necessario allentare alcun vincolo, che era l'esito che rischiava di
compromettere la riproducibilita'. E' stata inoltre verificata la compatibilita'
sintattica dei moduli che girano sulla VM con Python 3.12 e 3.11, dato che sono
stati scritti su 3.14.

**Come si potrebbe verificare.** Ripetere `pip install --dry-run
--only-binary=:all:` con i flag di piattaforma. Se una wheel sparisse dall'indice
il comando fallirebbe subito invece di ripiegare su una compilazione.

---

### 39. L'indirizzo della VM sta in `~/.ssh/config`, non in un file del progetto

**Decisione.** Gli script usano l'alias ssh `vm-icon`. Indirizzo e chiave stanno
nella configurazione ssh dell'utente, fuori dal repository.

**Alternative considerate.** Un file `deploy/vm.env` con `VM_HOST` e `VM_KEY`,
escluso da git tramite `.gitignore`.

**Motivo.** Il repository viene consegnato al docente, quindi ne' l'indirizzo
della VM ne' alcuna chiave devono poterci finire. Con `vm.env` la protezione
dipende interamente dal `.gitignore`: basta un `git add -f` distratto, o
l'invio di un archivio compresso della cartella, e il segreto esce. Con la
configurazione ssh il file sta altrove, quindi **il rischio non esiste per
costruzione** invece di essere mitigato. In piu' l'alias funziona identico per
`ssh`, `scp` e `rsync`, mentre `vm.env` avrebbe richiesto a ogni script di
comporre le opzioni a mano.

`deploy/vm.env` resta comunque nel `.gitignore` come rete di sicurezza.

**Come si potrebbe verificare.** Una ricerca di indirizzi IP e di materiale di
chiave su `deploy/` non deve trovare nulla. Gli script che non trovano l'alias
configurato si fermano stampando il blocco da incollare, senza tentare
connessioni verso un host vuoto.

---

### 40. Sincronizzazione senza rsync

**Decisione.** `deploy/sync.sh` usa `rsync` se lo trova nel PATH e altrimenti
ripiega su `tar` attraverso `ssh`.

**Alternative considerate.** Richiedere l'installazione di rsync da MSYS2;
oppure usare `scp -r` ritrasferendo tutto ogni volta.

**Motivo.** E' stato verificato che `rsync` non esiste in Git Bash e non e'
presente nemmeno nell'installazione MSYS2 sulla macchina: uno script scritto
attorno a rsync sarebbe fallito al primo lancio. Chiedere di installarlo per un
solo comando non e' proporzionato.

L'incrementalita' non si perde, e la ragione e' architetturale piu' che
implementativa. Il payload predefinito - archivi statici, `index.json`, manifest,
`gaps.jsonl`, parquet - pesa pochi MB e si trasferisce per intero in pochi
secondi, quindi distinguere il gia'-presente costerebbe piu' del trasferimento.
I dump grezzi, dopo il consolidamento, diventano archivi giornalieri
**immutabili**: un giorno chiuso non cambia mai piu', quindi basta scaricare i
file che non si hanno gia', e lo script li confronta per nome prima di chiederli.

**Come si potrebbe verificare.** Eseguire `sync.sh --grezzi` due volte di
seguito: la seconda non deve trasferire alcun archivio giornaliero.

---

### 41. Deduplica delle osservazioni, e il risultato negativo che l'accompagna

**Decisione.** Per ogni passaggio, identificato da `(trip_id, stop_sequence)`, si
conserva una riga a ogni **cambio** del valore osservato, con il `timestamp_feed`
della prima comparsa di quel valore. Sono disponibili due politiche alternative,
`ultimo` e `fasce`.

**Alternative considerate.** Una riga per passaggio, conservando solo l'ultima
osservazione; oppure una riga per ogni dump, senza alcuna deduplica.

**Motivo.** Una previsione che cambia nel corso della giornata **non e' un
duplicato**: e' l'evoluzione della stima dell'azienda, e dice quanto quella
previsione fosse affidabile con un certo anticipo. E' informazione che in Fase 3
potremmo voler usare come variabile esplicativa, e che non e' ricostruibile a
posteriori se la si getta ora. Conservare solo l'ultimo valore distruggerebbe un
dato irripetibile; conservare una riga per dump conserverebbe soprattutto
ripetizioni.

L'implementazione registra i cambi anziche' i valori distinti in senso
insiemistico. La differenza si vede solo quando una previsione torna a un valore
gia' visto: in quel caso la ricomparsa viene conservata come evento a se'. E'
voluto, perche' un'oscillazione e' informazione sulla stabilita' della stima, e
perche' riconoscere i valori gia' visti richiederebbe di tenere in memoria
l'intero insieme dei valori di ogni passaggio, che su Roma significa decine di
milioni di voci.

**Il risultato negativo.** Il presupposto della regola era che lo stesso
passaggio comparisse identico in centinaia di dump consecutivi, e che la
deduplica scartasse quindi la quasi totalita' delle righe. **Misurato sui dati
reali, non e' cosi'.** Su 98 dump di Roma, 1.982.754 `stop_time_update` hanno
prodotto 1.361.088 righe, cioe' il **68,6%** del totale: Roma ricalcola la
previsione quasi a ogni giro, e ogni passaggio riceve in media 10,9 valori
distinti, fino a un massimo di 76. Su Torino la quota e' il 65,1% con 5,4 valori
per passaggio. La proiezione a giornata piena e' di circa **20 milioni di righe
al giorno per Roma** e 2,2 milioni per Torino, quindi dell'ordine dei 280 milioni
di righe su due settimane.

La regola resta quella scelta, perche' la motivazione che la giustifica non e'
il risparmio ma la conservazione di un'informazione irripetibile. Va pero'
registrato che il beneficio in volume che le era stato attribuito non si e'
verificato, e che il dimensionamento della Fase 3 va fatto su questi numeri e non
su quelli attesi. Le politiche `ultimo` e `fasce` esistono proprio per poter
cambiare idea sulla base di una misura invece che di una previsione.

**Come si potrebbe verificare.** Confrontare, in Fase 3, la qualita' del modello
addestrato sui dati completi con quella ottenuta usando la sola ultima
osservazione per passaggio. Se la differenza fosse trascurabile, la politica
`ultimo` sarebbe preferibile e ridurrebbe il dataset di un ordine di grandezza.

---

### 42. Torino non trasmette lo `stop_id`: la chiave di join e' `(trip_id, stop_sequence)`

**Decisione.** L'orario programmato si interroga con la chiave
`(trip_id, stop_sequence)`, e lo `stop_id` mancante viene riempito dall'orario
statico.

**Alternative considerate.** La chiave naturale `(trip_id, stop_id,
stop_sequence)`, che era la prima implementazione.

**Motivo.** E' stato scoperto eseguendo il consolidamento sui dati veri e
notando che il numero di passaggi conservati non tornava: 4.691 invece dei 13.092
misurati. La causa e' che **GTT non include mai lo `stop_id`** nei
`stop_time_update`, identificando la fermata con il solo `stop_sequence`; Roma si
comporta all'opposto e lo fornisce sempre. Con la chiave naturale, il join su
Torino non trovava mai corrispondenza: la colonna `stop_id` restava vuota,
l'orario programmato nullo e il ritardo non calcolabile, e il parquet di Torino
sarebbe stato inutilizzabile in Fase 3 senza che nulla lo segnalasse.

La specifica GTFS garantisce che `stop_sequence` sia univoco dentro una corsa,
quindi la chiave ridotta e' altrettanto precisa e funziona su entrambe le
aziende. Quando il feed fornisce anche lo `stop_id` si usa quello del feed e si
verifica che coincida con quello statico; una divergenza viene contata e
segnalata, perche' significherebbe che la corsa in circolazione non e' quella che
l'orario descrive.

Lo stesso meccanismo copre il `route_id`, anch'esso assente nei `trip_update` di
Torino. Si potrebbe ricavarlo dai `vehicle_positions`, ma richiederebbe un
accoppiamento temporale fra due feed con timestamp diversi, mentre `trips.txt`
lo dichiara in modo esatto.

**Come si potrebbe verificare.** Dopo il consolidamento, il conteggio dei valori
vuoti nelle colonne `stop_id` e `route_id` deve essere zero per entrambe le
citta', e quello dei nulli in `orario_programmato` e `ritardo_secondi` pure. Sui
due giorni gia' consolidati e' cosi'.

---

## Fase 2 — Grafo tempo-espanso e ricerca

### 43. Il grafo copre una finestra temporale, non la giornata

**Decisione.** Il grafo tempo-espanso viene costruito sull'intervallo
`[partenza, partenza + orizzonte]`, con orizzonte predefinito di 120 minuti.

**Alternative considerate.** Costruire il grafo dell'intera giornata di servizio e
riusarlo per tutte le interrogazioni.

**Motivo.** L'orario di Roma contiene 5,6 milioni di passaggi al giorno. Il grafo
completo non e' un oggetto che si costruisca per rispondere a una singola
interrogazione, e riusarlo fra interrogazioni diverse non aiuterebbe, perche' la
Fase 5 eseguira' migliaia di interrogazioni con orari di partenza diversi. La
finestra e' anche cio' che una interrogazione usa davvero: nessuno accetta di
attendere quattro ore alla fermata.

Il limite va dichiarato come limite dei risultati e non come nota
implementativa: **la ricerca trova l'ottimo dentro la finestra**, e un itinerario
che richiedesse di attendere oltre l'orizzonte non verrebbe trovato affatto.

**Come si potrebbe verificare.** E' misurato su quante coppie origine-destinazione
dell'esperimento la finestra di due ore si riveli sufficiente. Le coppie non
risolte non vengono escluse dal campione: la loro percentuale e' essa stessa un
risultato, e toglierle darebbe una falsa impressione di completezza.

---

### 44. Lo stato si sdoppia in "a terra" e "a bordo"

**Decisione.** Lo stato della ricerca e' la terna `(fermata, istante, cambi)` piu'
l'informazione se ci si trovi a terra oppure a bordo di una corsa specifica.

**Alternative considerate.** La sola terna, come formulata inizialmente.

**Motivo.** La terna da sola non permette di contare correttamente i cambi.
Stando a una fermata a un dato istante, "restare a bordo" e "salire di nuovo"
sono indistinguibili se non si sa su quale corsa ci si trovi: un viaggiatore che
percorre dieci fermate senza scendere passerebbe per dieci stati che sembrano
altrettante salite, e la ricerca gli attribuirebbe dieci cambi. Il numero di
cambi e' uno dei tre criteri della ricerca multi-criterio, quindi l'errore
falserebbe l'intera frontiera di Pareto senza che nulla lo segnali.

Il cambio si conta alla salita e non alla discesa: contarlo alla discesa
addebiterebbe un cambio anche a chi scende semplicemente a destinazione.

**Come si potrebbe verificare.** Il test
`test_restare_a_bordo_non_conta_come_cambio` percorre una corsa che attraversa
piu' fermate e verifica che il conteggio resti a uno.

---

### 45. La chiave di stato a terra non contiene l'istante

**Decisione.** Uno stato a terra e' identificato dalla coppia `(fermata, cambi)`,
conservando l'istante di arrivo piu' precoce, e non dalla terna completa.

**Alternative considerate.** La lettura letterale della terna, che era
l'implementazione iniziale.

**Motivo.** E' una relazione di dominanza: trovarsi alla stessa fermata con lo
stesso numero di cambi ma **prima** e' sempre almeno altrettanto buono, perche'
ogni proseguimento disponibile a chi arriva tardi lo e' anche a chi arriva presto
- le corse partono agli stessi orari per entrambi - e attendere non costa nulla.
Gli stati con istante posteriore sono percio' dominati e possono essere eliminati
senza perdere soluzioni.

Il guadagno non e' marginale ed e' stato misurato: su una interrogazione di
Torino, la formulazione con l'istante nella chiave espandeva **6,4 milioni di
stati in 224 secondi**, quella con la chiave ridotta ne espande **45 mila in 0,7
secondi**, restituendo lo stesso orario di arrivo. Sono due ordini di grandezza,
e la differenza fra una ricerca utilizzabile e una che non lo e'.

Va sottolineato che non e' un'approssimazione: elimina stati dimostrabilmente
dominati, e l'ottimo resta garantito.

**Come si potrebbe verificare.** La coincidenza degli orari di arrivo prima e
dopo l'ottimizzazione, gia' osservata; e il test che confronta A* con una ricerca
esaustiva su istanze piccole, che continua a passare.

---

### 46. L'euristica usa il massimo VERO delle velocita', difetti dell'orario compresi

**Decisione.** La velocita' `V` dell'euristica geografica e' il massimo assoluto
misurato fra fermate consecutive sull'orario programmato, senza alcun taglio.

**Alternative considerate.** Un percentile alto, che sarebbe piu' rappresentativo
della fisica del problema; oppure l'esclusione degli archi anomali come dati
sporchi.

**Motivo.** L'ammissibilita' dell'euristica e' una delle poche proprieta' che il
progetto puo' **dimostrare formalmente**, ed e' cio' che garantisce che A*
restituisca l'ottimo. La dimostrazione richiede che `V` sia un limite superiore
alla velocita' di ogni spostamento **del grafo che stiamo cercando**, non della
realta' fisica: se la tabella oraria dichiara quattrocento metri in tre secondi,
allora in quel grafo quel movimento e' possibile, e `V` deve tenerne conto.

La misura mostra che questo accade davvero. Le velocita' fra fermate consecutive
hanno mediana di 16,4 km/h a Torino e 15,6 a Roma, valori perfettamente
plausibili, ma il massimo e' di **500,8 km/h a Torino e 297,1 a Roma**, con 135 e
1.063 archi rispettivamente sopra i 150 km/h. Caratterizzando gli archi anomali si
scopre che **il difetto non e' nelle coordinate ma negli orari**: le distanze sono
normali, dell'ordine dei 200-400 metri, ed e' la durata programmata a essere
assurda, tre secondi.

L'esclusione degli archi anomali e' stata scartata per una ragione precisa:
sposterebbe la garanzia da "vale sull'orario pubblicato" a "vale sull'orario che
abbiamo deciso noi", indebolendo proprio la parte piu' solida del progetto.

**Conseguenza, che e' un risultato negativo da riportare.** Con `V` cosi' grande
l'euristica vale quasi zero, e A* risparmia pochi punti percentuali di nodi
rispetto a Dijkstra, risultando anzi piu' lento in tempo di orologio perche'
calcolare l'euristica costa piu' dei nodi che fa evitare.

**Come si potrebbe verificare.** Il confronto e' misurato su cinquanta coppie per
citta' e riportato nella sezione della documentazione. Un test verifica inoltre
per campionamento che l'euristica non superi mai il costo residuo reale.

---

### 47. Una variante non ammissibile, come confronto e solo come confronto

**Decisione.** Accanto all'euristica ammissibile si misura una variante con `V`
pari al 99,9-esimo percentile delle velocita' - 82,0 km/h a Torino e 55,2 a Roma
- dichiarata **non ammissibile** ovunque compaia: nel codice, in una colonna del
CSV dei risultati e nella didascalia della figura.

**Alternative considerate.** Non misurarla affatto; oppure adottarla come
predefinita, guadagnando velocita'.

**Motivo.** Adottarla farebbe perdere la garanzia di ottimalita', che e' una
proprieta' dimostrabile e un punto di forza del progetto. Non misurarla
lascerebbe pero' senza risposta la domanda naturale: quanto costa davvero
rinunciare a quella garanzia? Misurandola si trasforma il difetto dei dati in un
risultato quantificato.

La scelta del 99,9-esimo percentile non e' arbitraria: produce valori fisicamente
plausibili per un mezzo urbano, mentre un percentile piu' basso escluderebbe
tratte veloci legittime, per esempio quelle ferroviarie o metropolitane.

Il numero che conta non e' il risparmio di nodi ma **su quante interrogazioni la
variante restituisce un orario di arrivo diverso dall'ottimo**: e' quello a
misurare il costo reale della rinuncia, invece di lasciarlo come rischio teorico.

**Come si potrebbe verificare.** La colonna `ottimo` di
`results/ricerca_astar.csv` confronta l'orario di ogni variante con quello di
Dijkstra, che non usa euristiche e non puo' quindi essere influenzato da una
stima sbagliata.

---

### 48. L'interfaccia del modello dei ritardi viene fissata prima dei dati

**Decisione.** `src/delays/interfaccia.py` definisce il contratto - una tratta
entra, una distribuzione esce - piu' una implementazione sintetica per lo
sviluppo. Il contratto e' fissato in Fase 2, due settimane prima che i dati
siano disponibili.

**Alternative considerate.** Aspettare i dati e progettare l'interfaccia sulla
forma che il modello appreso assumera'.

**Motivo.** La Fase 4 dovra' comporre distribuzioni di ritardo lungo una catena
di coincidenze. Aspettare i dati per decidere che forma abbia una distribuzione
significherebbe riscrivere le Fasi 2 e 4 quando arrivano. Le quattro operazioni
richieste - funzione di ripartizione, quantile, campionamento e media - non sono
arbitrarie: sono esattamente quelle che le fasi successive usano, la prima per
P(arrivo <= T), la seconda per la pinball loss, la terza per il Monte Carlo, la
quarta per i confronti con le baseline deterministiche.

**Il presidio contro l'uso accidentale.** Un modello sintetico e' per costruzione
indistinguibile da uno vero attraverso l'interfaccia, ed e' proprio questo a
renderlo pericoloso: senza un controllo esplicito basterebbe una dimenticanza per
pubblicare nel documento numeri calcolati su ritardi inventati, e nulla
nell'output lo segnalerebbe. Il presidio ha tre livelli: ogni modello espone un
attributo `sintetico`; ogni script che scriva in `results/` chiama
`assicura_utilizzabile`, che solleva un errore a meno che non sia stato passato
`--sintetico-ammesso`; e ogni CSV porta il nome del modello che lo ha prodotto,
cosi' l'origine di un risultato resta leggibile anche a distanza di mesi.

**Come si potrebbe verificare.** Tentare di eseguire uno script sperimentale con
il modello sintetico senza il permesso esplicito deve fallire con un messaggio che
spiega perche'. Nessun file in `results/` deve riportare `sintetico` nella colonna
del modello.
