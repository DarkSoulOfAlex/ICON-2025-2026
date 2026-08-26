# Un pianificatore di viaggi robusto ai ritardi

Documento di progetto per il corso di Ingegneria della Conoscenza.

> Documento in costruzione. Le sezioni presenti sono quelle chiuse dalle fasi
> gia' concluse; l'introduzione, le sezioni sulla ricerca, sul modello
> probabilistico e sulla valutazione sperimentale arriveranno con le rispettive
> fasi.

---

## Rappresentazione della conoscenza

### Il problema che la base di conoscenza deve risolvere

Un pianificatore di viaggi ha bisogno di sapere, per ogni coppia di fermate, se
un passeggero possa passare dall'una all'altra e quanto tempo gli occorra come
minimo. Questa relazione, che chiameremo di *trasbordo*, e' il fondamento su cui
poggia tutto il resto del progetto: il grafo tempo-espanso della Fase 2 la usa
per costruire gli archi di cambio, e il calcolo di probabilita' della Fase 4 la
usa per stabilire quando una coincidenza sia da considerarsi persa.

La circostanza che ha determinato la forma di questa parte del lavoro e' che la
relazione di trasbordo **non esiste nei dati di partenza**. Lo standard GTFS
prevede un file facoltativo, `transfers.txt`, in cui un'azienda puo' dichiarare
esplicitamente quali cambi siano possibili e con quale tempo minimo. Abbiamo
verificato il contenuto degli archivi di entrambe le aziende del progetto, Roma
Mobilita' e GTT di Torino: nessuna delle due lo pubblica. L'archivio di Roma
contiene `agency.txt`, `calendar_dates.txt`, `routes.txt`, `shapes.txt`,
`stop_times.txt`, `stops.txt` e `trips.txt`; quello di Torino aggiunge alcuni
file non standard sulle tariffe e sui quadri orari, ma neppure lui contiene i
trasbordi.

Questa assenza si e' rivelata la migliore garanzia possibile contro l'obiezione
che una base di conoscenza sia soltanto un database interrogato con un'altra
sintassi. Non esiste alcuna tabella dei trasbordi da leggere, filtrare o
giuntare: l'intera relazione va **derivata** a partire da cio' che i dati
effettivamente contengono, cioe' le coordinate delle fermate, la gerarchia che
lega le banchine alle stazioni, l'accessibilita' dichiarata di ciascuna fermata e
l'elenco delle linee che vi transitano. Ogni trasbordo che il pianificatore
utilizzera' e' una conclusione inferita, non un dato letto.

### I fatti e la loro forma

La base di conoscenza riceve dal GTFS otto predicati. Le fermate fisiche, con la
loro posizione e la cella dell'indice spaziale a cui appartengono; il legame fra
una banchina e la stazione che la contiene; il valore di accessibilita' dichiarato
per ciascuna fermata secondo la codifica dello standard, dove lo zero significa
"informazione non disponibile" e non "non accessibile"; l'elenco delle coppie
linea-fermata; e, quando esistono, i trasbordi dichiarati dall'azienda e le
segnalazioni contingenti di ascensori fuori servizio.

Due trasformazioni avvengono prima che i fatti raggiungano il programma logico, e
vale la pena dichiarare perche' non spostino conoscenza fuori dalla base. La
prima e' che gli identificativi testuali delle fermate diventano numeri interi:
la corrispondenza e' biunivoca e viene conservata, il risultato si ritraduce
esattamente, e il guadagno e' soltanto di velocita' nel grounding. La seconda e'
che le coordinate geografiche diventano metri interi su una proiezione piana
locale centrata sul baricentro delle fermate della citta'. Anche questo e' un
cambio di unita' di misura, non di contenuto: e' l'analogo del conservare gli
orari in secondi anziche' nella forma `HH:MM:SS`. La regola che stabilisce
*quali* coppie di fermate costituiscano un trasbordo resta interamente dentro il
programma logico, e opera sulle coordinate cosi' come le riceve.

### Il tempo minimo di trasbordo come eredita' difettibile

