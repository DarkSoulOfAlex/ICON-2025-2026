---
title: "Un pianificatore di viaggi robusto ai ritardi"
lang: it
---

Gruppo di lavoro

- `<Nome Cognome 1>`, `<matricola 1>`, `<username1>@studenti.uniba.it`
- `<Nome Cognome 2>`, `<matricola 2>`, `<username2>@studenti.uniba.it`

`<URL del repository contenente il materiale completo>`

AA `<anno accademico>`

# Introduzione

Chi prende l'autobus non ha lo stesso problema di chi guida. L'automobilista che
parte in ritardo arriva in ritardo della stessa quantita'; chi viaggia sul
trasporto pubblico, se perde una coincidenza per un minuto, non arriva un minuto
dopo ma un quarto d'ora dopo, o mezz'ora, a seconda della frequenza della linea
successiva. Il tempo di viaggio non e' una grandezza continua, e' una scala a
gradini i cui scalini hanno l'altezza degli intervalli fra le corse.

Questo scarto fra il piccolo ritardo e la sua conseguenza e' la ragione per cui
un orario pubblicato non basta a pianificare un viaggio. Gli orari che le aziende
di trasporto distribuiscono nel formato GTFS sono orari **teorici**: dicono
quando una corsa dovrebbe passare, non quando passa. Le stesse aziende
distribuiscono, in un formato parallelo chiamato GTFS Real-Time, gli scostamenti
osservati rispetto a quell'orario, e la distanza fra i due e' abitualmente di
minuti. Ogni pianificatore di viaggi oggi in uso ignora questa distanza:
costruisce l'itinerario che, secondo l'orario teorico, arriva prima. Se quel
itinerario contiene una coincidenza con due minuti di margine su una linea che
accumula regolarmente cinque minuti di ritardo, il pianificatore non ha modo di
saperlo e non ha modo di dirlo.

Il progetto affronta questo problema cambiando la grandezza da ottimizzare.
Invece di minimizzare l'orario di arrivo previsto dall'orario teorico, massimizza
la **probabilita' di arrivare entro un orario dato**, calcolata componendo lungo
la catena delle coincidenze le distribuzioni dei ritardi effettivamente osservati
sul campo. Le due grandezze non sono la stessa cosa riscritta: come il documento
mostrera' con una misura e non con un esempio, l'itinerario che le massimizza
puo' essere diverso, e quale sia il migliore dipende da quanto tempo si ha.

La domanda di ricerca e' percio' questa: **un itinerario scelto massimizzando
P(arrivo <= T) perde meno coincidenze di un itinerario scelto minimizzando
l'orario teorico, a parita' di tempo di viaggio nominale?** Il progetto e'
costruito su due citta' con reti e caratteristiche diverse, Roma e Torino, i cui
dati aperti sono raccolti in continuo da un sistema installato per lo scopo.

# Sommario

Il sistema e' un pianificatore di viaggi che integra quattro moduli, ciascuno
fondato su un formalismo diverso e ciascuno responsabile di una parte del
ragionamento che porta dalla domanda dell'utente all'itinerario proposto.

Il primo modulo e' una **base di conoscenza in Answer Set Programming** che
deriva, a partire dai dati grezzi del formato GTFS, la relazione di trasbordo fra
fermate: quali cambi siano possibili, quanto tempo richiedano come minimo, se
siano accessibili a un passeggero a ridotta mobilita', e quali fermate siano
collegate fra loro da una catena di cambi di lunghezza qualsiasi. Questa
relazione non esiste nei dati di partenza e viene interamente inferita.

Il secondo modulo e' una **ricerca su grafo tempo-espanso** che, data una coppia
origine-destinazione e un orario di partenza, produce l'insieme degli itinerari
non dominati su tre criteri: orario di arrivo, numero di cambi e minuti
trascorsi a piedi. Consuma la relazione di trasbordo prodotta dal primo modulo e
restituisce al terzo un insieme di candidati fra cui scegliere.

Il terzo modulo e' il **ragionamento in condizioni di incertezza** che assegna a
ciascun candidato la probabilita' di arrivare entro la scadenza, componendo le
distribuzioni dei ritardi lungo la successione delle coincidenze e tenendo conto
del fatto che una coincidenza persa non annulla il viaggio ma lo ritarda. E' il
modulo che realizza l'obiettivo del progetto, ed e' quello rispetto al quale
tutti gli altri sono infrastruttura.

Il quarto modulo, in corso di realizzazione, e' l'**apprendimento supervisionato
delle distribuzioni di ritardo** dai dati raccolti sul campo, che sostituira' il
modello provvisorio con cui il terzo modulo e' stato finora collaudato.

I quattro moduli sono deliberatamente eterogenei. La scelta non e' di comodo: il
problema si presta a essere spezzato lungo linee che corrispondono a formalismi
diversi, perche' derivare una relazione da regole con eccezioni, cercare in uno
spazio di stati, comporre distribuzioni di probabilita' e stimare quelle
distribuzioni dai dati sono quattro compiti che nessun singolo formalismo
affronta bene. Ogni modulo espone agli altri un'interfaccia stretta, e ciascuno
e' collaudato e misurato per conto proprio prima di essere composto.

# Elenco argomenti di interesse

Gli argomenti trattati sono quattro, tratti da sezioni diverse del programma e
qui indicati esplicitamente con il riferimento al capitolo corrispondente del
testo di Poole e Mackworth adottato nel corso.

**Argomento 1 — Rappresentazione e ragionamento relazionale (cap. 15) e
rappresentazione della conoscenza proposizionale (cap. 5).** La relazione di
trasbordo fra fermate e' rappresentata da un programma logico in Answer Set
Programming che ne deriva l'esistenza, il tempo minimo, l'accessibilita' e la
chiusura transitiva. Il programma esibisce le proprieta' che distinguono una base
di conoscenza da una interrogazione su una base di dati: eredita' difettibile con
eccezioni, non monotonia, ricorsione e vincoli di integrita' che rifiutano il
modello anziche' filtrare righe. La valutazione misura il costo di istanziazione
al crescere della rete e individua quale regola lo domina.

**Argomento 2 — Ricerca di soluzioni (cap. 3).** La costruzione di un itinerario
e' formulata come ricerca su un grafo tempo-espanso in cui i nodi sono gli eventi
di passaggio e il costo di un arco dipende dall'istante in cui lo si percorre.
Sono impiegati A* con un'euristica geografica di cui si dimostrano ammissibilita'
e consistenza, e una ricerca multi-criterio a etichette che restituisce la
frontiera di Pareto. La valutazione confronta A* con Dijkstra e misura il costo
della rappresentazione dello stato.

**Argomento 3 — Ragionamento e incertezza (cap. 9).** La probabilita' di arrivare
entro una scadenza e' calcolata componendo le distribuzioni di ritardo lungo la
catena delle coincidenze, con una struttura markoviana in cui il ritardo si
propaga dentro una corsa e si azzera attraversando un cambio. La quantita' e'
calcolata in due modi indipendenti, per convoluzione numerica e per
campionamento, e i due sono confrontati fra loro. La valutazione confronta il
criterio probabilistico con tre strategie di riferimento su una griglia di
scadenze.

**Argomento 4 — Apprendimento supervisionato (cap. 7) e apprendimento con
incertezza (cap. 10).** Le distribuzioni di ritardo che il terzo modulo compone
saranno stimate dai dati raccolti sul campo, con una stima condizionata alla
linea, alla fascia oraria e alla posizione lungo la corsa. E' l'argomento
attualmente in corso di realizzazione: la raccolta dei dati e' completa e
funzionante, la stima non e' ancora stata eseguita.

# Sezione Argomento 1 — Rappresentazione e ragionamento relazionale

## Sommario

Un pianificatore di viaggi ha bisogno di sapere, per ogni coppia di fermate, se
un passeggero possa passare dall'una all'altra e quanto tempo gli occorra come
minimo. Questa relazione, che chiameremo di *trasbordo*, e' il fondamento su cui
poggia il resto del sistema: la ricerca degli itinerari la usa per costruire gli
archi di cambio, e il calcolo di probabilita' la usa per stabilire quando una
coincidenza sia da considerarsi persa.

La circostanza che ha determinato la forma di questo modulo e' che la relazione
di trasbordo **non esiste nei dati di partenza**. Lo standard GTFS prevede un
file facoltativo, `transfers.txt`, in cui un'azienda puo' dichiarare quali cambi
siano possibili e con quale tempo minimo. Il contenuto degli archivi di entrambe
le aziende del progetto e' stato verificato: ne' Roma Mobilita' ne' GTT di Torino
lo pubblica. L'archivio di Roma contiene `agency.txt`, `calendar_dates.txt`,
`routes.txt`, `shapes.txt`, `stop_times.txt`, `stops.txt` e `trips.txt`; quello
di Torino aggiunge alcuni file non standard sulle tariffe e sui quadri orari, ma
neppure lui contiene i trasbordi. L'intera relazione va dunque **derivata** da
cio' che i dati contengono davvero: le coordinate delle fermate, la gerarchia che
lega le banchine alle stazioni, l'accessibilita' dichiarata di ciascuna fermata e
l'elenco delle linee che vi transitano. Ogni trasbordo che il pianificatore
utilizza e' una conclusione inferita, non un dato letto.

**I fatti in ingresso.** La base di conoscenza riceve dal GTFS otto predicati: le
fermate fisiche con la loro posizione e la cella dell'indice spaziale a cui
appartengono; il legame fra una banchina e la stazione che la contiene; il valore
di accessibilita' dichiarato secondo la codifica dello standard, dove lo zero
significa "informazione non disponibile" e non "non accessibile"; l'elenco delle
coppie linea-fermata; e, quando esistono, i trasbordi dichiarati dall'azienda e
le segnalazioni contingenti di ascensori fuori servizio.

**Il tempo minimo di trasbordo come eredita' difettibile.** La regola piu'
significativa del modulo stabilisce quanto tempo occorra come minimo per un
cambio. Il valore non e' memorizzato da nessuna parte e non e' unico: dipende dal
tipo di trasbordo, e le fonti di informazione hanno una gerarchia di
autorevolezza. Se l'azienda ha dichiarato un tempo per quella coppia vale quello;
altrimenti, se le due fermate sono banchine della stessa stazione, vale il tempo
di percorrenza interno, piu' lungo del semplice cammino perche' comprende
sottopassi, scale e tornelli; in assenza di entrambe le condizioni vale il tempo
di cammino all'aperto piu' un margine.

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

La priorita' e' interamente affidata ai tre `not`: una regola di livello
inferiore si applica soltanto quando nessuna regola piu' specifica ha gia'
concluso. E' la struttura dell'eredita' difettibile, quella per cui un default
vale finche' non interviene un'eccezione piu' precisa. Un'interrogazione
relazionale puo' riprodurre il risultato, ma solo scrivendo la gerarchia delle
priorita' dentro la query, tipicamente come catena di `COALESCE` o sequenza
ordinata di `LEFT JOIN`. La differenza non e' di eleganza ma di collocazione
della conoscenza: in quel caso la gerarchia vive nel codice dell'interrogazione, e
aggiungere un livello significa riscrivere la query; qui la gerarchia e'
dichiarata nella base di conoscenza, e aggiungere un livello significa aggiungere
una regola senza toccare le altre. Il collaudo verifica esattamente la parte non
riducibile: dichiarando un tempo per la sola direzione da `A1` verso `A2`, quella
direzione assume il valore dichiarato mentre la direzione opposta, non
dichiarata, resta governata dalla regola della stazione. La sovrascrittura e'
puntuale, come dev'essere un default.

**L'accessibilita' come conoscenza non monotona.** La seconda regola riguarda
l'accessibilita' di un trasbordo per un passeggero a ridotta mobilita'.

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

La proprieta' rilevante e' la **non monotonia**: aggiungere un fatto *rimuove*
conclusioni gia' derivate. Dichiarando che l'ascensore della fermata `A1` e'
fuori servizio, quattro trasbordi che risultavano accessibili smettono di
esserlo, e nessuno ne prende il posto. Nessuna interrogazione relazionale
positiva ha questo comportamento, per una ragione strutturale e non
implementativa: in algebra relazionale l'aggiunta di tuple non puo' mai ridurre
il risultato di una query positiva. Il test confronta l'insieme delle conclusioni
prima e dopo, e controlla non solo che quattro conclusioni siano sparite ma anche
che nessuna sia comparsa. Va notato che le eccezioni non sono tutte dichiarate:
la prima e' *derivata*, perche' un trasbordo a piedi diventa inaccessibile in
forza della propria distanza senza che nessuno debba annotarlo. Anche
l'antecedente `fermata_accessibile` e' a sua volta un'eredita' con default,
perche' lo standard prescrive che il valore zero su una banchina significhi
"eredita dalla stazione".

