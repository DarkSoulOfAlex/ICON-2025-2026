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