La regola piu' significativa del progetto e' quella che stabilisce quanto tempo
occorra come minimo per un cambio. Il valore non e' memorizzato da nessuna parte
e non e' unico: dipende da che tipo di trasbordo si tratti, e le fonti di
informazione hanno una gerarchia di autorevolezza. Se l'azienda ha dichiarato un
tempo per quella specifica coppia, vale quello. In assenza di una dichiarazione,
se le due fermate sono banchine della stessa stazione vale il tempo di
percorrenza interno alla stazione, piu' lungo del semplice cammino perche'
comprende sottopassi, scale e tornelli. In assenza di entrambe le condizioni,
vale il tempo di cammino all'aperto piu' un margine.

Le tre regole che realizzano questa gerarchia sono le seguenti.

```prolog
tempo_minimo_trasbordo(F1, F2, T) :-
    dichiarato(F1, F2, T).

tempo_minimo_trasbordo(F1, F2, tempo_stazione) :-
    stessa_stazione(F1, F2),
    not dichiarato(F1, F2, _).

tempo_minimo_trasbordo(F1, F2, T + margine_piedi) :-
    tempo_piedi(F1, F2, T),
    not dichiarato(F1, F2, _),
    not stessa_stazione(F1, F2).
```

Il meccanismo che realizza la priorita' e' interamente affidato ai tre `not`: una
regola di livello inferiore si applica soltanto quando nessuna regola piu'
specifica ha gia' concluso. E' la struttura classica dell'eredita' difettibile,
quella per cui un default vale finche' non interviene un'eccezione piu' precisa.

Un'interrogazione relazionale puo' riprodurre questo risultato, ma solo scrivendo
la gerarchia delle priorita' dentro la query stessa, tipicamente sotto forma di
una catena di `COALESCE` o di una sequenza di `LEFT JOIN` ordinati. La differenza
non e' di eleganza ma di collocazione della conoscenza: in quel caso la gerarchia
vive nel codice dell'interrogazione, e aggiungere un livello significa riscrivere
la query. Qui la gerarchia e' dichiarata nella base di conoscenza, e aggiungere un
livello significa aggiungere una regola senza toccare le altre. Il collaudo di
questa proprieta' verifica esattamente la parte non riducibile: dichiarando un
tempo per la sola direzione da `A1` verso `A2`, quella direzione assume il valore
dichiarato mentre la direzione opposta, non dichiarata, resta governata dalla
regola della stazione. La sovrascrittura e' puntuale, come dev'essere un
default.

### L'accessibilita' come conoscenza non monotona

La seconda regola riportata riguarda l'accessibilita' di un trasbordo per un
passeggero a ridotta mobilita'.

```prolog
accessibile(F1, F2) :-
    trasbordo_ammissibile(F1, F2, _),
    fermata_accessibile(F1),
    fermata_accessibile(F2),
    not eccezione_accessibilita(F1, F2).

eccezione_accessibilita(F1, F2) :-
    tempo_piedi(F1, F2, T),
    T > tempo_piedi_max_sedia.

eccezione_accessibilita(F1, F2) :-
    trasbordo_ammissibile(F1, F2, _),
    ascensore_fuori_servizio(F1).
```

Qui la proprieta' rilevante e' la **non monotonia**: aggiungere un fatto alla base
di conoscenza *rimuove* conclusioni che erano gia' state derivate. Dichiarando che
l'ascensore della fermata `A1` e' fuori servizio, quattro trasbordi che risultavano
accessibili smettono di esserlo, e nessuno ne prende il posto. Nessuna
interrogazione relazionale positiva ha questo comportamento, per una ragione
strutturale e non implementativa: in algebra relazionale l'aggiunta di tuple a una
relazione non puo' mai ridurre il risultato di una query positiva. Il
comportamento e' verificato da un test che confronta l'insieme delle conclusioni
prima e dopo l'aggiunta del fatto, e controlla non solo che quattro conclusioni
siano sparite, ma anche che nessuna sia comparsa.

Vale la pena notare che le eccezioni non sono tutte dichiarate: la prima e'
*derivata*. Un trasbordo a piedi diventa inaccessibile in forza della propria
distanza, senza che nessuno debba annotarlo, perche' la regola confronta il tempo
di cammino con una soglia. Anche l'antecedente `fermata_accessibile` e' a sua
volta un'eredita' con default, perche' lo standard GTFS prescrive che il valore
zero su una banchina significhi "eredita dalla stazione".

### La raggiungibilita' come chiusura transitiva

La terza regola e' la definizione ricorsiva della raggiungibilita'.

```prolog
raggiungibile(F, F) :- fermata(F).

raggiungibile(F1, F3) :-
    raggiungibile(F1, F2),
    trasbordo_ammissibile(F2, F3, _).
```