**La raggiungibilita' come chiusura transitiva.** La terza regola e' ricorsiva.

```prolog
raggiungibile(F, F) :- fermata(F).

raggiungibile(F1, F3) :-
    raggiungibile(F1, F2),
    trasbordo_ammissibile(F2, F3, _).
```

Due fermate sono collegate se esiste una catena di trasbordi di lunghezza
qualsiasi. La ricorsione non e' un artificio: il numero di cambi necessari a
collegare due punti di una rete non e' noto in anticipo e dipende dalla
topologia. Il collaudo verifica la parte che solo la ricorsione puo' produrre,
disponendo quattro fermate in fila a duecento metri l'una dall'altra, sotto la
soglia di duecentocinquanta metri per le coppie adiacenti e sopra per quelle a un
posto di distanza: nessun trasbordo diretto collega la prima alla terza, eppure
la chiusura le collega, e collega anche la prima alla quarta. Una variante della
stessa regola calcola la chiusura sui soli trasbordi accessibili; non e' una
duplicazione ma un'altra domanda, perche' un percorso esistente per un passeggero
qualsiasi puo' non esistere per un passeggero in sedia a rotelle.

**I vincoli di integrita'.** Il quarto elemento e' di natura diversa dai
precedenti.

```prolog
:- fermata(F),
   #count { F2 : trasbordo_a_piedi(F, F2) } > grado_massimo_plausibile.

:- trasbordo_ammissibile(F1, F2, T), tempo_piedi(F1, F2, TP), T < TP.
```

Un vincolo di integrita' non filtra righe: **rifiuta il modello**. Se una sola
coppia di fermate lo viola, il programma non ha alcuna risposta, e non una
risposta piu' corta. E' una condizione sull'intera interpretazione, di natura
diversa da qualunque clausola `WHERE`, e garantisce che cio' che esce dalla base
di conoscenza sia coerente per costruzione anziche' per controllo a valle. I
quattro vincoli presenti sono stati scelti perche' possono davvero scattare, e
ciascuno corrisponde a un difetto documentato dei dati aperti: il primo dei due
riportati intercetta le fermate prive di coordinate, che nei feed reali finiscono
tutte nello stesso punto e formerebbero un nodo di scambio inesistente ma enorme;
il secondo intercetta i tempi di trasbordo dichiarati piu' brevi del tempo
materialmente necessario a percorrere la distanza a piedi, che renderebbero il
pianificatore sistematicamente troppo fiducioso.

**La negazione e' stratificata.** La negazione per fallimento compare in cinque
punti: nelle due regole di sovrascrittura del tempo minimo, nella regola
dell'accessibilita' e nella definizione di trasbordo utile, che chiede
l'esistenza di una linea servita dalla fermata di arrivo e non da quella di
partenza. In tutti i casi la verifica e' diretta. `dichiarato` e' un fatto in
ingresso e non dipende da nulla; `stessa_stazione` dipende soltanto da
`in_stazione`, anch'esso in ingresso; `eccezione_accessibilita` dipende da
`tempo_piedi`, da `trasbordo_ammissibile` e dal fatto contingente sugli
ascensori, ma non da `accessibile`; `serve` e' un fatto in ingresso. Nessuno dei
predicati che compaiono negati dipende, nemmeno per via indiretta, dal predicato
che lo nega: il grafo delle dipendenze non contiene alcun ciclo che attraversi
una negazione, e il programma ammette percio' un unico modello stabile ben
definito. E' questa proprieta' a garantire che la base di conoscenza abbia una
risposta sola e non un insieme di risposte alternative fra cui scegliere. L'unica
ricorsione presente, quella della raggiungibilita', e' puramente positiva e non
interferisce con la stratificazione.

**L'indice spaziale, e perche' non altera la semantica.** La regola del trasbordo
a piedi confronta coppie di fermate. Confrontarle tutte significa istanziare un
numero di atomi quadratico: sulle 8.301 fermate di Roma sono circa 69 milioni di
coppie, e il grounding non termina in tempo utile. Ogni fermata riceve percio' la
cella di una griglia regolare, calcolata dalle sue coordinate, e la regola
confronta soltanto le fermate nella stessa cella o in una delle otto adiacenti.
Va dichiarato che cosa questo accorgimento non e': non e' clustering, perche' non
c'e' nulla di appreso, nessun centroide, nessuna funzione obiettivo e nessuna
scelta dipendente dai dati; e' un'indicizzazione deterministica sulle coordinate,
l'equivalente spaziale di un indice su una colonna. Soprattutto **non altera
l'insieme delle conclusioni**, e la ragione e' geometrica: il lato della cella e'
posto uguale alla soglia di cammino, quindi due fermate che distino meno della
soglia non possono cadere in celle non adiacenti e nessun trasbordo puo' sfuggire
al confronto. Poiche' un'argomentazione geometrica puo' sempre nascondere un
errore, la proprieta' e' anche verificata sperimentalmente, come riportato nella
valutazione.

**I dati di calendario, e una circostanza che ha cambiato il modulo.** La base di
conoscenza lavora sulla topologia della rete e non sul calendario, ma il
calendario e' un prerequisito di tutto il resto. Lo standard GTFS prevede due
modi complementari di dichiarare quando una corsa circoli: `calendar.txt` esprime
una regola settimanale con un periodo di validita', `calendar_dates.txt` esprime
eccezioni puntuali, additive o sottrattive. Lo standard richiede che almeno uno
dei due sia presente, non entrambi. Le due aziende usano i regimi opposti: Torino
pubblica `calendar.txt` con 1.106 servizi e `calendar_dates.txt` con 34.758
eccezioni, cioe' la forma canonica; Roma **non pubblica affatto** `calendar.txt`,
e ogni singolo giorno di servizio e' elencato come eccezione additiva nelle 4.707
righe di `calendar_dates.txt`. Entrambe le scelte sono conformi. Un modulo
scritto sull'assunzione implicita che `calendar.txt` esista funzionerebbe su
Torino e restituirebbe zero corse attive su Roma, senza sollevare alcuna
eccezione e senza somigliare in alcun modo a un errore. Avere due citta' con
regimi opposti ha trasformato una possibile fonte di errore silenzioso in un caso
di prova.

Alla stessa categoria appartiene il trattamento degli orari oltre la mezzanotte.
Il GTFS ammette e usa regolarmente valori come `25:30:00`, che indicano l'una e
mezza di notte del giorno successivo ma appartengono al giorno di servizio
precedente. Riportarli sotto le ventiquattro ore, che e' la normalizzazione
istintiva, sposta silenziosamente tutte le corse notturne sul giorno sbagliato.

## Strumenti utilizzati

La base di conoscenza e' scritta in Answer Set Programming [1] e valutata con il
sistema **clingo** [2], che ne esegue il grounding e la risoluzione. Il
formalismo e' impiegato nella sua forma standard: regole normali con negazione
per fallimento, ricorsione, vincoli di integrita' e aggregati `#count`; la
semantica dei modelli stabili e le condizioni di stratificazione sono quelle
usuali, discusse nel testo del corso [3]. La lettura degli archivi GTFS [4] e la
preparazione dei fatti sono realizzate con **pandas** [5]; il collegamento fra il
programma logico e Python usa l'API Python di clingo.

Il solo elemento non riconducibile a un modello noto e' l'argomentazione
geometrica sull'indice spaziale esposta nel sommario, con la relativa verifica
sperimentale riportata nella valutazione.

## Decisioni di Progetto

**L'indice spaziale a griglia.** Il lato della cella e' posto uguale alla soglia
di cammino, 250 metri, e la regola confronta ogni fermata con quelle della
propria cella e delle otto adiacenti. L'alternativa scartata era il confronto
esaustivo di tutte le coppie, che su Roma non termina in tempo utile. La scelta
del lato non e' libera: un lato inferiore alla soglia spezzerebbe coppie che
devono essere confrontate, e la semantica cambierebbe. Il programma espone un
interruttore, `con_indice`, che sostituisce la regola indicizzata con quella
esaustiva, e la sua esistenza e' cio' che rende possibile la verifica
sperimentale.

**Identificativi interi e coordinate in metri.** Gli identificativi testuali
delle fermate diventano numeri interi e le coordinate geografiche diventano metri
interi su una proiezione piana locale centrata sul baricentro delle fermate della
citta'. Entrambe le trasformazioni avvengono prima che i fatti raggiungano il
programma logico, ed e' opportuno dichiarare perche' non spostino conoscenza
fuori dalla base: la corrispondenza e' biunivoca e viene conservata, il risultato
si ritraduce esattamente, e il guadagno e' soltanto di velocita' nel grounding.
Il cambio di unita' e' l'analogo del conservare gli orari in secondi anziche'
nella forma `HH:MM:SS`. La regola che stabilisce *quali* coppie costituiscano un
trasbordo resta interamente dentro il programma logico.

**Il tempo di cammino e' discretizzato in bande.** Il tempo a piedi fra due
fermate e' assegnato in quattro bande anziche' calcolato con continuita'. La
motivazione e' che un tempo di trasbordo ha senso al mezzo minuto e non al metro,
e che la discretizzazione riduce drasticamente il numero di valori distinti da
istanziare. Resta un'approssimazione, ed e' dichiarata come tale fra i limiti
nelle conclusioni.

**I vincoli di integrita' sono scelti perche' possano essere violati.** Alcuni
vincoli inizialmente formulati sono stati scartati, per esempio il divieto per
una fermata di essere trasbordo di se stessa, perche' la costruzione delle regole
li rende impossibili per definizione: un vincolo che non puo' mai essere violato
non e' logica, e' un commento travestito da logica. I quattro rimasti sono
collaudati costruendo il dato che li viola, verificando che il programma diventi
insoddisfacibile e che torni soddisfacibile disattivando i soli vincoli.

**Il campionamento per prossimita' dal baricentro geometrico.** Le sottoreti su
cui si misura la complessita' sono ottenute prendendo le N fermate piu' vicine a
un centro fisso, che non e' stato scelto a mano ma derivato dai dati come la
fermata piu' vicina al baricentro geometrico di tutte le fermate della citta':
per Roma la 70841, S. SABA/AVENTINO, per Torino la 962, Fermata 1873 - PUGLIA
C.3. L'alternativa era il campionamento casuale, ed e' stata scartata perche'
cinquanta fermate estratte a sorte fra le ottomila di Roma finirebbero sparse a
chilometri l'una dall'altra e non genererebbero quasi nessun trasbordo a piedi:
la curva misurerebbe il costo di un problema che non somiglia a quello vero. Il
campionamento per prossimita' conserva la densita' reale della rete ed e' inoltre
monotono, nel senso che un campione piu' grande contiene quello piu' piccolo,
proprieta' senza la quale i punti della curva non sarebbero confrontabili fra
loro. Il prezzo va dichiarato: i risultati valgono per una porzione connessa e
densa di rete e non sono estrapolabili a un campione sparso di pari cardinalita'.

**La materializzazione per la ricerca esclude la chiusura transitiva.** La
relazione `raggiungibile` risponde a domande di connettivita' globale che il
pianificatore pone di rado, mentre `trasbordo_ammissibile`, quella effettivamente
consumata dal grafo tempo-espanso, e' molto piu' piccola e cresce linearmente. La
materializzazione destinata alla ricerca esclude percio' la chiusura, riducendo il
costo di un ordine di grandezza, e la calcola soltanto quando serva davvero. Che
la scelta si possa compiere a valle, disattivando l'interruttore `con_chiusura`
invece di riformulare le regole, e' una conseguenza diretta della natura
dichiarativa della rappresentazione.

**I parametri numerici.** La soglia di cammino e' di 250 metri, il tempo di
percorrenza interno a una stazione di 180 secondi, il margine aggiunto al cammino
all'aperto di 60 secondi, il tempo massimo di cammino per un passeggero in sedia
a rotelle di 300 secondi, e il grado massimo plausibile di trasbordi a piedi per
fermata di 40. Sono valori di modello, dichiarati come costanti `#const` in testa
al programma perche' siano modificabili senza toccare le regole.

## Valutazione

La misura risponde a una domanda pratica: fino a che dimensione di rete questa
base di conoscenza resta utilizzabile, e quale delle sue regole ne determina il
costo. Sono state misurate cinque dimensioni crescenti, da cinquanta a duemila
fermate, su entrambe le citta', con tre ripetizioni indipendenti per ogni
combinazione. Per ciascuna esecuzione si registrano il numero di atomi generati,
il tempo di grounding e il tempo di solving, tenuti separati perche' misurano due
cose diverse: il primo e' il costo di istanziare le regole sui dati, il secondo
quello di risolvere il programma proposizionale che ne risulta.

Una precisazione sulle deviazioni standard riportate. Il numero di atomi e quello
di regole sono grandezze **deterministiche**: a parita' di dati e di programma
clingo genera sempre la stessa istanziazione, la loro deviazione standard sulle
tre ripetizioni e' nulla per costruzione, e riportarla serve unicamente a
documentare che le ripetizioni sono state eseguite. La variabilita' reale sta nei
tempi, che dipendono dal carico della macchina.

Tabella 1 — Roma, media e deviazione standard su tre ripetizioni.

| Fermate | Atomi | Grounding (s) | Solving (s) | Trasbordi derivati |
| ---: | ---: | ---: | ---: | ---: |
| 50 | 7.334 ± 0 | 0,012 ± 0,001 | 0,0006 ± 0,0001 | 436 |
| 150 | 24.463 ± 0 | 0,048 ± 0,006 | 0,0015 ± 0,0001 | 1.096 |
| 400 | 70.612 ± 0 | 0,160 ± 0,048 | 0,0039 ± 0,0003 | 2.738 |
| 1000 | 724.410 ± 0 | 1,692 ± 0,139 | 0,0150 ± 0,0003 | 7.232 |
| 2000 | 2.358.444 ± 0 | 5,707 ± 0,753 | 0,0380 ± 0,0008 | 13.938 |

Tabella 2 — Torino, media e deviazione standard su tre ripetizioni.

| Fermate | Atomi | Grounding (s) | Solving (s) | Trasbordi derivati |
| ---: | ---: | ---: | ---: | ---: |
| 50 | 3.141 ± 0 | 0,005 ± 0,000 | 0,0003 ± 0,0000 | 164 |
| 150 | 13.862 ± 0 | 0,021 ± 0,000 | 0,0010 ± 0,0000 | 688 |
| 400 | 34.018 ± 0 | 0,052 ± 0,006 | 0,0024 ± 0,0002 | 1.616 |
| 1000 | 136.729 ± 0 | 0,245 ± 0,012 | 0,0072 ± 0,0008 | 4.498 |
| 2000 | 438.374 ± 0 | 0,910 ± 0,042 | 0,0190 ± 0,0029 | 9.542 |

![**Figura 1.** Costo della base di conoscenza al crescere del numero di fermate, in scala doppio logaritmica, per le due citta'. I pannelli (a), (b) e (c) riportano rispettivamente gli atomi generati, il tempo di grounding e il tempo di solving, come media su tre ripetizioni indipendenti con barre di deviazione standard; sugli atomi le barre sono nulle per costruzione, trattandosi di una grandezza deterministica. Il pannello (d) confronta la variante con indice spaziale, a linea continua, con quella che confronta tutte le coppie di fermate, a linea tratteggiata, eseguita solo fino a quattrocento fermate perche' oltre quella soglia il suo costo quadratico non aggiunge informazione. Dati grezzi in `results/complessita_kb.csv`.](../results/complessita_kb.png)

**Da dove nasce la crescita.** La pendenza delle curve in scala doppio
logaritmica e' l'esponente di crescita. Su tutto l'intervallo misurato gli atomi
crescono come `n^1,59` a Roma e come `n^1,30` a Torino, ma il dato interessante e'
che la pendenza **aumenta con la dimensione**: sull'ultimo raddoppio, da mille a
duemila fermate, entrambe le citta' si assestano attorno a `n^1,70`. Non e' una
crescita polinomiale di ordine fisso, e' una crescita che accelera. Disattivando
la sola ricorsione e rieseguendo la stessa istanza si ottiene l'attribuzione
diretta.

Tabella 3 — Quota di atomi generata dalla chiusura transitiva.

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
sottorete si allarga le fermate finiscono quasi tutte nella stessa componente,
mentre tutte le altre regole restano lineari nel numero di coppie candidate, che
l'indice spaziale mantiene proporzionale al numero di fermate.

Il tempo di solving, due ordini di grandezza inferiore a quello di grounding,
conferma la lettura. Il programma, una volta istanziato, e' sostanzialmente
deterministico: non ci sono scelte da compiere, perche' la negazione e'
stratificata e la ricorsione e' positiva, quindi il modello stabile e' unico e il
risolutore non deve esplorare alcuno spazio di ricerca. Il costo di questa base
di conoscenza e' interamente un costo di istanziazione, non di ricerca.

**Perche' le due reti si comportano in modo diverso.** A parita' di numero di
fermate Roma costa costantemente piu' di Torino, e il divario si allarga: a
cinquanta fermate il rapporto fra gli atomi e' 2,3, a duemila e' 5,4. La
differenza non sta nelle dimensioni assolute delle due reti, che sono
confrontabili, 8.301 fermate contro 7.073, ma nella **densita' locale**. Nella
sottorete campionata attorno al centro, Roma deriva stabilmente attorno a sette
trasbordi per fermata, Torino attorno a quattro e mezzo. Un rapporto di densita'
di circa 1,5 diventa un rapporto di 5,4 sul numero di atomi proprio per via della
chiusura transitiva: una componente connessa piu' densa e' anche piu' grande, e
il costo della chiusura cresce con il quadrato della sua dimensione. Nella
Tabella 3 si vede che Torino raggiunge a duemila fermate la quota di atomi
ricorsivi che Roma aveva gia' superato a mille: la stessa curva, traslata. E' il
risultato che giustifica l'aver misurato due citta' anziche' una, perche' con una
sola rete non si sarebbe potuto distinguere fra un costo intrinseco della
formulazione e un costo dipendente dalla topologia.

**Il costo dell'indice spaziale, e la verifica della sua semantica.** Il pannello
(d) della Figura 1 confronta la formulazione indicizzata con quella esaustiva.

Tabella 4 — Atomi generati con e senza indice spaziale.

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
69 milioni di coppie, il che spiega perche' non sia praticabile a piena scala.

La verifica che conta non e' pero' quella sul costo ma quella sulla semantica. A
ogni dimensione in cui entrambe le varianti sono state eseguite, l'insieme dei
trasbordi derivati e' risultato **identico**: stessi trasbordi, stessi tempi
minimi, stessi attributi di accessibilita' e di utilita'. L'indice restringe
l'ordine di istanziazione, non l'insieme delle conclusioni, e l'argomentazione
geometrica trova qui la sua conferma sperimentale.

**La rete intera.** La curva si ferma a duemila fermate perche' oltre quella
soglia il campionamento per prossimita' comincia a coincidere con la rete intera
e il confronto fra dimensioni perde significato. La rete intera e' pero' stata
eseguita, e i suoi numeri sono una misura e non un'estrapolazione.

Tabella 5 — Esecuzione sull'intera rete di ciascuna citta'.

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

L'intera base di conoscenza di Roma si istanzia in undici secondi e mezzo, costo
pienamente sostenibile per un'elaborazione da eseguire una volta al giorno,
quando l'orario statico cambia. Il numero di atomi sulla rete intera di Roma, 4,5
milioni, e' inferiore ai 26 milioni che l'esponente `n^1,70` misurato sull'ultimo
raddoppio avrebbe fatto prevedere: la ragione e' che il campionamento per
prossimita' seleziona la porzione **piu' densa** della rete, quella centrale, e
allargandosi alla periferia la densita' cala, le componenti connesse si
frammentano e la chiusura transitiva cresce meno del previsto. E' la conferma
sperimentale del limite dichiarato fra le decisioni di progetto: la curva misura
correttamente il costo su porzioni dense di rete, e sovrastima quello sulla rete
completa.

**Un risultato negativo sulla poverta' dei dati.** Delle 8.301 fermate di Roma,
**tutte** dichiarano `wheelchair_boarding` uguale a zero, che nella codifica
dello standard significa "informazione non disponibile"; lo stesso vale per il
campo corrispondente su tutte le 179.177 corse. Inoltre **nessuna** fermata di
Roma dichiara una `parent_station`: la gerarchia delle stazioni, in
quell'archivio, non esiste. Torino si comporta diversamente, con 2.722 fermate
dichiarate accessibili, 1.075 esplicitamente non accessibili e 3.276 senza
informazione, e 47.023 corse su 60.580 dichiarate accessibili; ma anche li'
soltanto due fermate su 7.073 appartengono a una stazione.

Le conseguenze si leggono nella Tabella 5. Su Roma la regola dell'accessibilita'
deriva **zero** trasbordi accessibili: non perche' sia sbagliata, ma perche' il
suo antecedente non e' mai soddisfatto, dal momento che nessuna fermata risulta
accessibile e non esiste alcuna stazione da cui ereditare il dato. Su Torino la
stessa regola funziona e deriva 7.382 trasbordi accessibili su 21.130, poco piu'
di un terzo. Quanto alla gerarchia dei tempi minimi, il suo primo livello non
riceve alcun fatto su nessuna delle due citta', perche' nessuna pubblica
`transfers.txt`, e il secondo livello si applica a due sole fermate in tutto il
progetto: su questi dati l'eredita' difettibile collassa quasi ovunque sul terzo
livello, quello del cammino all'aperto.

Sarebbe disonesto presentare come funzionante una gerarchia a tre livelli di cui,
sul campo, ne opera stabilmente uno solo. Va detto con precisione che cosa questo
dimostri e che cosa no. Dimostra che la formulazione e' piu' generale dei dati
disponibili, il che e' una scelta deliberata: la base di conoscenza e' scritta
per il formato GTFS e non per due archivi particolari, e su un'azienda che
pubblichi `transfers.txt` e una gerarchia di stazioni i primi due livelli
entrerebbero in funzione senza modificare una riga. Non dimostra che quei livelli
siano utili in pratica su Roma e Torino, perche' su Roma e Torino non lo sono. Il
loro collaudo e' percio' affidato a dati costruiti. Ne discende inoltre che la
distinzione fra `raggiungibile` e `raggiungibile_accessibile`, sul piano della
rappresentazione una delle parti piu' interessanti, e' misurabile soltanto su
Torino: ogni risultato sull'accessibilita' va riferito a Torino e non alla media
delle due citta'.

# Sezione Argomento 2 — Ricerca di soluzioni

## Sommario

La domanda a cui il pianificatore deve rispondere non e' "qual e' il percorso
piu' corto fra A e B" ma "partendo da A alle otto, qual e' il primo momento in
cui posso essere in B". La differenza non e' di formulazione: nel trasporto
pubblico il costo di un arco dipende dall'istante in cui lo si percorre, perche'
fra una corsa e la successiva si aspetta, e un cammino minimo su un grafo statico
non ha modo di rappresentarlo.

La rappresentazione adottata e' il **grafo tempo-espanso**, in cui i nodi non
sono le fermate ma gli **eventi**: ogni passaggio di una corsa a una fermata, con
il suo orario. Muoversi nel grafo significa muoversi nel tempo oltre che nello
spazio, e attendere a una fermata diventa semplicemente non fare nulla mentre il
tempo passa. Gli archi di cambio fra fermate diverse sono quelli derivati dalla
base di conoscenza descritta nell'argomento precedente, che stabilisce quali
trasbordi esistano e quanto tempo richiedano come minimo. Il costo che si
minimizza e' l'**orario di arrivo**, non la durata del viaggio: partire piu'
tardi non e' peggio se si arriva prima, mentre minimizzando la durata si
preferirebbe un viaggio di venti minuti che parte fra due ore a uno di
venticinque che parte adesso, il che non e' quello che chiede chi sta alla
fermata.

**Lo stato, e perche' la terna non basta.** Lo stato della ricerca e' la terna
`(fermata, istante, cambi effettuati)`, ma la terna da sola non e' sufficiente a
contare correttamente i cambi. Stando a una fermata a un dato istante, "restare a
bordo" e "salire di nuovo" sono situazioni indistinguibili se non si sa su quale
corsa ci si trovi: un viaggiatore che percorre dieci fermate senza mai scendere
passerebbe per dieci stati successivi, ciascuno dei quali sembrerebbe una salita,
e la ricerca gli attribuirebbe dieci cambi. Il conteggio dei cambi, che e' uno
dei tre criteri della ricerca multi-criterio, sarebbe sistematicamente sbagliato
senza che nulla lo segnali. Lo stato si sdoppia percio' in due forme che
condividono la terna come parte osservabile. **A terra** si e' a una fermata, a
un certo istante, dopo un certo numero di cambi, e da li' si puo' salire su una
corsa, trasbordare verso una fermata vicina o camminare. **A bordo** si e' su una
corsa specifica, appena arrivati a un suo passaggio, e da li' si puo' proseguire
senza cambiare oppure scendere. L'identita' della corsa e' l'unica informazione
aggiuntiva rispetto alla terna, ed e' quella che rende il conteggio corretto per
costruzione anziche' per convenzione. Il cambio si conta alla **salita** e non
alla discesa: scendere a destinazione costerebbe altrimenti un cambio che il
viaggiatore non percepisce, e due itinerari identici tranne che per la fermata
finale risulterebbero diversi su un criterio.