Due fermate sono collegate se esiste una catena di trasbordi che porti dall'una
all'altra, di lunghezza qualsiasi. La ricorsione non e' un artificio: il numero di
cambi necessari a collegare due punti di una rete non e' noto in anticipo e
dipende dalla topologia della citta'. Il collaudo verifica proprio la parte che
solo la ricorsione puo' produrre, disponendo quattro fermate in fila a duecento
metri l'una dall'altra, sotto la soglia di duecentocinquanta metri per le coppie
adiacenti e sopra per quelle a un posto di distanza: nessun trasbordo diretto
collega la prima alla terza, eppure la chiusura le collega, e collega anche la
prima alla quarta.

Una variante della stessa regola calcola la chiusura sui soli trasbordi
accessibili. Non e' una duplicazione: e' un'altra domanda, perche' un percorso
esistente per un passeggero qualsiasi puo' non esistere per un passeggero in
sedia a rotelle, e distinguere le due raggiungibilita' e' precisamente il tipo di
conoscenza che il progetto vuole rappresentare.

### I vincoli di integrita'

Il quarto elemento riportato e' un vincolo.

```prolog
:- fermata(F),
   #count { F2 : trasbordo_a_piedi(F, F2) } > grado_massimo_plausibile.

:- trasbordo_ammissibile(F1, F2, T), tempo_piedi(F1, F2, TP), T < TP.
```

Un vincolo di integrita' non filtra righe: **rifiuta il modello**. Se una sola
coppia di fermate lo viola, il programma non ha alcuna risposta, e non una
risposta piu' corta. E' una condizione sull'intera interpretazione, di natura
diversa da qualunque clausola `WHERE`, e serve a garantire che cio' che esce dalla
base di conoscenza sia coerente per costruzione anziche' per controllo a valle.

Nello scrivere questa parte abbiamo scartato alcuni vincoli che avevamo
inizialmente formulato, come il divieto per una fermata di essere trasbordo di se
stessa, perche' la costruzione delle regole li rende impossibili per definizione:
un vincolo che non puo' mai essere violato non e' logica, e' un commento
travestito da logica. I quattro rimasti sono stati scelti perche' possono davvero
scattare, e ciascuno corrisponde a un difetto documentato dei dati aperti. Il
primo dei due riportati intercetta le fermate prive di coordinate, che nei feed
reali finiscono tutte nello stesso punto e formerebbero un nodo di scambio
inesistente ma enorme; il secondo intercetta i tempi di trasbordo dichiarati piu'
brevi del tempo materialmente necessario a percorrere la distanza a piedi, che
renderebbero il pianificatore sistematicamente troppo fiducioso e produrrebbero,
in Fase 5, coincidenze perse senza spiegazione apparente. Tutti e quattro sono
collaudati costruendo il dato che li viola e verificando che il programma diventi
insoddisfacibile, e che torni soddisfacibile disattivando i soli vincoli.

### Dove sta la negazione e perche' e' stratificata

La negazione per fallimento compare in cinque punti: nelle due regole di
sovrascrittura del tempo minimo, nella regola dell'accessibilita' e nella
definizione di trasbordo utile, che chiede l'esistenza di una linea servita dalla
fermata di arrivo e non servita da quella di partenza.

In tutti i casi la negazione e' **stratificata**, e la verifica e' diretta.
`dichiarato` e' un fatto in ingresso e non dipende da nulla. `stessa_stazione`
dipende soltanto da `in_stazione`, anch'esso un fatto in ingresso.
`eccezione_accessibilita` dipende da `tempo_piedi`, da `trasbordo_ammissibile` e
dal fatto contingente sugli ascensori, ma non da `accessibile`. `serve` e' un
fatto in ingresso. Nessuno dei predicati che compaiono negati dipende, nemmeno
per via indiretta, dal predicato che lo nega: il grafo delle dipendenze non
contiene percio' alcun ciclo che attraversi una negazione, e il programma
ammette un unico modello stabile ben definito. E' questa proprieta' a garantire
che la base di conoscenza abbia una risposta sola, e non un insieme di risposte
alternative fra cui scegliere.

L'unica ricorsione presente, quella della raggiungibilita', e' puramente
positiva, quindi non interferisce con la stratificazione.

### L'indice spaziale