**L'euristica geografica, con la dimostrazione della sua ammissibilita'.** La
ricerca mono-criterio usa A* con l'euristica che divide la distanza in linea
d'aria fra la fermata corrente e la destinazione per la velocita' massima
presente nella rete.

Sia `n` uno stato la cui fermata dista `d` metri in linea d'aria dalla
destinazione, e sia `V` la velocita' massima fra due fermate consecutive presente
nell'orario. Ogni itinerario che porti da `n` alla destinazione e' una
successione finita di spostamenti fra fermate. La somma delle loro lunghezze non
puo' essere inferiore a `d`, perche' il segmento e' il cammino piu' breve fra due
punti del piano e la spezzata che li congiunge e' almeno altrettanto lunga.
Ciascuno di quegli spostamenti impiega almeno la propria lunghezza divisa `V`,
perche' `V` e' per costruzione un limite superiore alla velocita' di ogni
spostamento della rete. Il tempo residuo reale e' percio' almeno `d / V`, che e'
il valore restituito dall'euristica. Le attese alle fermate e i tempi minimi di
trasbordo si sommano a quel tempo e possono solo aumentarlo, quindi non intaccano
il limite. L'euristica non sovrastima mai il costo residuo: e' ammissibile, e A*
restituisce percio' l'ottimo.

L'euristica e' inoltre **consistente**, perche' e' della forma `d(x)/V` con `d`
distanza euclidea, che soddisfa la disuguaglianza triangolare: per ogni arco da
`x` a `y` di costo `c` vale `h(x) <= c + h(y)`. Con un'euristica consistente ogni
stato viene estratto dalla coda gia' con il suo costo definitivo e non e'
necessario riaprirlo. La dimostrazione e' verificata anche per campionamento: un
test estrae stati a caso, calcola il costo residuo reale con una ricerca
esaustiva e controlla che l'euristica non lo superi mai. Un'euristica non
ammissibile non solleverebbe alcun errore e non rallenterebbe nulla:
restituirebbe semplicemente itinerari peggiori, in silenzio.

**La frontiera di Pareto, e perche' non esiste un itinerario ottimo.** La ricerca
multi-criterio valuta ogni itinerario su tre grandezze: orario di arrivo, numero
di cambi e minuti trascorsi a piedi. Non esiste un modo oggettivo di ridurle a
una sola, perche' cio' richiederebbe di decidere quanto valga un cambio espresso
in minuti, e la risposta dipende da chi viaggia: chi porta una valigia, chi ha
poco tempo e chi ha difficolta' motorie darebbero tre risposte diverse. Un
itinerario che arriva cinque minuti prima ma con un cambio in piu' non e'
migliore ne' peggiore, e' un altro compromesso. Cio' che si puo' dire in modo
oggettivo e' quali itinerari siano **dominati**: un itinerario e' dominato se ne
esiste un altro non peggiore su tutti e tre i criteri e strettamente migliore su
almeno uno. Gli itinerari non dominati formano la frontiera di Pareto, e la
ricerca restituisce quella, lasciando la scelta finale a chi viaggia. La
disuguaglianza stretta su almeno un criterio non e' un dettaglio formale: senza
di essa due itinerari identici si dominerebbero a vicenda e la frontiera si
svuoterebbe.

**Il modello dei ritardi non entra in questa fase.** Va detto esplicitamente,
perche' e' una scelta di perimetro e non un'omissione: la ricerca descritta qui
lavora sull'orario **programmato** e non usa in alcun modo i ritardi. La
robustezza probabilistica e' oggetto dell'argomento successivo, che consuma la
frontiera di Pareto prodotta da questo come proprio insieme di candidati.

## Strumenti utilizzati

La ricerca mono-criterio impiega **A\*** e, come termine di paragone senza
euristica, l'algoritmo di **Dijkstra**; entrambi sono usati nella loro forma
standard e sono descritti nel testo del corso [3]. La ricerca multi-criterio e'
una ricerca a etichette con potatura per dominanza, nella forma abituale per i
problemi di cammino multi-obiettivo [6]. La coda di priorita' e' quella della
libreria standard di Python, `heapq`; il calcolo delle distanze e la
manipolazione delle strutture del grafo usano **numpy** [7].

Non vi sono algoritmi originali in questo modulo. Sono invece originali due
argomentazioni riportate altrove in questa sezione: la dimostrazione di
ammissibilita' e consistenza dell'euristica geografica, esposta nel sommario, e
la relazione di dominanza fra stati a terra su cui si fonda la scelta della
chiave di stato, esposta fra le decisioni di progetto.

## Decisioni di Progetto

**Il grafo copre una finestra temporale, non la giornata.** Il grafo parte
dall'orario di partenza richiesto e dura un orizzonte prefissato, per
impostazione predefinita due ore. La ragione e' di dimensione: l'orario di Roma
contiene 5,6 milioni di passaggi al giorno, e il grafo dell'intera giornata non
e' un oggetto che si costruisca per rispondere a una singola interrogazione. La
finestra non e' pero' solo un espediente, perche' e' anche cio' che una
interrogazione usa davvero: nessuno accetta di attendere quattro ore alla
fermata. Il prezzo va comunque dichiarato come limitazione dei risultati e non
come nota implementativa: **la ricerca trova l'ottimo dentro la finestra**, e un
itinerario che richiedesse di attendere oltre l'orizzonte non verrebbe trovato
affatto. La valutazione riporta su quante coppie origine-destinazione la finestra
di due ore si sia rivelata sufficiente.

**La chiave di stato a terra non contiene l'istante.** E' la decisione che ha
avuto l'effetto piu' grande sul costo della ricerca, e vale la pena riportare il
passaggio intermedio perche' il risultato finale da solo nasconderebbe che
l'identificazione degli stati non era affatto ovvia. La prima implementazione
seguiva la lettura letterale dello stato e trattava come distinti due arrivi alla
stessa fermata in istanti diversi. E' corretta, ma su una finestra di due ore
produce centinaia di stati per ogni fermata, uno per ogni orario a cui vi si
possa arrivare.

L'osservazione che risolve il problema e' una relazione di dominanza: trovarsi
alla stessa fermata, con lo stesso numero di cambi, ma **prima**, e' sempre
almeno altrettanto buono. Ogni prosecuzione disponibile allo stato piu' tardivo
e' disponibile anche a quello piu' precoce, perche' le azioni possibili da una
fermata dipendono dall'istante solo attraverso il vincolo di non poter salire su
una corsa gia' partita, e un istante anteriore rilassa quel vincolo senza
irrigidirne altri. Identificando percio' uno stato a terra con la sola coppia
`(fermata, cambi)` e conservando l'istante di arrivo piu' precoce, gli stati con
istante posteriore spariscono senza che alcuna soluzione vada perduta. Non e'
un'approssimazione ma l'eliminazione di stati dimostrabilmente dominati. Le due
formulazioni convivono nel codice, perche' altrimenti il confronto non sarebbe
riproducibile: il parametro `istante_nella_chiave` riattiva quella storica.

**L'euristica usa il massimo vero delle velocita', difetti dell'orario
compresi.** L'ammissibilita' obbliga a scegliere come `V` il massimo effettivo
delle velocita' fra fermate consecutive presenti nell'orario, e non un valore
fisicamente plausibile: il limite deve valere per il grafo che si sta cercando,
non per la fisica, perche' se l'orario dichiara un movimento, quel movimento nel
grafo esiste. La conseguenza e' misurata e discussa nella valutazione, ed e'
sfavorevole.

**Una variante non ammissibile, come confronto e solo come confronto.** Per
quantificare quanto costi l'ammissibilita' e' stata implementata anche una
variante con `V` pari al 99,9-esimo percentile delle velocita' invece che al
massimo. Quella variante **non e' ammissibile** e A* non garantisce piu'
l'ottimo. E' dichiarata come tale ovunque compaia: nel codice, nella colonna
`tipo_velocita` di `results/ricerca_astar.csv`, che marca ogni riga con il valore
di `V` usato e con la sua natura, e nella didascalia della figura. **La variante
ammissibile resta l'unica che produce risultati ufficiali del progetto.**

**Il tetto sul numero di cambi.** La ricerca impone un massimo di quattro cambi,
che e' un vincolo di realismo prima che di costo: un itinerario con sei cambi non
verrebbe scelto da nessuno. Il tetto ha pero' un'interazione non ovvia con la
rappresentazione dello stato, misurata nella valutazione.

## Valutazione

Il confronto e' stato eseguito su cinquanta coppie origine-destinazione per
citta', estratte con un seme dichiarato fra le fermate effettivamente servite
nella finestra, con partenza alle 08:00 e orizzonte di 120 minuti. Le varianti
condividono lo stesso codice e differiscono solo per l'euristica o per la chiave
di stato, cosi' che il confronto isoli l'elemento in esame.

**Il costo del grafo.**

Tabella 6 — Dimensione del grafo tempo-espanso al crescere della finestra,
partenza alle 08:00. Media su tre costruzioni indipendenti; eventi e archi sono
grandezze deterministiche, quindi la loro deviazione standard e' nulla per
costruzione e la variabilita' sta nel solo tempo di costruzione.

| Finestra | Roma: eventi | Roma: archi | Roma: MB | Torino: eventi | Torino: archi | Torino: MB |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 15 min | 120.725 | 291.306 | 7,3 | 50.548 | 125.728 | 3,4 |
| 30 min | 134.120 | 331.149 | 8,0 | 55.716 | 141.550 | 3,6 |
| 60 min | 160.611 | 410.436 | 9,3 | 65.455 | 171.932 | 4,2 |
| 120 min | 212.788 | 566.576 | 11,9 | 83.121 | 227.023 | 5,1 |
| 240 min | 315.000 | 871.117 | 17,0 | 118.263 | 330.877 | 6,8 |

La crescita e' **sublineare** nella durata della finestra: quadruplicando
l'orizzonte da sessanta a duecentoquaranta minuti gli archi di Roma poco piu' che
raddoppiano. La ragione e' che una parte cospicua del grafo non dipende dalla
finestra, perche' i trasbordi a terra derivati dalla base di conoscenza sono gli
stessi a qualunque ora, e sono 41.266 a Roma e 21.130 a Torino. Il grafo di due
ore di Roma occupa dodici megabyte, costo che rende praticabile ricostruirlo per
ogni interrogazione anziche' conservarlo.

Sulle cinquanta coppie esaminate per citta' la finestra di due ore si e' rivelata
sufficiente in **43 casi su 50 a Roma e 39 su 50 a Torino**, cioe' nell'86% e nel
78%. Le sette e le undici coppie rimaste non sono state escluse dal campione: la
loro percentuale e' essa stessa un risultato, e toglierle darebbe una falsa
impressione di completezza. Corrispondono a collegamenti che nella finestra
considerata non esistono, tipicamente fra periferie opposte servite da linee a
bassa frequenza.

**La relazione di dominanza vale due ordini di grandezza.** Sulla prima coppia
risolta del campione di Torino, la 3176 → 3492 estratta con il seme 20260826, le
due formulazioni della chiave di stato danno questi numeri.

| Formulazione dello stato a terra | Stati espansi | Secondi |
| --- | ---: | ---: |
| `(fermata, istante, cambi)` | 1.464.312 | 60,39 |
| `(fermata, cambi)` | 23.597 | 0,61 |

Sessantadue volte meno stati e novantanove volte meno tempo, con lo stesso
identico orario di arrivo. Su altre coppie il divario e' risultato ancora piu'
ampio, fino a milioni di stati e oltre duecento secondi. La coincidenza dei
risultati prima e dopo conferma sperimentalmente l'argomentazione di dominanza.
Vale la pena osservare che senza questa riformulazione l'intera campagna
sperimentale finale, che prevede migliaia di interrogazioni, non sarebbe
eseguibile: a duecento secondi per interrogazione, mille interrogazioni
richiederebbero due giorni e mezzo di calcolo.

**L'euristica geografica: un risultato negativo.**

Tabella 7 — Confronto delle varianti di ricerca. Media e deviazione standard
sulle coppie risolte: 43 per Roma, 39 per Torino. La colonna "non ottime" conta
le interrogazioni in cui la variante restituisce un orario di arrivo diverso da
quello di Dijkstra, che non usando euristiche non puo' essere influenzato da una
stima sbagliata.

| Citta' | Variante | V (m/s) | Stati espansi | Secondi | Risparmio | Non ottime |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Roma | Dijkstra | - | 37.156 ± 32.062 | 0,514 ± 0,398 | - | 0 / 43 |
| Roma | A* ammissibile | 82,5 | 34.391 ± 29.851 | 0,743 ± 0,540 | 7,7% ± 2,6% | 0 / 43 |
| Roma | A* p99,9 *(non amm.)* | 15,3 | 23.771 ± 21.376 | 0,586 ± 0,441 | 35,8% ± 9,8% | 0 / 43 |
| Torino | Dijkstra | - | 13.783 ± 10.348 | 0,201 ± 0,142 | - | 0 / 39 |
| Torino | A* ammissibile | 139,1 | 13.301 ± 10.034 | 0,311 ± 0,191 | 3,8% ± 1,6% | 0 / 39 |
| Torino | A* p99,9 *(non amm.)* | 22,8 | 11.070 ± 8.532 | 0,286 ± 0,178 | 20,6% ± 6,8% | 0 / 39 |

Il risultato principale e' negativo, e conviene enunciarlo senza attenuazioni:
**l'euristica ammissibile risparmia il 7,7% degli stati a Roma e il 3,8% a
Torino, e A\* impiega piu' tempo di Dijkstra**, 0,74 secondi contro 0,51 a Roma.
Calcolare l'euristica costa piu' dei nodi che fa evitare.

Non e' un fallimento del metodo: e' il metodo che funziona correttamente su dati
imperfetti, e la catena che porta a quel numero e' interamente ricostruibile.
L'ammissibilita' obbliga a scegliere come `V` il massimo vero delle velocita', che
e' di **500,8 km/h a Torino e 297,1 a Roma**. Quei valori non vengono da
coordinate sbagliate, come si potrebbe supporre, ma dalla tabella oraria: gli
archi anomali coprono distanze del tutto ordinarie, duecento o quattrocento
metri, in **tre secondi di orario programmato**. Sono 135 archi su 1.752.603 a
Torino e 1.063 su 5.343.307 a Roma. Con un `V` di cinquecento chilometri orari
l'euristica stima in pochi secondi un tempo residuo che ne vale centinaia, e A*
si comporta quasi come Dijkstra.

Tabella 8 — Distribuzione delle velocita' fra fermate consecutive, misurata
sull'orario programmato.

| Citta' | Archi | Mediana | p99 | p99,9 | Massimo | Sopra 150 km/h |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Roma | 5.343.307 | 15,6 km/h | 34,4 km/h | 55,2 km/h | 297,1 km/h | 1.063 |
| Torino | 1.752.603 | 16,4 km/h | 56,2 km/h | 82,0 km/h | 500,8 km/h | 135 |

La variante non ammissibile, con `V` al 99,9-esimo percentile — 55,2 km/h a Roma
e 82,0 a Torino, valori fisicamente plausibili per un mezzo urbano — risparmia il
35,8% e il 20,6% degli stati, da quattro a cinque volte piu' dell'ammissibile. Il
dato piu' interessante e' pero' un altro: **su nessuna delle 82 interrogazioni
risolte la variante non ammissibile ha restituito un orario di arrivo diverso
dall'ottimo**. La garanzia formale e la sua violazione pratica sono due cose
distinte, e i dati dicono che su questa rete la seconda non si manifesta. Cio'
non autorizza a rinunciare alla garanzia: un campione di ottantadue
interrogazioni non dimostra che non esista una coppia su cui la variante sbagli,
e la differenza fra "non abbiamo trovato controesempi" e "non esistono
controesempi" e' esattamente cio' che una dimostrazione fornisce e una misura no.

**Il costo dei cambi nello stato, e perche' non e' spreco.** Tenere il numero di
cambi nello stato moltiplica lo spazio di ricerca. La variante che proietta via i
cambi, identificando uno stato a terra con la sola fermata, espande **11.734
stati contro 34.391 a Roma** e **4.817 contro 13.301 a Torino**, circa un terzo.
Preso da solo, il numero suggerirebbe che i cambi nello stato costino un fattore
tre di lavoro inutile. La misura dice pero' anche un'altra cosa, che il solo
conteggio degli stati nasconderebbe: la variante proiettata **restituisce
l'itinerario sbagliato su 5 interrogazioni su 40 a Roma e su 4 su 39 a Torino**.

Il meccanismo e' stato isolato sperimentalmente ed e' l'interazione con il tetto
di quattro cambi. Con i cambi proiettati via, uno stato raggiunto per primo
attraverso un percorso che ha gia' speso quattro cambi viene marcato come
visitato, e un percorso successivo che vi arrivi con un solo cambio viene
scartato perche' non migliora l'orario di arrivo — salvo che quel secondo
percorso avrebbe potuto proseguire per altri tre cambi, mentre il primo era
esaurito. Ripetendo l'esperimento con un tetto di dodici cambi le discrepanze
scendono a **zero**, il che conferma che la causa e' il tetto e non un difetto
della proiezione in se'. Il fattore tre non e' dunque spreco ma il **prezzo della
correttezza** in presenza di un vincolo sul numero di cambi, ed e' anche la
ragione per cui il progetto mantiene una sola struttura di stato invece di due
implementazioni: la variante proiettata esiste unicamente come termine di
paragone di questa misura.

**La frontiera di Pareto sui dati reali.** La ricerca multi-criterio restituisce
in media **5,72 ± 2,83 soluzioni non dominate a Roma** e **5,05 ± 2,89 a
Torino**. Il numero e' significativo: se esistesse un itinerario ottimo la
frontiera ne conterrebbe uno solo. Che ne contenga mediamente cinque significa
che su una tipica coppia origine-destinazione ci sono cinque compromessi
genuinamente diversi fra rapidita', numero di cambi e minuti a piedi, nessuno dei
quali migliore degli altri senza una decisione su quanto valga un cambio. E'
precisamente il fatto che rende interessante la domanda di ricerca del progetto:
se l'itinerario ottimo fosse unico, massimizzare la probabilita' di arrivo entro
un orario si ridurrebbe a un problema di riordinamento.