La regola del trasbordo a piedi confronta coppie di fermate. Confrontarle tutte
significa istanziare un numero di atomi quadratico: sulle 8.301 fermate di Roma
sono circa 69 milioni di coppie, e il grounding non termina in tempo utile. La
base di conoscenza usa percio' un indice spaziale: ogni fermata riceve una cella
di una griglia regolare, calcolata dalle sue coordinate, e la regola confronta
soltanto le fermate che si trovano nella stessa cella o in una delle otto
adiacenti.

E' importante dichiarare esplicitamente che cosa sia e che cosa non sia questo
accorgimento. Non e' clustering: non c'e' nulla di appreso, nessun centroide,
nessuna funzione obiettivo, nessuna scelta dipendente dai dati. E'
un'indicizzazione deterministica sulle coordinate, l'equivalente spaziale di un
indice su una colonna di una tabella.

Soprattutto, **non altera la semantica della regola**, e la ragione e'
geometrica. Il lato della cella e' posto uguale alla soglia di cammino: due
fermate che distino meno della soglia non possono quindi cadere in celle non
adiacenti, e nessun trasbordo puo' sfuggire al confronto. L'insieme dei trasbordi
derivati e' percio' identico a quello che si otterrebbe confrontando tutte le
coppie. Poiche' un'argomentazione geometrica puo' sempre nascondere un errore, la
proprieta' e' anche verificata per via sperimentale: il programma logico espone
un interruttore che sostituisce la regola indicizzata con quella esaustiva, e la
misura della sezione seguente confronta i due insiemi di trasbordi su ogni
dimensione in cui entrambe le varianti sono eseguibili. Sono risultati identici
in tutti i casi.

### Il calendario di servizio, e una scoperta che ha cambiato il modulo

La base di conoscenza lavora sulla topologia della rete e non sul calendario, ma
il calendario e' un prerequisito di tutto il resto, ed e' opportuno riferire qui
una circostanza emersa dai dati che ha modificato il progetto del modulo che lo
gestisce.

Lo standard GTFS prevede due modi complementari di dichiarare quando una corsa
circoli. Il file `calendar.txt` esprime una regola settimanale con un periodo di
validita': questa corsa circola dal lunedi' al venerdi' fra due date. Il file
`calendar_dates.txt` esprime eccezioni puntuali a quella regola, additive o
sottrattive. Lo standard richiede che almeno uno dei due sia presente, ma non
entrambi.

Le due aziende del progetto usano i due regimi opposti. Torino pubblica
`calendar.txt` con 1.106 servizi e `calendar_dates.txt` con 34.758 eccezioni,
cioe' la forma canonica. Roma **non pubblica affatto** `calendar.txt`: ogni
singolo giorno di servizio e' elencato come eccezione additiva, e le 4.707 righe
di `calendar_dates.txt` sono l'unica fonte del calendario. Entrambe le scelte
sono conformi.

La conseguenza pratica e' che un modulo scritto sull'assunzione implicita che
`calendar.txt` esista funzionerebbe perfettamente su Torino e restituirebbe zero
corse attive su Roma, senza sollevare alcuna eccezione e senza somigliare in alcun
modo a un errore. Avere due citta' con regimi opposti ha trasformato una
possibile fonte di errore silenzioso in un caso di prova: la funzione che
determina i servizi attivi parte da un insieme vuoto quando la regola settimanale
manca, applica le aggiunte e infine le rimozioni, in quest'ordine, perche' una
rimozione deve poter cancellare anche un servizio introdotto da un'aggiunta dello
stesso giorno.

Alla stessa categoria appartiene il trattamento degli orari oltre la mezzanotte.
Il GTFS ammette e usa regolarmente valori come `25:30:00`, che indicano l'una e
mezza di notte del giorno successivo ma appartenenti al giorno di servizio
precedente. Riportarli sotto le ventiquattro ore, che e' la normalizzazione
istintiva, sposta silenziosamente tutte le corse notturne sul giorno sbagliato. Il
modulo li conserva percio' come secondi non normalizzati, e traduce un orario in
un istante reale seguendo la definizione della specifica, secondo cui i tempi si
misurano da "mezzogiorno meno dodici ore" del giorno di servizio. Nei giorni
ordinari questa definizione coincide con la mezzanotte; nei due giorni all'anno in
cui cambia l'ora legale no, e la differenza e' esattamente un'ora su tutte le
corse della giornata.