![**Figura 2.** Costo del grafo ed effetto dell'euristica, su cinquanta coppie origine-destinazione per citta' con partenza alle 08:00 e finestra di 120 minuti. Il pannello (a) riporta la crescita del grafo con l'orizzonte temporale, in scala doppio logaritmica. Il pannello (b) confronta gli stati espansi da A* ammissibile con quelli di Dijkstra sulle stesse interrogazioni: la nuvola aderisce alla bisettrice, che e' la rappresentazione visiva del risparmio quasi nullo. Il pannello (c) confronta la distribuzione del risparmio per le due varianti; **le scatole tratteggiate corrispondono all'euristica NON ammissibile**, che non garantisce l'ottimo e non produce alcun risultato ufficiale del progetto. Il pannello (d) mostra il costo dei cambi nello stato: la variante proiettata espande circa un terzo degli stati, ma sbaglia l'itinerario su nove interrogazioni su 79. Dati grezzi in `results/ricerca_astar.csv`, `results/grafo_finestra.csv` e `results/velocita_archi.csv`.](../results/ricerca_astar.png)

Nessuno dei risultati riportati in questa sezione dipende da un modello dei
ritardi: sono tutti calcolati sull'orario programmato pubblicato dalle due
aziende.

# Sezione Argomento 3 — Ragionamento e incertezza

## Sommario

Questo modulo assegna a ciascun itinerario la probabilita' di arrivare a
destinazione entro una scadenza `T`, e sceglie quello che la massimizza. Riceve
come candidati gli itinerari non dominati prodotti dalla ricerca multi-criterio
descritta nell'argomento precedente — mediamente fra cinque e sei per ogni coppia
origine-destinazione — e come modello dei ritardi una distribuzione condizionata
alla linea, alla posizione lungo la corsa e al ritardo osservato a monte. E' il
modulo che realizza l'obiettivo del progetto.

**Perche' l'obiettivo probabilistico non e' una penalizzazione del tempo.** La
tentazione naturale, di fronte al problema, e' evitare la probabilita' e
correggere l'orario: penalizzare gli itinerari con coincidenze tese, per esempio
sommando al tempo di viaggio un termine proporzionale alla strettezza dei
margini. Sarebbe piu' semplice e non richiederebbe alcun modello dei ritardi. Non
funziona, e la ragione non e' di accuratezza ma di struttura. Una penalizzazione
della forma "tempo di viaggio piu' lambda per la tensione delle coincidenze"
induce **un solo ordinamento** sugli itinerari: fissato lambda esiste un
migliore, ed e' sempre lo stesso. La quantita' P(arrivo <= T) induce invece **una
famiglia di ordinamenti indicizzata da T**, e nessuna scelta di lambda puo'
riprodurre una famiglia con un elemento solo.

L'inversione si vede su due itinerari costruiti apposta. Il primo, A, arriva
cinquanta minuti dopo la partenza secondo l'orario, ma la sua unica coincidenza
ha due minuti di margine. Il secondo, B, arriva cinquantacinque minuti dopo, con
dodici minuti di margine.

| Scadenza T | P(A) | P(B) | Migliore |
| ---: | ---: | ---: | :---: |
| +50 min | 0,078 | 0,000 | A |
| +55 min | 0,337 | 0,236 | A |
| +60 min | 0,498 | 0,827 | **B** |
| +70 min | 0,912 | 0,990 | **B** |
| +120 min | 0,998 | 1,000 | **B** |

Per una scadenza stretta vince A, perche' B non puo' proprio arrivare in tempo:
il suo orario di arrivo programmato e' gia' oltre la scadenza. Per una scadenza
appena piu' larga vince B, e con distacco, perche' la coincidenza di A salta
troppo spesso. Nessun ordinamento fisso puo' contenere entrambe le risposte.
L'esempio rende immediato il meccanismo ma resta un caso costruito: il risultato
vero e' la misura su un campione, riportata nella valutazione.

**La catena delle coincidenze, e perche' il prodotto ingenuo sbaglia.** Calcolare
P(arrivo <= T) richiede di comporre le distribuzioni di ritardo lungo la
successione delle tappe. La composizione ovvia — il prodotto delle probabilita'
di prendere ciascuna coincidenza — e' sbagliata per due ragioni di segno opposto,
e nessuna delle due e' trascurabile.

**Sovrastima**, perche' tratta come indipendenti eventi che non lo sono. Il
ritardo con cui un mezzo arriva alla fermata di discesa non e' indipendente da
quello con cui e' partito: e' lo stesso veicolo, e i ritardi si accumulano lungo
il percorso. La probabilita' congiunta di due coincidenze prese non e' il
prodotto delle marginali.

**Sottostima**, perche' considera fallimento definitivo una coincidenza persa.
Chi perde un autobus prende quello successivo e arriva piu' tardi, il che puo'
benissimo essere ancora entro T. Ignorare il recupero cancella proprio il
fenomeno che la domanda di ricerca vuole misurare: un itinerario e' robusto anche
perche', quando perde una coincidenza, ne trova un'altra presto. E' una
proprieta' della rete e non del singolo itinerario, e senza il recupero due
itinerari con la stessa coincidenza tesa ma frequenze molto diverse
risulterebbero identici.

La struttura corretta e' **markoviana con azzeramento**. Presa una coincidenza,
l'arrivo a valle dipende dal ritardo del nuovo mezzo e non da quanto per poco la
si e' presa: l'informazione sul ritardo precedente si perde attraversando il
cambio. Il ritardo si propaga percio' *dentro* una corsa, non *fra* una corsa e
la successiva, e la catena va rappresentata come una successione di tappe in cui,
a ciascuna, si sceglie quale corsa si riesca effettivamente a prendere fra quella
pianificata e i recuperi disponibili. Il condizionamento fra salita e discesa e'
esplicito: la distribuzione del ritardo alla discesa viene richiesta al modello
passandogli il ritardo alla salita. E' il punto in cui il calcolo smette di
trattare come indipendenti eventi che non lo sono, ed e' anche la ragione per cui
l'interfaccia del modello dei ritardi prevede fin dall'inizio un campo per il
ritardo a monte.

La stessa quantita' e' calcolata in due modi indipendenti, per convoluzione
numerica su una griglia temporale discreta e per campionamento. Averne due non e'
ridondanza: sulla catena a piu' coincidenze non esiste una forma chiusa contro
cui verificare il risultato, e la concordanza fra due implementazioni che non
condividono nulla e' l'unica verifica non circolare disponibile. L'unico caso con
soluzione analitica — una sola tappa, senza correlazione, con la corsa sempre
prendibile — e' usato come ancoraggio nei test, e li' entrambi i metodi
coincidono con la ripartizione del ritardo entro due punti percentuali.

## Strumenti utilizzati

Il calcolo impiega due metodi standard: la **convoluzione numerica** di
distribuzioni discretizzate su griglia e il **campionamento Monte Carlo**;
entrambi sono descritti nel testo del corso per il ragionamento in condizioni di
incertezza [3], e le loro proprieta' di convergenza sono quelle usuali. Le
distribuzioni continue e le loro funzioni di ripartizione provengono da
**scipy.stats** [8]; la propagazione sulla griglia e il campionamento usano
**numpy** [7], con generatori pseudocasuali espliciti e inizializzati da un seme
dichiarato.

Sono originali di questo progetto, e per questo esposti nel sommario e fra le
decisioni di progetto anziche' qui: l'argomentazione sulla non riducibilita'
dell'obiettivo probabilistico a una penalizzazione del tempo, l'analisi delle due
ragioni di segno opposto per cui il prodotto ingenuo delle probabilita' sbaglia,
e la struttura markoviana con azzeramento e recupero con cui la catena delle
coincidenze e' modellata.

## Decisioni di Progetto

**L'interfaccia del modello dei ritardi e' fissata prima dei dati.** Il contratto
fra il calcolo di probabilita' e il modello dei ritardi e' stato progettato prima
che i dati reali fossero disponibili, e comprende fin dall'inizio il campo per il
ritardo a monte che rende esprimibile il condizionamento. Esiste
un'implementazione **sintetica** che lo soddisfa, usata per far girare e
collaudare il codice mentre la raccolta prosegue. Un modello sintetico e' per
costruzione indistinguibile da uno vero attraverso l'interfaccia, ed e'
esattamente questo a renderlo pericoloso: senza un controllo esplicito, una
dimenticanza basterebbe a pubblicare numeri calcolati su ritardi inventati senza
che nulla lo segnali. Il presidio ha tre livelli: ogni modello espone un
attributo che dichiara se sia sintetico; ogni script che scriva in `results/`
invoca un controllo che solleva un errore a meno che non sia stato concesso il
permesso esplicito; e ogni file di risultati porta il nome del modello che lo ha
prodotto, cosi' l'origine resta leggibile anche a distanza di mesi.

**Una coincidenza persa e' un ritardo, non un fallimento.** Quando la catena
perde una coincidenza, il calcolo prosegue sulla corsa successiva della stessa
linea dalla stessa fermata, fino a un tetto di due recuperi; solo esaurito il
tetto l'itinerario fallisce. L'alternativa scartata era il fallimento secco, molto
piu' semplice da calcolare, che pero' rende P(arrivo <= T) sistematicamente
pessimistica e soprattutto cancella il fenomeno che la domanda di ricerca vuole
misurare. Il tetto va dichiarato e misurato: sulle 1.920 valutazioni della
griglia sperimentale la quota media di massa di probabilita' che esaurisce i
recuperi e' del **9,2%**, circa un caso su undici. E' abbastanza da meritare
questa menzione e non abbastanza da governare i risultati; oltre un quarto il
tetto direbbe piu' sul proprio valore che sul mondo, e andrebbe alzato.

**Due metodi di calcolo, e la convoluzione resta quella del pianificatore.** La
misura riportata nella valutazione mostra che il Monte Carlo domina la
convoluzione sia in accuratezza sia in costo. La convoluzione resta comunque il
metodo usato dal pianificatore, per una proprieta' che l'errore medio non
cattura: e' **deterministica**. Due esecuzioni danno lo stesso numero, mentre il
Monte Carlo ha rumore campionario, e un pianificatore che confronta cinque
candidati fra loro puo' vedere invertito l'ordine di due itinerari quasi
equivalenti dal solo rumore, rendendo la scelta irriproducibile. Il campionamento
e' percio' relegato al ruolo di verifica, che e' quello in cui la sua accuratezza
superiore serve davvero.

**La correlazione lungo la corsa e' un parametro, non una costante.** Il modello
accetta un parametro in [0, 1] che governa quanto il ritardo osservato a monte si
trasferisca alla fermata di discesa; il valore usato negli esperimenti e' 0,7.
Ignorarlo renderebbe la catena artificialmente ottimistica, perche' tratterebbe
come indipendenti il ritardo alla salita e quello alla discesa dello **stesso
mezzo**; cablarlo significherebbe scrivere il resto del progetto attorno a un
numero inventato, mentre il modello appreso dai dati avra' la correlazione che i
dati mostrano. A correlazione nulla il condizionamento non ha effetto e
P(arrivo <= T) di una singola tappa coincide con la ripartizione del ritardo: e'
esattamente l'ancoraggio analitico usato nei test.

**L'insieme candidato e' la frontiera di Pareto, e la misura che lo giustifica.**
Il limite di massimizzare su quell'insieme e' piu' affilato di quanto sembri: la
frontiera e' calcolata su criteri deterministici — orario di arrivo, numero di
cambi, minuti a piedi — e **collassa fra loro gli itinerari che differiscono solo
per il margine sulle coincidenze**, che e' precisamente la dimensione da cui
dipende la robustezza. Massimizzare su un insieme privo delle alternative
rilevanti non sarebbe un limite da dichiarare in una nota: sarebbe un esperimento
incapace di rispondere alla domanda posta. Il dubbio e' stato risolto **prima** di
costruire il pianificatore, misurando quanto P vari lungo la frontiera. La
risposta e' che varia molto: l'ampiezza fra la soluzione migliore e la peggiore
e' mediamente di **0,44**, e solo una coppia su quattordici sta sotto 0,05. La
frontiera e' quindi abbastanza ricca, e l'allargamento dell'insieme candidato —
che era la contromisura preparata — non si e' reso necessario.

Vale la pena riferire che la **prima versione di questa misura era viziata**, e
perche'. Includeva fra i candidati anche gli itinerari il cui arrivo *programmato*
cadeva gia' dopo la scadenza, che hanno probabilita' prossima a zero per
costruzione: l'ampiezza risultava di 0,66, ma quel numero registrava soprattutto
che un itinerario piu' lento arriva piu' tardi, il che non e' una scoperta.
Restringendo ai soli itinerari **nominalmente fattibili** il valore scende a 0,44,
ed e' quello a rispondere alla domanda. La differenza fra i due numeri e'
esattamente la velocita' travestita da robustezza.

**La scadenza e' relativa all'itinerario piu' veloce.** T e' definita come orario
di arrivo dell'itinerario piu' veloce piu' un margine, e il margine varia su una
griglia di zero, cinque, dieci, quindici, venti e trenta minuti. La definizione
relativa aderisce alla domanda di ricerca, che parla di confronto "a parita' di
tempo di viaggio nominale"; una scadenza assoluta avrebbe introdotto una scelta
arbitraria sull'orario dell'appuntamento, e i risultati avrebbero dipeso da
quella invece che dal metodo. Va riconosciuto che questa definizione e' **severa
verso il criterio probabilistico**: ogni itinerario piu' lento di un certo scarto
sull'orario deve recuperare quello scarto prima ancora di poter competere, quindi
il piu' veloce parte avvantaggiato per costruzione. E' aritmetica della
definizione, non una proprieta' del modello, e implica che il vantaggio misurato
vada letto come un limite inferiore.

**Il tratto a piedi finale entra nel tempo di viaggio.** L'itinerario porta un
campo con i secondi di cammino dopo l'ultima discesa, e tutti i calcoli ne
tengono conto. La prima versione del convertitore costruiva le tappe dai soli
tratti percorsi a bordo, quindi calcolava la probabilita' di arrivare **alla
fermata di discesa** invece che a destinazione: sul campione di Torino il **54%
dei candidati termina con un tratto a piedi**, quindi per piu' della meta' degli
itinerari il tempo di viaggio era sottostimato, e sistematicamente a favore
proprio di quelli che camminano di piu'. Il confronto fra strategie ne sarebbe
uscito falsato nella direzione peggiore, perche' la strategia del margine fisso
tende a scegliere itinerari con piu' cammino. Il tratto a piedi resta separato
dalle tappe perche' non e' soggetto a ritardi: si cammina sempre alla stessa
velocita', e trattarlo come una tappa gli attribuirebbe una varianza che non ha.

**Un test che falliva a intermittenza non e' stato archiviato.** I parametri delle
distribuzioni sintetiche sono derivati da `hashlib.blake2b` e non dalla funzione
`hash` incorporata. La ragione merita di essere riportata perche' dice qualcosa
sul metodo prima che sul codice. Un test deterministico ha cominciato a fallire
in circa due esecuzioni su tre della suite completa, passando sempre quando
eseguito da solo. La tentazione naturale, di fronte a un test che "a volte
fallisce", e' allargarne la tolleranza o dichiararlo instabile. La causa era
invece un difetto vero: il modello usava `hash((seme, route_id))` per derivare i
parametri, e **Python randomizza l'hash delle stringhe a ogni processo**, quindi
lo stesso identificativo di linea produceva parametri diversi a ogni esecuzione.
Il modello si dichiarava deterministico dato un seme e non lo era, e la verifica
fatta inizialmente — due chiamate nello stesso processo — era proprio quella
incapace di rivelarlo. Le conseguenze sarebbero andate ben oltre il test: **ogni
esperimento di questa sezione sarebbe stato irriproducibile**, e il difetto si
sarebbe manifestato solo come numeri che cambiano fra un'esecuzione e l'altra
senza spiegazione, in un progetto che dichiara la riproducibilita' fra i propri
requisiti. Un test deterministico che fallisce a intermittenza non e' un test
instabile: e' un programma non deterministico, e la differenza fra le due letture
e' la differenza fra trovare il difetto e nasconderlo.

## Valutazione

**Avvertenza sui risultati di questa sezione.** Il modello dei ritardi utilizzato
qui e' **sintetico**: le distribuzioni sono inventate, non apprese dai dati
raccolti sul campo, che alla data di scrittura non erano ancora sufficienti. I
numeri riportati qualificano il **metodo** — se il calcolo e' corretto, quanto
costa, in quali condizioni il criterio probabilistico cambia la scelta — e non
dicono nulla sul trasporto pubblico di Roma o di Torino. Ogni file di risultato
porta il nome del modello in una colonna, e gli script si rifiutano di scrivere
senza un permesso esplicito. I risultati sperimentali sui ritardi reali sono
oggetto dell'argomento successivo, non ancora concluso. Le sezioni precedenti non
sono interessate da questa avvertenza: i loro risultati sono calcolati sulla
topologia della rete e sull'orario programmato pubblicati dalle due aziende.

**Accuratezza e costo dei due metodi di calcolo.**

Tabella 9 — Accuratezza e costo. L'errore e' lo scarto rispetto a un Monte Carlo
con 200.000 campioni, media e deviazione standard su tutte le valutazioni della
griglia.

| Metodo | Parametro | Errore su P | Costo per valutazione |
| --- | ---: | ---: | ---: |
| convoluzione | passo 5 s | 0,0039 ± 0,0047 | 96 ms |
| convoluzione | passo 10 s | 0,0049 ± 0,0060 | 89 ms |
| convoluzione | passo 30 s | 0,0165 ± 0,0148 | 87 ms |
| convoluzione | passo 60 s | 0,0385 ± 0,0293 | 87 ms |
| Monte Carlo | 100 campioni | 0,0271 ± 0,0225 | 3 ms |
| Monte Carlo | 1.000 campioni | 0,0107 ± 0,0092 | 8 ms |
| Monte Carlo | 10.000 campioni | 0,0026 ± 0,0021 | 25 ms |
| Monte Carlo | 100.000 campioni | 0,0011 ± 0,0008 | 151 ms |

**Il risultato non e' quello atteso.** Ci si aspettava che la convoluzione fosse
il metodo esatto e il campionamento l'approssimazione economica. La misura dice
il contrario: il Monte Carlo con diecimila campioni e' **piu' accurato e quasi
quattro volte piu' rapido** della convoluzione con passo di dieci secondi, e la
domina su entrambi gli assi per ogni scelta dei parametri. La spiegazione sta in
dove finisce il tempo. Il costo della convoluzione non e' dominato dalla griglia
temporale ma dal numero di interrogazioni al modello dei ritardi: una per ogni
bin di ritardo alla salita e per ogni corsa candidata, perche' ognuna richiede la
distribuzione condizionata corrispondente. Raffinare la griglia temporale da
sessanta a cinque secondi costa nove millisecondi, ma il costo di base e' gia'
superiore a quello del campionamento con diecimila estrazioni.

![**Figura 3.** Accuratezza e costo dei due metodi di calcolo, su distribuzioni sintetiche. Nel pannello (a) l'asse orizzontale porta il parametro di ciascun metodo, che ha significato diverso per i due: passo della griglia in secondi per la convoluzione, numero di campioni per il Monte Carlo. Il pannello (b) e' quello che conta: mette accuratezza e costo sugli stessi assi, e mostra che la curva del Monte Carlo giace interamente in basso a sinistra rispetto a quella della convoluzione. Dati grezzi in `results/conv_vs_montecarlo.csv`.](../results/conv_vs_montecarlo.png)

**La griglia della scadenza, e la dimostrazione di non riducibilita'.**

Tabella 10 — Le tre grandezze al variare del margine sulla scadenza, su quaranta
coppie origine-destinazione per citta'. Il guadagno e' la differenza media fra la
probabilita' della scelta robusta e quella della baseline piu' veloce.

| Citta' | Margine | Ampiezza sulla frontiera | Coincidenza | Guadagno su piu' veloce |
| --- | ---: | ---: | ---: | ---: |
| Roma | 0 min | 0,026 ± 0,042 | 85% | 0,001 ± 0,003 |
| Roma | 5 min | 0,279 ± 0,266 | 82% | 0,040 ± 0,123 |
| Roma | 10 min | 0,371 ± 0,269 | 75% | 0,068 ± 0,158 |
| Roma | 15 min | 0,425 ± 0,268 | 75% | 0,080 ± 0,188 |
| Roma | 20 min | 0,433 ± 0,279 | 70% | 0,084 ± 0,190 |
| Roma | 30 min | 0,562 ± 0,302 | 62% | 0,049 ± 0,104 |
| Torino | 0 min | 0,024 ± 0,027 | 88% | 0,009 ± 0,050 |
| Torino | 5 min | 0,290 ± 0,270 | 80% | 0,040 ± 0,147 |
| Torino | 10 min | 0,376 ± 0,251 | 75% | 0,058 ± 0,152 |
| Torino | 15 min | 0,452 ± 0,251 | 70% | 0,098 ± 0,210 |
| Torino | 20 min | 0,429 ± 0,265 | 68% | 0,096 ± 0,191 |
| Torino | 30 min | 0,478 ± 0,271 | 55% | 0,061 ± 0,120 |

Le tre colonne, lette insieme, sono la dimostrazione di non riducibilita'. La
coincidenza fra la scelta robusta e quella piu' veloce **scende monotonamente**
dall'85-88% a margine nullo al 55-62% a trenta minuti: al variare della sola
scadenza, a parita' di rete, di orario e di modello dei ritardi, il criterio
probabilistico cambia idea su una frazione crescente delle coppie. Nessun
ordinamento fisso sugli itinerari puo' produrre questo comportamento, ed e' la
misura su ottanta coppie che sostituisce l'esempio costruito riportato nel
sommario.

Il guadagno **non e' monotono**, e la sua forma a campana e' il risultato piu'
informativo della sezione. A margine nullo vale praticamente zero, perche' la
scadenza coincide con l'arrivo programmato del piu' veloce e nessun itinerario ha
speranze apprezzabili: non c'e' niente da guadagnare quando tutti falliscono. A
trenta minuti torna a scendere, perche' la scadenza e' cosi' larga che quasi
tutti arrivano: non c'e' niente da guadagnare nemmeno quando tutti riescono. Il
massimo sta fra i quindici e i venti minuti, dove il criterio probabilistico
guadagna fra otto e dieci punti percentuali di probabilita' di arrivo. Questo non
e' un limite del metodo ma il suo **campo di applicabilita'**, e va letto cosi':
il ragionamento probabilistico serve quando la scadenza e' abbastanza stretta da
rendere il fallimento possibile e abbastanza larga da rendere il successo
raggiungibile. Fuori da quell'intervallo la risposta non dipende dal criterio, e
un modello dei ritardi non ripaga la propria complessita'.

![**Figura 4.** Le tre grandezze in funzione del margine sulla scadenza, su quaranta coppie per citta' e con modello dei ritardi sintetico. Il pannello (b) e' la dimostrazione di non riducibilita': la coincidenza fra scelta robusta e scelta piu' veloce scende al crescere del margine, quindi l'ordinamento fra itinerari dipende dalla scadenza. Il pannello (c) mostra la forma a campana del guadagno. Le barre di deviazione standard del pannello (c) scendono sotto lo zero, ma si tratta di un artefatto: la deviazione standard e' simmetrica mentre la distribuzione non lo e', e la differenza per singola coppia non e' **mai** negativa, in nessuna delle 480 combinazioni esaminate. Dati grezzi in `results/robusto_griglia_T.csv`.](../results/robusto_griglia_T.png)

**Il confronto con le strategie di riferimento.** Le tre baseline non sono
avversari di comodo: rappresentano cio' che si fa realmente in assenza di un
modello dei ritardi. La **piu' veloce** e' il pianificatore di qualunque
applicazione di viaggio, ed e' il termine di paragone naturale perche' e' quello
che l'utente ha oggi. **Meno cambi** e' cio' che fa chi ha imparato per
esperienza che ogni trasbordo e' un'occasione di perdere una coincidenza, ma non
sa quantificarlo. Il **margine fisso** e' la baseline che conta: rappresenta la
persona ragionevole che si da' una regola — accetto solo itinerari in cui ogni
coincidenza ha almeno cinque minuti di margine, e fra quelli prendo il piu'
veloce. E' una strategia sensata e gratuita, ed e' quella che il pianificatore
probabilistico deve battere per giustificare la propria esistenza. Tutte e
quattro le strategie scelgono dallo stesso insieme di candidati e vengono
valutate con lo stesso calcolo di P(arrivo <= T): il confronto misura quindi la
strategia di scelta e non il metodo di valutazione.

Tabella 11 — Probabilita' media di arrivo entro la scadenza, su tutte le coppie e
tutti i margini della griglia.

| Strategia | Roma | Torino |
| --- | ---: | ---: |
| robusto | **0,555 ± 0,374** | **0,570 ± 0,367** |
| piu' veloce | 0,501 ± 0,363 | 0,509 ± 0,373 |
| meno cambi | 0,429 ± 0,411 | 0,388 ± 0,418 |
| margine fisso | 0,403 ± 0,418 | 0,426 ± 0,420 |

Due osservazioni, di cui la seconda inattesa. La prima e' che il pianificatore
robusto **non perde mai** contro nessuna baseline: su tutte e 480 le combinazioni
di citta', coppia e margine, la sua probabilita' e' maggiore o uguale a quella di
ciascuna alternativa. Va detto pero' che questo non e' un risultato ma un
**controllo di correttezza**: le quattro strategie scelgono dallo stesso insieme
e il pianificatore massimizza per definizione la grandezza con cui tutte vengono
poi valutate, quindi perdere sarebbe stato un difetto dell'implementazione. Il
risultato e' semmai di quanto vince, che e' il contenuto della Tabella 10.

La seconda e' che la strategia del **margine fisso e' la peggiore delle tre**,
sotto perfino a "meno cambi" su Roma. Il fatto merita attenzione perche'
contraddice l'intuizione, ed e' spiegabile: con una scadenza ancorata all'arrivo
del piu' veloce, imporre cinque minuti di margine su ogni coincidenza costringe a
scegliere itinerari sensibilmente piu' lenti sull'orario, e lo svantaggio di
partenza supera il beneficio della maggiore affidabilita'. La regola del margine
fisso e' una difesa contro le coincidenze perse che non guarda alla scadenza, e
in un problema in cui la scadenza e' il vincolo si difende dal rischio sbagliato.
E' precisamente il tipo di errore che un criterio probabilistico esplicito evita,
perche' P(arrivo <= T) contiene T e la regola dei cinque minuti no.

Va ricordato un'ultima volta che tutti i numeri di questa sezione sono calcolati
su ritardi inventati. Dicono che il metodo distingue gli itinerari, che il calcolo
e' corretto e riproducibile, e in quale intervallo di scadenze il criterio
probabilistico cambia le decisioni. Se il vantaggio misurato qui si conservi sui
ritardi reali di Roma e di Torino e' esattamente la domanda a cui l'argomento
successivo dovra' rispondere, ed e' l'unica risposta che varra' come risultato
sperimentale sul trasporto pubblico.

# Sezione Argomento 4 — Apprendimento supervisionato e apprendimento con incertezza

## Sommario

Questo modulo stimera' dai dati raccolti sul campo le distribuzioni di ritardo
che il ragionamento probabilistico descritto nell'argomento precedente compone
lungo la catena delle coincidenze. Fino a oggi quel ragionamento e' stato
collaudato su distribuzioni sintetiche, che permettono di verificare il calcolo
ma non dicono nulla sul trasporto pubblico reale; sostituirle con distribuzioni
apprese e' cio' che trasforma il metodo in un risultato sperimentale.

La grandezza da stimare non e' un valore ma una **distribuzione condizionata**:
dato il passaggio di una corsa a una fermata, la distribuzione del suo
scostamento dall'orario programmato, condizionata alla linea, alla fascia oraria,
alla posizione lungo la corsa e al ritardo gia' osservato a monte sulla stessa
corsa. Le prime tre variabili spiegano quanto una linea sia strutturalmente
puntuale; l'ultima e' quella che rende esprimibile la correlazione dentro una
corsa, ed e' la ragione per cui l'interfaccia del modello dei ritardi la prevede
fin dalla prima versione.

**La raccolta dei dati e' completa e funzionante**, ed e' l'unica parte di questo
argomento gia' conclusa. Un sistema installato su una macchina virtuale sempre
accesa interroga ogni minuto i due feed GTFS Real-Time di ciascuna citta',
`trip_updates` e `vehicle_positions`, conserva i dump grezzi, archivia
l'orario statico ogni volta che cambia e consolida ogni notte le osservazioni
della giornata in formato colonnare, calcolando lo scostamento fra orario
osservato e orario programmato. Alla data di scrittura risultano **quattro
giornate consolidate per 74 MB di dati colonnari**, e sull'ultima giornata piena
la copertura reale e' del **100% su entrambe le citta'**.

Cio' che manca e' la stima vera e propria: la scelta della famiglia di
distribuzioni, il raggruppamento delle condizioni con numerosita' campionaria
sufficiente, la validazione della bonta' di adattamento e il confronto fra il
modello appreso e quello sintetico sulle stesse coppie origine-destinazione. La
valutazione di questo argomento sara' percio' anche la risposta finale alla
domanda di ricerca del progetto.

## Strumenti utilizzati

La stima impieghera' **scikit-learn** [9] per la parte di apprendimento
supervisionato e **scipy.stats** [8] per l'adattamento delle distribuzioni e i
test di bonta' di adattamento; la manipolazione dei dati colonnari usa **pandas**
[5] e il formato Parquet tramite **pyarrow**. La raccolta gia' in esercizio usa
**gtfs-realtime-bindings** [10] per interpretare il formato protobuf dei feed e
la sola libreria standard di Python per le richieste HTTP.

## Decisioni di Progetto

Le decisioni gia' prese riguardano la raccolta, e sono vincolanti per la stima
perche' determinano che cosa sara' disponibile. Le riportiamo qui perche' e' in
questo argomento che i dati raccolti vengono consumati.

**Si conserva una riga a ogni cambio della previsione, non solo l'ultima.** Per
ogni passaggio, identificato da `(trip_id, stop_sequence)`, si conserva una riga a
ogni cambio del valore osservato. Una previsione che cambia nel corso della
giornata **non e' un duplicato**: e' l'evoluzione della stima dell'azienda, e dice
quanto quella previsione fosse affidabile con un certo anticipo. E' informazione
che potrebbe servire come variabile esplicativa e che non e' ricostruibile a
posteriori se la si getta ora.

**Il risultato negativo che accompagna quella scelta.** Il presupposto della
regola era che lo stesso passaggio comparisse identico in centinaia di dump
consecutivi e che la deduplica scartasse quindi la quasi totalita' delle righe.
Misurato sui dati reali non e' cosi': su 98 dump di Roma, 1.982.754
`stop_time_update` hanno prodotto 1.361.088 righe, cioe' il **68,6%** del totale,
perche' Roma ricalcola la previsione quasi a ogni giro e ogni passaggio riceve in
media 10,9 valori distinti, fino a un massimo di 76; su Torino la quota e' il
65,1% con 5,4 valori per passaggio. La proiezione a giornata piena e' di circa
**20 milioni di righe al giorno per Roma** e 2,2 milioni per Torino. La regola
resta quella scelta, perche' la motivazione che la giustifica non e' il risparmio
ma la conservazione di un'informazione irripetibile; va pero' registrato che il
beneficio in volume che le era stato attribuito non si e' verificato, e che il
dimensionamento di questo argomento va fatto su questi numeri e non su quelli
attesi.

**La chiave di join e' `(trip_id, stop_sequence)`, non quella naturale.** E' stato
scoperto eseguendo il consolidamento sui dati veri e notando che il numero di
passaggi conservati non tornava: 4.691 invece dei 13.092 misurati. La causa e' che
**GTT non include mai lo `stop_id`** nei `stop_time_update`, identificando la
fermata con il solo `stop_sequence`, mentre Roma si comporta all'opposto e lo
fornisce sempre. Con la chiave naturale il join su Torino non trovava mai
corrispondenza: la colonna `stop_id` restava vuota, l'orario programmato nullo e
il ritardo non calcolabile, e i dati di Torino sarebbero stati inutilizzabili
senza che nulla lo segnalasse. La specifica GTFS garantisce che `stop_sequence`
sia univoco dentro una corsa, quindi la chiave ridotta e' altrettanto precisa e
funziona su entrambe le aziende.

**L'orario statico e' archiviato a ogni cambiamento.** Il ritardo e' uno
scostamento da un orario programmato, e quell'orario cambia: confrontare
un'osservazione di oggi con l'orario di due settimane fa produrrebbe ritardi
inventati. Ogni giorno si confronta l'impronta dell'archivio statico e, se e'
cambiata, se ne conserva una nuova revisione; un indice associa a ogni data la
revisione valida quel giorno.

## Valutazione

La valutazione di questo argomento non e' ancora stata eseguita. Comprendera' la
bonta' di adattamento delle distribuzioni stimate, misurata su dati non usati per
la stima; il confronto fra il modello appreso e quello sintetico a parita' di
coppie origine-destinazione e di griglia di scadenze; e la ripetizione, sui
ritardi reali, dell'esperimento riportato nell'argomento precedente, che e' la
risposta alla domanda di ricerca del progetto. Ogni risultato sara' riportato
come media e deviazione standard su piu' giornate di raccolta, in modo che la
variabilita' fra giorni feriali e festivi e fra condizioni di traffico diverse
sia visibile e non nascosta in un valore unico.

# Conclusioni

Il sistema realizzato deriva da dati aperti una relazione che quei dati non
contengono, cerca su di essa gli itinerari non dominati fra tre criteri, e
sceglie fra questi quello che massimizza la probabilita' di arrivare entro una
scadenza. Le tre parti sono state misurate separatamente, e ciascuna ha prodotto
un risultato che vale la pena riassumere.

La base di conoscenza si e' rivelata sostenibile a piena scala — undici secondi e
mezzo per istanziare l'intera rete di Roma — e la misura ha attribuito il costo a
una regola precisa, la chiusura transitiva, che a duemila fermate genera da sola
il 92,9% degli atomi. Poiche' quella relazione serve di rado al pianificatore, il
costo si riduce di un ordine di grandezza disattivandola, e il fatto che la scelta
si possa compiere a valle senza riformulare le regole e' una proprieta' della
rappresentazione dichiarativa, non un accorgimento implementativo.

La ricerca ha prodotto due risultati negativi, entrambi istruttivi.
L'euristica geografica, benche' dimostrabilmente ammissibile, risparmia meno del
dieci per cento degli stati e fa impiegare ad A* piu' tempo di Dijkstra, perche'
l'ammissibilita' obbliga a tarare la velocita' massima su archi anomali
dell'orario che dichiarano quattrocento metri percorsi in tre secondi. La misura
del costo dei cambi nello stato, invece, ha mostrato che un'ottimizzazione
apparentemente gratuita — proiettare via il conteggio dei cambi, che riduce di
due terzi gli stati espansi — restituisce l'itinerario sbagliato su nove
interrogazioni su settantanove, e la causa isolata sperimentalmente e'
l'interazione con il tetto sul numero di cambi.

Il ragionamento probabilistico ha mostrato di non essere riducibile a una
penalizzazione del tempo di viaggio: al variare della sola scadenza, la scelta
robusta si discosta da quella piu' veloce su una frazione crescente delle coppie,
dal dodici-quindici per cento a margine nullo al trentotto-quarantacinque per
cento a trenta minuti.
Il guadagno ha una forma a campana con massimo fra i quindici e i venti minuti di
margine, ed e' quello il campo di applicabilita' del metodo: il ragionamento
probabilistico serve quando la scadenza e' abbastanza stretta da rendere il
fallimento possibile e abbastanza larga da rendere il successo raggiungibile.
Questi numeri sono pero' calcolati su distribuzioni di ritardo sintetiche, e
qualificano il metodo, non il trasporto pubblico di Roma o di Torino.

## Problematiche non affrontate, e possibili estensioni

Le lacune che seguono sono dichiarate per esteso, perche' un elenco preciso di
cio' che manca e' piu' utile di una sezione che lo nasconda, e perche' ciascuna
di esse e' un punto da cui un altro gruppo potrebbe ripartire.

**La risposta alla domanda di ricerca non c'e' ancora.** E' la lacuna piu'
importante. Il vantaggio del criterio probabilistico e' stato misurato su ritardi
inventati; se si conservi sui ritardi reali e' esattamente cio' che resta da
verificare. La raccolta e' completa e funzionante, con quattro giornate gia'
consolidate, ma la stima delle distribuzioni e il conseguente backtesting non
sono stati eseguiti.

**Le lacune di copertura del programma.** Tre argomenti del corso non sono
rappresentati nel progetto, e non per caso. I **Knowledge Graph e le ontologie**
non compaiono: la conoscenza del dominio e' rappresentata da un programma logico
con predicati fissati a priori, e non da una struttura a grafo con una gerarchia
di classi e proprieta' interrogabile; un'estensione naturale sarebbe descrivere
la rete di trasporto come ontologia, con una tassonomia dei tipi di fermata e di
servizio, e derivarne per sussunzione le proprieta' oggi codificate a mano. Le
**reti bayesiane** non compaiono: la dipendenza fra il ritardo alla salita e
quello alla discesa e' rappresentata da un condizionamento diretto, non da una
struttura grafica con piu' variabili e inferenza generale; una rete bayesiana
permetterebbe di aggiungere variabili esplicative come il meteo, il giorno della
settimana o lo stato del traffico, e di ragionare anche in senso diagnostico. Il
**soddisfacimento di vincoli** non compare come formalismo autonomo: i vincoli
del progetto sono vincoli di integrita' che rifiutano modelli incoerenti, non
variabili con domini su cui cercare un'assegnazione; un'estensione naturale
sarebbe la pianificazione di un viaggio con piu' tappe obbligate e finestre
temporali, che e' un problema di soddisfacimento di vincoli a pieno titolo.

**I limiti che vengono dai dati.** Nessuna delle due aziende pubblica
`transfers.txt`, quindi il primo livello della gerarchia dei tempi minimi di
trasbordo non riceve alcun fatto; solo due fermate in tutto il progetto
appartengono a una stazione, quindi neppure il secondo. Sui dati disponibili
l'eredita' difettibile collassa quasi ovunque sul terzo livello, e i primi due
sono collaudati solo su dati costruiti. Roma non dichiara l'accessibilita' di
alcuna fermata e non dichiara alcuna stazione, quindi la regola
dell'accessibilita' vi deriva zero conclusioni e ogni risultato su quel tema e'
riferibile alla sola Torino. Aggiungere una terza citta' con un archivio piu'
ricco renderebbe misurabile cio' che oggi e' soltanto rappresentabile.

**I limiti del modello geometrico.** La distanza fra due fermate e' quella in
linea d'aria e non quella effettivamente percorribile a piedi: in presenza di una
ferrovia, di un fiume o di una tangenziale fra due fermate vicine il tempo di
trasbordo derivato e' ottimistico. Integrare un grafo stradale eliminerebbe
l'approssimazione, al prezzo di una dipendenza da una fonte dati aggiuntiva. Il
tempo di cammino e' inoltre discretizzato in quattro bande anziche' calcolato con
continuita', scelta motivata dal fatto che un tempo di trasbordo ha senso al
mezzo minuto e non al metro, ma che resta un'approssimazione.

**I limiti della ricerca.** Il grafo copre una finestra di due ore a partire
dall'orario richiesto, e la ricerca trova percio' l'ottimo *dentro la finestra*:
su cinquanta coppie origine-destinazione per citta' la finestra si e' rivelata
sufficiente in quarantatre casi a Roma e trentanove a Torino, e sulle restanti
non esiste alcun itinerario nella finestra considerata. Quelle coppie non sono
state escluse dal campione, ma la loro esistenza limita la generalita' dei
risultati alle coppie collegate entro due ore. La ricerca impone inoltre un tetto
di quattro cambi, che e' un vincolo di realismo ma che interagisce con la
rappresentazione dello stato in modo non ovvio.

**I limiti del modello probabilistico.** Il numero di recuperi dopo una
coincidenza persa e' limitato a due, e sulle valutazioni della griglia il 9,2%
della massa di probabilita' esaurisce quel tetto: e' abbastanza da meritare una
menzione, e un valore piu' alto renderebbe il risultato piu' dipendente dal tetto
che dal modello. La scadenza e' definita in modo relativo all'itinerario piu'
veloce, scelta che aderisce alla domanda di ricerca ma che e' severa verso il
criterio probabilistico, e che rende il vantaggio misurato un limite inferiore.
Infine, l'insieme dei candidati e' la frontiera di Pareto, che collassa fra loro
gli itinerari differenti solo per il margine sulle coincidenze; la misura ha
mostrato che la frontiera e' comunque abbastanza ricca, ma un insieme candidato
costruito apposta nella dimensione dei margini resta un'estensione possibile.

# Riferimenti Bibliografici

[1] G. Brewka, T. Eiter, M. Truszczyński. *Answer Set Programming at a Glance*.
Communications of the ACM, 54(12):92-103, 2011.

[2] M. Gebser, R. Kaminski, B. Kaufmann, T. Schaub. *Multi-shot ASP solving with
clingo*. Theory and Practice of Logic Programming, 19(1):27-82, 2019. Sistema e
documentazione: <https://potassco.org/clingo/>.

[3] D. L. Poole, A. K. Mackworth. *Artificial Intelligence: Foundations of
Computational Agents*. 3ª edizione, Cambridge University Press, 2023.

[4] *General Transit Feed Specification (GTFS) Schedule Reference*.
<https://gtfs.org/schedule/reference/>.

[5] W. McKinney. *Data Structures for Statistical Computing in Python*.
Proceedings of the 9th Python in Science Conference, 2010.
Documentazione: <https://pandas.pydata.org/>.

[6] E. Q. V. Martins. *On a multicriteria shortest path problem*. European
Journal of Operational Research, 16(2):236-245, 1984.

[7] C. R. Harris et al. *Array programming with NumPy*. Nature, 585:357-362,
2020.

[8] P. Virtanen et al. *SciPy 1.0: fundamental algorithms for scientific
computing in Python*. Nature Methods, 17:261-272, 2020.

[9] F. Pedregosa et al. *Scikit-learn: Machine Learning in Python*. Journal of
Machine Learning Research, 12:2825-2830, 2011.

[10] *GTFS Realtime Reference*. <https://gtfs.org/realtime/reference/>.

[11] Roma Mobilità. Dati aperti del trasporto pubblico di Roma: orario statico
<https://romamobilita.it/sites/default/files/rome_static_gtfs.zip> e feed
real-time `rome_rtgtfs_trip_updates_feed.pb` e
`rome_rtgtfs_vehicle_positions_feed.pb` sullo stesso dominio.

[12] Gruppo Torinese Trasporti. Dati aperti del trasporto pubblico di Torino:
orario statico <https://www.gtt.to.it/open_data/gtt_gtfs.zip> e feed real-time
<https://percorsieorari.gtt.to.it/das_gtfsrt/>.

[13] J. D. Hunter. *Matplotlib: A 2D Graphics Environment*. Computing in Science
& Engineering, 9(3):90-95, 2007.