### Che cosa i dati non contengono, e cosa ne consegue

Eseguendo la base di conoscenza sulle reti complete e' emerso un risultato
negativo che vale la pena riportare per intero, perche' riguarda il rapporto fra
la generalita' delle regole e la poverta' dei dati su cui vengono applicate.

Delle 8.301 fermate di Roma, **tutte** dichiarano `wheelchair_boarding` uguale a
zero, che nella codifica dello standard significa "informazione non
disponibile"; lo stesso vale per il campo corrispondente su tutte le 179.177
corse. Inoltre, **nessuna** fermata di Roma dichiara una `parent_station`: la
gerarchia delle stazioni, nell'archivio di Roma, semplicemente non esiste. Torino
si comporta diversamente: 2.722 fermate sono dichiarate accessibili, 1.075
esplicitamente non accessibili e 3.276 senza informazione, e 47.023 corse su
60.580 sono dichiarate accessibili; ma anche li' soltanto due fermate su 7.073
appartengono a una stazione.

Le conseguenze si leggono direttamente nella Tabella 5. Su Roma la regola
dell'accessibilita' deriva **zero** trasbordi accessibili: non perche' sia
sbagliata, ma perche' il suo antecedente non e' mai soddisfatto, dal momento che
nessuna fermata risulta accessibile e non esiste alcuna stazione da cui ereditare
il dato. Su Torino la stessa regola funziona e deriva 7.382 trasbordi accessibili
su 21.130, cioe' poco piu' di un terzo. Quanto alla gerarchia dei tempi minimi,
il suo primo livello non riceve alcun fatto su nessuna delle due citta', perche'
nessuna pubblica `transfers.txt`, e il secondo livello si applica a due sole
fermate in tutto il progetto: in pratica, su questi dati, l'eredita' difettibile
collassa quasi ovunque sul suo terzo livello, quello del cammino all'aperto.

Sarebbe disonesto presentare come funzionante una gerarchia a tre livelli di cui,
sul campo, ne opera stabilmente uno solo. Va detto invece con precisione che cosa
questo dimostri e che cosa no. Dimostra che la formulazione e' piu' generale dei
dati disponibili, il che e' una scelta deliberata: la base di conoscenza e'
scritta per il formato GTFS e non per due archivi particolari, e su un'azienda
che pubblichi `transfers.txt` e una gerarchia di stazioni i primi due livelli
entrerebbero in funzione senza modificare una riga. Non dimostra che quei livelli
siano utili in pratica su Roma e Torino, perche' su Roma e Torino non lo sono. Il
loro collaudo e' percio' affidato a dati costruiti, ed e' l'unica forma di
verifica possibile finche' non si aggiunga al progetto una terza citta' con un
archivio piu' ricco.

C'e' infine una conseguenza per la valutazione sperimentale delle fasi
successive. La distinzione fra `raggiungibile` e `raggiungibile_accessibile`, che
sul piano della rappresentazione e' una delle parti piu' interessanti, e'
misurabile soltanto su Torino. Ogni risultato sull'accessibilita' che comparira'
nelle fasi successive andra' quindi riferito a Torino, e non alla media delle due
citta'.

### Limiti di questa rappresentazione

Tre limiti vanno dichiarati. Il primo e' che il tempo di cammino e' discretizzato
in quattro bande anziche' calcolato con continuita': e' una scelta di modello,
motivata dal fatto che un tempo di trasbordo ha senso al mezzo minuto e non al
metro, ma resta un'approssimazione. Il secondo e' che la distanza fra due fermate
e' quella in linea d'aria, non quella effettivamente percorribile a piedi: la base
di conoscenza non dispone del grafo stradale, e in presenza di una ferrovia o di
un fiume fra due fermate vicine il tempo derivato e' ottimistico. Il terzo, discusso per esteso
poco sopra, e' che due dei tre livelli della gerarchia dei tempi minimi non
ricevono alcun fatto da queste due citta', e che su Roma la regola
dell'accessibilita' non deriva nulla per assenza del dato di partenza.

---

## Complessita' della base di conoscenza

### Protocollo di misura

La misura risponde a una domanda pratica: fino a che dimensione di rete questa
base di conoscenza resta utilizzabile, e quale delle sue regole ne determina il
costo. Sono state misurate cinque dimensioni crescenti, da cinquanta a duemila
fermate, su entrambe le citta', con tre ripetizioni indipendenti per ogni
combinazione. Per ciascuna esecuzione si registrano il numero di atomi generati,
il tempo di grounding e il tempo di solving, tenuti separati perche' misurano due
cose diverse: il primo e' il costo di istanziare le regole sui dati, il secondo
quello di risolvere il programma proposizionale che ne risulta.

Le sottoreti sono ottenute per **prossimita' geografica**: si prendono le N
fermate piu' vicine a un centro fisso. Il centro non e' stato scelto a mano ma
derivato dai dati, come la fermata piu' vicina al baricentro geometrico di tutte
le fermate della citta'; per Roma e' la fermata 70841, S. SABA/AVENTINO, per
Torino la 962, Fermata 1873 - PUGLIA C.3. La scelta del campionamento per
prossimita' anziche' casuale non e' neutra e va motivata: cinquanta fermate
estratte a sorte fra le ottomila di Roma finirebbero sparse su tutta la citta', a
chilometri l'una dall'altra, e non genererebbero quasi nessun trasbordo a piedi.
La curva misurerebbe il costo di un problema che non somiglia a quello vero. Il
campionamento per prossimita' conserva invece la densita' reale della rete, ed e'
inoltre monotono, nel senso che un campione piu' grande contiene quello piu'
piccolo: senza questa proprieta' i punti della curva non sarebbero confrontabili
fra loro, perche' misurerebbero reti diverse anziche' la stessa rete a dimensioni
diverse. Il prezzo va dichiarato: i risultati valgono per una porzione connessa e
densa di rete, e non sono estrapolabili a un campione sparso di pari cardinalita'.

Una precisazione metodologica sulle deviazioni standard riportate. Il numero di
atomi e quello di regole sono grandezze **deterministiche**: a parita' di dati e
di programma, clingo genera sempre la stessa istanziazione. La loro deviazione
standard sulle tre ripetizioni e' percio' nulla per costruzione, e riportarla
serve unicamente a documentare che le ripetizioni sono state effettivamente
eseguite. La variabilita' reale sta nei tempi, che dipendono dal carico della
macchina, ed e' li' che la deviazione standard porta informazione.

### Risultati

Tabella 1 - Roma, media e deviazione standard su tre ripetizioni.

| Fermate | Atomi | Grounding (s) | Solving (s) | Trasbordi derivati |
| ---: | ---: | ---: | ---: | ---: |
| 50 | 7.334 ± 0 | 0,012 ± 0,001 | 0,0006 ± 0,0001 | 436 |
| 150 | 24.463 ± 0 | 0,048 ± 0,006 | 0,0015 ± 0,0001 | 1.096 |
| 400 | 70.612 ± 0 | 0,160 ± 0,048 | 0,0039 ± 0,0003 | 2.738 |
| 1000 | 724.410 ± 0 | 1,692 ± 0,139 | 0,0150 ± 0,0003 | 7.232 |
| 2000 | 2.358.444 ± 0 | 5,707 ± 0,753 | 0,0380 ± 0,0008 | 13.938 |

Tabella 2 - Torino, media e deviazione standard su tre ripetizioni.

| Fermate | Atomi | Grounding (s) | Solving (s) | Trasbordi derivati |
| ---: | ---: | ---: | ---: | ---: |
| 50 | 3.141 ± 0 | 0,005 ± 0,000 | 0,0003 ± 0,0000 | 164 |
| 150 | 13.862 ± 0 | 0,021 ± 0,000 | 0,0010 ± 0,0000 | 688 |
| 400 | 34.018 ± 0 | 0,052 ± 0,006 | 0,0024 ± 0,0002 | 1.616 |
| 1000 | 136.729 ± 0 | 0,245 ± 0,012 | 0,0072 ± 0,0008 | 4.498 |
| 2000 | 438.374 ± 0 | 0,910 ± 0,042 | 0,0190 ± 0,0029 | 9.542 |

![Complessita' della base di conoscenza](../results/complessita_kb.png)

**Figura 1.** Costo della base di conoscenza al crescere del numero di fermate,
in scala doppio logaritmica, per le due citta'. I pannelli (a), (b) e (c)
riportano rispettivamente gli atomi generati, il tempo di grounding e il tempo di
solving, come media su tre ripetizioni indipendenti con barre di deviazione
standard; sugli atomi le barre sono nulle per costruzione, trattandosi di una
grandezza deterministica. Il pannello (d) confronta la variante con indice
spaziale, a linea continua, con quella che confronta tutte le coppie di fermate,
a linea tratteggiata, eseguita solo fino a quattrocento fermate perche' oltre
quella soglia il suo costo quadratico non aggiunge informazione. Dati grezzi in
`results/complessita_kb.csv`.

### Da dove nasce la crescita

La pendenza delle curve in scala doppio logaritmica e' l'esponente di crescita.
Su tutto l'intervallo misurato gli atomi crescono come `n^1,59` a Roma e come
`n^1,30` a Torino, ma il dato interessante e' che la pendenza **aumenta con la
dimensione**: sull'ultimo raddoppio, da mille a duemila fermate, entrambe le
citta' si assestano attorno a `n^1,70`. Non e' una crescita polinomiale di ordine
fisso, e' una crescita che accelera, e la spiegazione sta in quale regola stia
generando gli atomi.

Disattivando la sola ricorsione e rieseguendo la stessa istanza si ottiene
l'attribuzione diretta, senza doverla dedurre.

Tabella 3 - Quota di atomi generata dalla chiusura transitiva.

| Fermate | Roma | Torino |
| ---: | ---: | ---: |
| 50 | 31,5% | 32,2% |
| 150 | 45,7% | 35,2% |
| 400 | 52,6% | 35,7% |
| 1000 | 88,0% | 54,9% |
| 2000 | 92,9% | 70,4% |

A cinquanta fermate la ricorsione produce meno di un terzo degli atomi, e il
costo e' dominato dalla generazione delle coppie candidate e dal calcolo delle
distanze. A duemila fermate, su Roma, il 92,9% degli atomi nasce dalla sola
chiusura transitiva. E' questa la regola che domina il grounding, e il motivo e'
strutturale: la chiusura transitiva di una relazione e' quadratica nella
dimensione della componente connessa su cui viene calcolata, e man mano che la
sottorete si allarga le fermate finiscono quasi tutte nella stessa componente. Il
numero di atomi di `raggiungibile` tende percio' al quadrato del numero di
fermate connesse, mentre tutte le altre regole restano lineari nel numero di
coppie candidate, che l'indice spaziale mantiene proporzionale al numero di
fermate.

Il tempo di solving, che nelle tabelle e' due ordini di grandezza inferiore a
quello di grounding, conferma la lettura. Il programma, una volta istanziato, e'
sostanzialmente deterministico: non ci sono scelte da compiere, perche' la
negazione e' stratificata e la ricorsione e' positiva, quindi il modello stabile
e' unico e il risolutore non deve esplorare alcuno spazio di ricerca. Il costo di
questa base di conoscenza e' interamente un costo di istanziazione, non di
ricerca.

### Perche' le due reti si comportano in modo diverso

A parita' di numero di fermate Roma costa costantemente piu' di Torino, e il
divario si allarga: a cinquanta fermate il rapporto fra gli atomi e' 2,3, a
duemila e' 5,4. La differenza non sta nelle dimensioni assolute delle due reti,
che sono confrontabili, 8.301 fermate contro 7.073, ma nella **densita' locale**.

Nella sottorete campionata attorno al centro, Roma deriva stabilmente attorno a
sette trasbordi per fermata, Torino attorno a quattro e mezzo. Un rapporto di
densita' di circa 1,5 diventa un rapporto di 5,4 sul numero di atomi proprio per
via della chiusura transitiva: una componente connessa piu' densa e' anche piu'
grande, e il costo della chiusura cresce con il quadrato della sua dimensione. Lo
si vede anche nella Tabella 3, dove Torino raggiunge a duemila fermate la quota di
atomi ricorsivi che Roma aveva gia' superato a mille: la stessa curva, traslata.

E' il risultato che giustifica l'aver misurato due citta' anziche' una. Con una
sola rete non si sarebbe potuto distinguere fra un costo intrinseco della
formulazione e un costo dipendente dalla topologia; con due si vede che la forma
della crescita e' la stessa e che a cambiare e' solo la costante, governata dalla
densita' della rete.

### Il costo dell'indice spaziale

Il pannello (d) della Figura 1 confronta la formulazione indicizzata con quella
che confronta tutte le coppie di fermate.

Tabella 4 - Atomi generati con e senza indice spaziale.

| Fermate | Roma, con | Roma, senza | Torino, con | Torino, senza |
| ---: | ---: | ---: | ---: | ---: |
| 50 | 7.334 | 10.222 | 3.141 | 7.377 |
| 150 | 24.463 | 63.727 | 13.862 | 55.330 |
| 400 | 70.612 | 375.992 | 34.018 | 345.082 |

Il risparmio non e' un fattore costante ma **cresce con il numero di fermate**,
perche' la variante esaustiva genera un numero di coppie quadratico mentre quella
indicizzata lo mantiene proporzionale al numero di fermate: si passa da 1,4 volte
a cinquanta fermate a 5,3 volte a quattrocento su Roma, e da 2,3 a 10,1 su
Torino. Sull'intera rete di Roma la variante esaustiva dovrebbe istanziare circa
69 milioni di coppie, il che spiega perche' quella formulazione non sia
praticabile a piena scala.

La verifica che conta non e' pero' quella sul costo, ma quella sulla semantica. A
ogni dimensione in cui entrambe le varianti sono state eseguite, l'insieme dei
trasbordi derivati e' risultato **identico**: stessi trasbordi, stessi tempi
minimi, stessi attributi di accessibilita' e di utilita'. L'indice restringe
l'ordine di istanziazione, non l'insieme delle conclusioni, e l'argomentazione
geometrica esposta nella sezione precedente trova qui la sua conferma
sperimentale.

### La rete intera

La curva si ferma a duemila fermate perche' oltre quella soglia il campionamento
per prossimita' comincia a coincidere con la rete intera, e il confronto fra
dimensioni perde significato. La rete intera e' pero' stata eseguita, e i suoi
numeri sono una misura e non un'estrapolazione.

Tabella 5 - Esecuzione sull'intera rete di ciascuna citta'.

| | Roma | Torino |
| --- | ---: | ---: |
| Fermate | 8.301 | 7.073 |
| Fatti in ingresso | 55.894 | 44.187 |
| Atomi generati | 4.541.658 | 958.909 |
| Tempo di grounding | 11,3 s | 2,1 s |
| Tempo di solving | 0,09 s | 0,04 s |
| Trasbordi derivati | 41.266 | 21.130 |
| di cui accessibili | 0 | 7.382 |
| di cui utili | 24.554 | 11.439 |

L'intera base di conoscenza di Roma si istanzia in undici secondi e mezzo, che e'
un costo pienamente sostenibile per un'elaborazione da eseguire una volta al
giorno, quando l'orario statico cambia. La sproporzione fra grounding e solving
si conferma e si accentua: il risolutore impiega meno di un centesimo del tempo
speso a istanziare.

Va segnalato che il numero di atomi sulla rete intera di Roma, 4,5 milioni, e'
inferiore ai 26 milioni che l'esponente `n^1,70` misurato sull'ultimo raddoppio
avrebbe fatto prevedere. La ragione e' che il campionamento per prossimita'
seleziona la porzione **piu' densa** della rete, quella centrale: allargandosi
alla periferia la densita' cala, le componenti connesse si frammentano e la
chiusura transitiva cresce meno del previsto. E' la conferma sperimentale del
limite che era stato dichiarato in premessa al protocollo, e va letta come tale:
la curva misura correttamente il costo su porzioni dense di rete, e sovrastima
quello sulla rete completa.

### Che cosa implica sul dimensionamento del problema

La conclusione operativa e' che il costo di questa base di conoscenza e'
governato dalla chiusura transitiva, e che il dimensionamento non va quindi
ragionato sul numero di fermate ma sulla dimensione delle componenti connesse che
esse formano.

Ne discende una conseguenza concreta per le fasi successive. La relazione
`raggiungibile` serve a rispondere a domande di connettivita' globale, del tipo
"esiste un modo di andare da qui a li'", che il pianificatore pone di rado; la
relazione `trasbordo_ammissibile`, che e' quella effettivamente consumata dal
grafo tempo-espanso della Fase 2, e' molto piu' piccola e cresce linearmente,
attestandosi su cinque trasbordi per fermata a Roma e tre a Torino. La
materializzazione destinata alla Fase 2 puo' percio' escludere la chiusura,
riducendo il costo di un ordine di grandezza, e calcolarla soltanto quando serva
davvero. Il fatto che questa scelta si possa compiere a valle, senza riformulare
le regole ma disattivando un interruttore, e' una conseguenza diretta della
natura dichiarativa della rappresentazione.
