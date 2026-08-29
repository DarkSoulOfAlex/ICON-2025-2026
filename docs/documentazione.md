---
title: "Un pianificatore di viaggi robusto ai ritardi"
lang: it
---

Gruppo di lavoro

- `<Nome Cognome 1>`, `<matricola 1>`, `<username1>@studenti.uniba.it`
- `<Nome Cognome 2>`, `<matricola 2>`, `<username2>@studenti.uniba.it`

`<URL_REPOSITORY>`

AA `<anno accademico>`

# Introduzione

Chi prende l'autobus non ha lo stesso problema di chi guida. L'automobilista che
parte in ritardo arriva in ritardo della stessa quantita'; chi viaggia sul
trasporto pubblico, se perde una coincidenza per un minuto, non arriva un minuto
dopo ma un quarto d'ora dopo, o mezz'ora, a seconda della frequenza della linea
successiva. Il tempo di viaggio non e' una grandezza continua, e' una scala a
gradini i cui scalini hanno l'altezza degli intervalli fra le corse.

Questo scarto fra il piccolo ritardo e la sua conseguenza e' la ragione per cui un
orario pubblicato non basta a pianificare un viaggio. Gli orari che le aziende di
trasporto distribuiscono nel formato GTFS sono orari **teorici**: dicono quando
una corsa dovrebbe passare, non quando passa. Le stesse aziende distribuiscono, in
un formato parallelo chiamato GTFS Real-Time, gli scostamenti osservati rispetto a
quell'orario, e la distanza fra i due e' abitualmente di minuti. Ogni
pianificatore di viaggi oggi in uso ignora questa distanza: costruisce
l'itinerario che, secondo l'orario teorico, arriva prima. Se quell'itinerario
contiene una coincidenza con due minuti di margine su una linea che accumula
regolarmente cinque minuti di ritardo, il pianificatore non ha modo di saperlo e
non ha modo di dirlo.

Il progetto affronta questo problema cambiando la grandezza da ottimizzare. Invece
di minimizzare l'orario di arrivo previsto dall'orario teorico, massimizza la
**probabilita' di arrivare entro un orario dato**, calcolata componendo lungo la
catena delle coincidenze le distribuzioni dei ritardi effettivamente osservati sul
campo. Le due grandezze non sono la stessa cosa riscritta: come il documento
mostra con una misura e non con un esempio, l'itinerario che le massimizza puo'
essere diverso, e quale sia il migliore dipende da quanto tempo si ha a
disposizione.

La domanda di ricerca e' percio' questa: **un itinerario scelto massimizzando
P(arrivo <= T) perde meno coincidenze di un itinerario scelto minimizzando
l'orario teorico, a parita' di tempo di viaggio nominale?** Il progetto e'
costruito su due citta' con reti e caratteristiche diverse, Roma e Torino, i cui
dati aperti sono raccolti in continuo da un sistema installato per lo scopo.

# Sommario

Il sistema e' un pianificatore di viaggi che integra cinque moduli, ciascuno
fondato su un formalismo diverso e ciascuno responsabile di una parte del
ragionamento che porta dalla domanda dell'utente all'itinerario proposto.

Il primo modulo e' una **base di conoscenza in Answer Set Programming** che
deriva, a partire dai dati grezzi del formato GTFS, la relazione di trasbordo fra
fermate: quali cambi siano possibili, quanto tempo richiedano come minimo, se
siano accessibili a un passeggero a ridotta mobilita', e quali fermate siano
collegate fra loro da una catena di cambi di lunghezza qualsiasi. Questa relazione
non esiste nei dati di partenza e viene interamente inferita, con regole che
esibiscono eredita' con eccezioni, non monotonia, ricorsione e vincoli di
integrita'.

Il secondo modulo e' una **ricerca su grafo tempo-espanso** che, data una coppia
origine-destinazione e un orario di partenza, produce l'insieme degli itinerari
non dominati su tre criteri: orario di arrivo, numero di cambi e minuti trascorsi
a piedi. Consuma la relazione di trasbordo prodotta dal primo modulo per costruire
gli archi di cambio, e restituisce al terzo un insieme di candidati fra cui
scegliere.

Il terzo modulo e' il **ragionamento in condizioni di incertezza** che assegna a
ciascun candidato la probabilita' di arrivare entro la scadenza, componendo le
distribuzioni dei ritardi lungo la successione delle coincidenze e tenendo conto
del fatto che una coincidenza persa non annulla il viaggio ma lo ritarda. E' il
modulo che realizza l'obiettivo del progetto, e quello rispetto al quale tutti gli
altri sono infrastruttura.

Il quarto modulo, in corso di realizzazione, e' l'**apprendimento delle
distribuzioni di ritardo** dai dati raccolti sul campo, che sostituira' il modello
provvisorio con cui il terzo modulo e' stato finora collaudato.

Il quinto modulo formula come **soddisfacimento di vincoli** il viaggio con piu'
tappe obbligate e finestre temporali: le tratte sono le variabili, gli itinerari
non dominati prodotti dal secondo modulo sono i domini, e due budget globali — sul
numero totale di cambi e sui minuti totali a piedi — legano fra loro scelte che
altrimenti sarebbero indipendenti.

I cinque moduli sono deliberatamente eterogenei, e la scelta non e' di comodo: il
problema si spezza lungo linee che corrispondono a formalismi diversi, perche'
derivare una relazione da regole con eccezioni, cercare in uno spazio di stati,
comporre distribuzioni di probabilita', stimare quelle distribuzioni dai dati e
soddisfare vincoli che legano scelte gia' compiute sono compiti che nessun singolo
formalismo affronta bene. Ogni modulo
espone agli altri un'interfaccia stretta ed e' collaudato e misurato per conto
proprio prima di essere composto; le quattro sezioni che seguono sono percio'
leggibili anche separatamente.

# Elenco argomenti di interesse

Gli argomenti trattati sono quattro, tratti da sezioni diverse del programma e qui
indicati esplicitamente con il riferimento al capitolo corrispondente del testo
adottato nel corso [1].

**Argomento 1 — Rappresentazione e ragionamento relazionale (cap. 15) e
rappresentazione della conoscenza proposizionale (cap. 5).** La relazione di
trasbordo fra fermate e' rappresentata da un programma logico in Answer Set
Programming che ne deriva l'esistenza, il tempo minimo, l'accessibilita' e la
chiusura transitiva. Il programma esibisce le proprieta' che distinguono una base
di conoscenza da una interrogazione su una base di dati: eredita' con default ed
eccezioni, non monotonia, ricorsione e vincoli di integrita' che rifiutano il
modello anziche' filtrare righe. La valutazione misura il costo di istanziazione
al crescere della rete su due citta' e individua quale regola lo domina.

**Argomento 2 — Ricerca di soluzioni (cap. 3).** La costruzione di un itinerario
e' formulata come ricerca su un grafo tempo-espanso in cui i nodi sono gli eventi
di passaggio e il costo di un arco dipende dall'istante in cui lo si percorre.
Sono impiegati A* con un'euristica geografica di cui si dimostrano ammissibilita'
e consistenza su questi dati, e una ricerca multi-criterio a etichette che
restituisce la frontiera delle soluzioni non dominate. La valutazione confronta A*
con Dijkstra, misura il costo della rappresentazione dello stato e quantifica il
guadagno di una relazione di dominanza fra stati.

**Argomento 3 — Ragionamento e incertezza (cap. 9).** La probabilita' di arrivare
entro una scadenza e' calcolata componendo le distribuzioni di ritardo lungo la
catena delle coincidenze, con una struttura markoviana in cui il ritardo si
propaga dentro una corsa e si azzera attraversando un cambio, e in cui una
coincidenza persa e' un ritardo anziche' un fallimento. La quantita' e' calcolata
in due modi indipendenti, per convoluzione numerica e per campionamento, e i due
sono confrontati fra loro. La valutazione confronta il criterio probabilistico con
tre strategie di riferimento su una griglia di scadenze.

**Argomento 4 — Apprendimento supervisionato (cap. 7) e apprendimento con
incertezza (cap. 10).** Le distribuzioni di ritardo che il terzo modulo compone
saranno stimate dai dati raccolti sul campo, con una stima condizionata alla
linea, alla fascia oraria, alla posizione lungo la corsa e al ritardo osservato a
monte. E' l'argomento attualmente in corso di realizzazione: la raccolta dei dati
e' completa e funzionante, la stima non e' ancora stata eseguita.

**Argomento 5 — Soddisfacimento di vincoli (cap. 4).** Il viaggio con piu' tappe
obbligate e' formulato come problema di vincoli: le variabili sono le tratte, i
domini gli itinerari non dominati che le percorrono, e i vincoli la precedenza fra
tappe consecutive, le finestre temporali a due estremi sulle tappe intermedie e
due budget globali sul numero di cambi e sui minuti a piedi. La valutazione
verifica, prima di ogni altra cosa, che il problema non sia risolubile tappa per
tappa senza tornare indietro: e' la condizione perche' la formulazione a vincoli
sia giustificata invece che decorativa.

# Sezione Argomento 1 — Rappresentazione e ragionamento relazionale

## Sommario

Il problema si formula come **derivazione di una relazione a partire da regole con
eccezioni**, nella forma trattata dal testo del corso per la rappresentazione
proposizionale e per quella relazionale [1, cap. 5 e cap. 15]. La particolarita'
di questo caso e' che la relazione da derivare — quali cambi fra fermate siano
possibili, quanto durino, per chi siano accessibili — non compare da nessuna parte
nei dati di partenza, e nessuna sua istanza puo' essere letta: ognuna e' una
conclusione. Il modulo e' percio' il punto in cui il progetto e' piu' esposto
all'obiezione che una base di conoscenza sia un database interrogato con un'altra
sintassi, ed e' anche il punto in cui quell'obiezione e' piu' facile da respingere.

Un pianificatore di viaggi ha bisogno di sapere, per ogni coppia di fermate, se un
passeggero possa passare dall'una all'altra e quanto tempo gli occorra come
minimo. Questa relazione, che chiameremo di *trasbordo*, e' il fondamento su cui
poggia il resto del sistema: la ricerca degli itinerari la usa per costruire gli
archi di cambio, e il calcolo di probabilita' la usa per stabilire quando una
coincidenza sia da considerarsi persa.

Lo standard GTFS [5] prevede un file facoltativo, `transfers.txt`, in cui
un'azienda puo' dichiarare quali cambi siano possibili e con quale tempo minimo.
Il contenuto degli archivi di entrambe le aziende del progetto e' stato
verificato: ne' Roma Mobilita' ne' GTT di Torino lo pubblica. L'archivio di Roma
contiene `agency.txt`, `calendar_dates.txt`, `routes.txt`, `shapes.txt`,
`stop_times.txt`, `stops.txt` e `trips.txt`; quello di Torino aggiunge alcuni file
non standard sulle tariffe e sui quadri orari, ma neppure lui contiene i
trasbordi. L'intera relazione va dunque derivata da cio' che i dati contengono
davvero: le coordinate delle fermate, la gerarchia che lega le banchine alle
stazioni, l'accessibilita' dichiarata di ciascuna fermata e l'elenco delle linee
che vi transitano.

**I fatti in ingresso.** La base di conoscenza riceve dal GTFS otto predicati: le
fermate fisiche con la loro posizione e la cella dell'indice spaziale a cui
appartengono; il legame fra una banchina e la stazione che la contiene; il valore
di accessibilita' dichiarato secondo la codifica dello standard, dove lo zero
significa "informazione non disponibile" e non "non accessibile"; l'elenco delle
coppie linea-fermata; e, quando esistono, i trasbordi dichiarati dall'azienda e le
segnalazioni contingenti di ascensori fuori servizio.

**Il tempo minimo di trasbordo, e la gerarchia delle fonti.** La regola piu'
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

La priorita' e' interamente affidata ai tre `not`: una regola di livello inferiore
si applica soltanto quando nessuna regola piu' specifica ha gia' concluso. E' la
forma che il testo del corso chiama eredita' con default ed eccezioni
[1, cap. 5], e non serve rispiegarla qui; cio' che vale la pena argomentare e' che
in **questo** problema non sia riducibile a un'interrogazione.

Un'interrogazione relazionale puo' riprodurre il risultato, ma solo scrivendo la
gerarchia delle priorita' dentro la query, tipicamente come catena di `COALESCE` o
sequenza ordinata di `LEFT JOIN`. La differenza non e' di eleganza ma di
collocazione della conoscenza: in quel caso la gerarchia vive nel codice
dell'interrogazione, e aggiungere un livello significa riscrivere la query; qui la
gerarchia e' dichiarata nella base di conoscenza, e aggiungere un livello
significa aggiungere una regola senza toccare le altre. Il collaudo verifica
esattamente la parte non riducibile: dichiarando un tempo per la sola direzione da
`A1` verso `A2`, quella direzione assume il valore dichiarato mentre la direzione
opposta, non dichiarata, resta governata dalla regola della stazione. La
sovrascrittura e' **puntuale**, come dev'essere un default, e non totale come
sarebbe l'effetto di un `COALESCE` scritto su un intero insieme di righe.

**L'accessibilita', e la direzione in cui cambiano le conclusioni.** La seconda
regola riguarda l'accessibilita' di un trasbordo per un passeggero a ridotta
mobilita'.

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

Il comportamento che interessa e' misurabile e viene misurato: dichiarando che
l'ascensore della fermata `A1` e' fuori servizio, **quattro** trasbordi che
risultavano accessibili smettono di esserlo, e **nessuno** ne prende il posto.
Aggiungere un fatto ha rimosso conclusioni. Il confronto vale perche' e' fatto
sull'insieme completo delle conclusioni prima e dopo, e controlla entrambe le
direzioni: che quattro siano sparite e che nessuna sia comparsa. Nessuna
interrogazione relazionale positiva puo' comportarsi cosi', perche' in algebra
relazionale l'aggiunta di tuple non riduce mai il risultato di una query positiva
[1, cap. 5].

Va notato che le eccezioni non sono tutte dichiarate: la prima e' **derivata**,
perche' un trasbordo a piedi diventa inaccessibile in forza della propria
distanza, senza che nessuno debba annotarlo. Anche l'antecedente
`fermata_accessibile` e' a sua volta un'eredita' con default, perche' lo standard
GTFS prescrive che il valore zero su una banchina significhi "eredita dalla
stazione": le due gerarchie sono percio' annidate, e la seconda alimenta la prima.

**La raggiungibilita', e perche' la profondita' non e' nota in anticipo.**

```prolog
raggiungibile(F, F) :- fermata(F).

raggiungibile(F1, F3) :-
    raggiungibile(F1, F2),
    trasbordo_ammissibile(F2, F3, _).
```

Due fermate sono collegate se esiste una catena di trasbordi di lunghezza
qualsiasi. La ricorsione non e' un artificio stilistico: il numero di cambi
necessari a collegare due punti di una rete non e' noto in anticipo e dipende
dalla topologia della citta', quindi nessun numero fissato di giunzioni puo'
sostituirla. Il collaudo verifica la parte che solo la ricorsione puo' produrre,
disponendo quattro fermate in fila a duecento metri l'una dall'altra: la distanza
e' sotto la soglia di duecentocinquanta metri per le coppie adiacenti e sopra per
quelle a un posto di distanza, quindi nessun trasbordo diretto collega la prima
alla terza, eppure la chiusura le collega, e collega anche la prima alla quarta.
Una variante della stessa regola calcola la chiusura sui soli trasbordi
accessibili; non e' una duplicazione ma un'altra domanda, perche' un percorso
esistente per un passeggero qualsiasi puo' non esistere per un passeggero in sedia
a rotelle, e distinguere le due raggiungibilita' e' precisamente il tipo di
conoscenza che il modulo vuole rappresentare.

**I vincoli di integrita', e perche' questi quattro.**

```prolog
:- fermata(F),
   #count { F2 : trasbordo_a_piedi(F, F2) } > grado_massimo_plausibile.

:- trasbordo_ammissibile(F1, F2, T), tempo_piedi(F1, F2, TP), T < TP.
```

Un vincolo di integrita' rifiuta il modello anziche' filtrare righe, ed e' percio'
di natura diversa da qualunque clausola `WHERE` [1, cap. 5]. Cio' che vale la pena
riportare e' il criterio con cui i quattro presenti sono stati scelti: **devono
poter scattare**. Alcuni vincoli inizialmente formulati sono stati scartati, per
esempio il divieto per una fermata di essere trasbordo di se stessa, perche' la
costruzione delle regole li rende impossibili per definizione, e un vincolo che
non puo' mai essere violato non e' logica ma un commento travestito da logica.
Ciascuno dei quattro rimasti corrisponde a un difetto documentato dei dati aperti:
il primo dei due riportati intercetta le fermate prive di coordinate, che nei feed
reali finiscono tutte nello stesso punto e formerebbero un nodo di scambio
inesistente ma enorme; il secondo intercetta i tempi di trasbordo dichiarati piu'
brevi del tempo materialmente necessario a percorrere la distanza a piedi, che
renderebbero il pianificatore sistematicamente troppo fiducioso e produrrebbero
coincidenze perse senza spiegazione apparente.

**La verifica che il programma sia stratificato.** Il programma ammette un unico
modello stabile, e non un insieme di risposte alternative fra cui scegliere,
purche' nessun predicato negato dipenda dal predicato che lo nega [1, cap. 5][3].
La condizione va verificata su questo programma, e la verifica e' diretta. La
negazione compare in cinque punti: nelle due regole di sovrascrittura del tempo
minimo, nella regola dell'accessibilita' e nella definizione di trasbordo utile,
che chiede l'esistenza di una linea servita dalla fermata di arrivo e non da
quella di partenza. `dichiarato` e' un fatto in ingresso e non dipende da nulla;
`stessa_stazione` dipende soltanto da `in_stazione`, anch'esso in ingresso;
`eccezione_accessibilita` dipende da `tempo_piedi`, da `trasbordo_ammissibile` e
dal fatto contingente sugli ascensori, ma **non** da `accessibile`; `serve` e' un
fatto in ingresso. Nessuno dei predicati negati dipende, nemmeno per via
indiretta, dal predicato che lo nega, quindi il grafo delle dipendenze non
contiene cicli che attraversino una negazione. L'unica ricorsione presente, quella
della raggiungibilita', e' puramente positiva e non interferisce.

**L'indice spaziale, e perche' non altera l'insieme delle conclusioni.** La regola
del trasbordo a piedi confronta coppie di fermate. Confrontarle tutte significa
istanziare un numero di atomi quadratico: sulle 8.301 fermate di Roma sono circa
69 milioni di coppie, e il grounding non termina in tempo utile. Ogni fermata
riceve percio' la cella di una griglia regolare, calcolata dalle sue coordinate, e
la regola confronta soltanto le fermate nella stessa cella o in una delle otto
adiacenti.

Va dichiarato che cosa questo accorgimento **non** e': non e' clustering, perche'
non c'e' nulla di appreso, nessun centroide, nessuna funzione obiettivo e nessuna
scelta dipendente dai dati; e' un'indicizzazione deterministica sulle coordinate.
Soprattutto non altera l'insieme delle conclusioni, e la ragione e' geometrica.
Sia `s` la soglia di cammino e sia `s` anche il lato della cella. Due fermate che
distino meno di `s` differiscono in ciascuna coordinata di meno di `s`, quindi i
loro indici di cella differiscono al piu' di uno in ciascuna delle due direzioni:
le loro celle sono percio' coincidenti o adiacenti, e la coppia viene confrontata.
Nessun trasbordo puo' sfuggire al confronto, e l'insieme derivato coincide con
quello della formulazione esaustiva. La scelta del lato non e' dunque libera: un
lato inferiore alla soglia spezzerebbe coppie che devono essere confrontate, e la
semantica cambierebbe. Poiche' un'argomentazione geometrica puo' sempre nascondere
un errore, la proprieta' e' anche verificata sperimentalmente, come riportato
nella valutazione.

**I dati di calendario, e una circostanza che ha cambiato il modulo.** La base di
conoscenza lavora sulla topologia della rete e non sul calendario, ma il
calendario e' un prerequisito di tutto il resto. Lo standard GTFS prevede due modi
complementari di dichiarare quando una corsa circoli: `calendar.txt` esprime una
regola settimanale con un periodo di validita', `calendar_dates.txt` esprime
eccezioni puntuali, additive o sottrattive. Lo standard richiede che almeno uno
dei due sia presente, non entrambi. Le due aziende usano i regimi opposti: Torino
pubblica `calendar.txt` con 1.106 servizi e `calendar_dates.txt` con 34.758
eccezioni, cioe' la forma canonica; Roma **non pubblica affatto** `calendar.txt`,
e ogni singolo giorno di servizio e' elencato come eccezione additiva nelle 4.707
righe di `calendar_dates.txt`. Entrambe le scelte sono conformi.

Un modulo scritto sull'assunzione implicita che `calendar.txt` esista
funzionerebbe su Torino e restituirebbe **zero corse attive su Roma**, senza
sollevare alcuna eccezione e senza somigliare in alcun modo a un errore. Avere due
citta' con regimi opposti ha trasformato una possibile fonte di errore silenzioso
in un caso di prova: la funzione che determina i servizi attivi parte da un
insieme vuoto quando la regola settimanale manca, applica le aggiunte e infine le
rimozioni, in quest'ordine, perche' una rimozione deve poter cancellare anche un
servizio introdotto da un'aggiunta dello stesso giorno.

Alla stessa categoria appartiene il trattamento degli orari oltre la mezzanotte.
Il GTFS ammette e usa regolarmente valori come `25:30:00`, che indicano l'una e
mezza di notte del giorno successivo ma appartengono al giorno di servizio
precedente. Riportarli sotto le ventiquattro ore, che e' la normalizzazione
istintiva, sposta silenziosamente tutte le corse notturne sul giorno sbagliato. Il
modulo li conserva percio' come secondi non normalizzati e traduce un orario in un
istante reale seguendo la definizione della specifica, secondo cui i tempi si
misurano da "mezzogiorno meno dodici ore" del giorno di servizio: nei giorni
ordinari coincide con la mezzanotte, nei due giorni all'anno in cui cambia l'ora
legale no, e la differenza e' esattamente un'ora su tutte le corse della giornata.

## Strumenti utilizzati

La base di conoscenza e' scritta in **Answer Set Programming** [2] e valutata con
il sistema **clingo** [4], che ne esegue il grounding e la risoluzione. Il
formalismo e' impiegato nella sua forma standard — regole normali con negazione
per fallimento, ricorsione, vincoli di integrita' e aggregati `#count` — e la
semantica dei modelli stabili con le relative condizioni di stratificazione e'
quella usuale [3], trattata nel testo del corso [1, cap. 5]. La rappresentazione
per predicati e variabili, con la quantificazione implicita sulle regole, segue
l'impostazione relazionale del medesimo testo [1, cap. 15]. La lettura degli
archivi GTFS [5] e la preparazione dei fatti usano **pandas** [6]; il collegamento
fra programma logico e Python usa l'API Python di clingo.

L'unico elemento non riconducibile a un modello noto e' l'argomentazione
geometrica che stabilisce l'equivalenza fra la regola indicizzata e quella
esaustiva, esposta nel sommario e verificata sperimentalmente nella valutazione.

## Decisioni di Progetto

**L'indice spaziale a griglia, con lato pari alla soglia.** Il lato della cella e'
di **250 metri**, uguale alla soglia di cammino, e la regola confronta ogni
fermata con quelle della propria cella e delle otto adiacenti. *Alternative
scartate:* il confronto esaustivo di tutte le coppie, che su Roma richiederebbe di
istanziare 69 milioni di coppie e non termina in tempo utile; e una griglia piu'
fitta, che sarebbe stata piu' selettiva ma avrebbe richiesto di ispezionare un
intorno piu' ampio di celle per conservare la correttezza, annullando il
vantaggio. *Perche' questo valore:* legare il lato alla soglia e' cio' che rende
l'equivalenza dimostrabile invece che sperimentale, come argomentato nel sommario;
un lato inferiore alla soglia cambierebbe la semantica, uno superiore
allargherebbe inutilmente i confronti. Il programma espone l'interruttore
`con_indice`, che sostituisce la regola indicizzata con quella esaustiva, e la sua
esistenza e' cio' che rende possibile la verifica sperimentale dell'equivalenza.

**La soglia di cammino: 250 metri.** E' la distanza massima entro cui due fermate
distinte sono considerate collegate a piedi. *Alternative scartate:* valori piu'
generosi, dell'ordine dei 400-500 metri, che sono la scelta abituale nella
letteratura sull'accessibilita' pedonale. *Perche' 250:* la distanza e' misurata
in linea d'aria e non lungo la rete stradale, quindi sottostima sistematicamente
il percorso reale; una soglia stretta limita l'errore di quella
approssimazione. Il valore governa anche il lato della cella, quindi il costo di
grounding, e la Tabella 4 ne mostra l'effetto sul numero di coppie candidate.

**Il tempo di percorrenza interno a una stazione: 180 secondi.** *Alternativa
scartata:* usare anche qui il tempo di cammino calcolato dalle coordinate.
*Perche' no:* due banchine della stessa stazione possono distare pochi metri in
linea d'aria ed essere separate da sottopassi, scale e tornelli, quindi la
distanza euclidea le farebbe apparire immediate; un valore fisso e piu' alto e'
meno preciso ma non e' sistematicamente ottimistico. Il valore incide oggi su due
sole fermate dell'intero progetto, come riportato nella valutazione.

**Il margine aggiunto al cammino all'aperto: 60 secondi.** Rappresenta il tempo
che non e' cammino — orientarsi, attraversare, individuare la banchina giusta.
*Alternativa scartata:* nessun margine, cioe' tempo di trasbordo uguale al solo
tempo di cammino. *Perche' no:* renderebbe il pianificatore ottimista proprio
sulle coincidenze strette, che sono quelle su cui l'intero progetto misura la
robustezza.

**Il tempo massimo di cammino per un passeggero in sedia a rotelle: 300 secondi.**
E' la soglia oltre la quale un trasbordo a piedi viene derivato come non
accessibile, ed e' l'eccezione *derivata* della regola dell'accessibilita'.
*Alternativa scartata:* considerare accessibile qualunque trasbordo fra due
fermate entrambe dichiarate accessibili. *Perche' no:* l'accessibilita' di un
cambio non e' solo una proprieta' delle due fermate ma anche della distanza fra
loro, e trascurarlo avrebbe reso la regola una semplice congiunzione di due fatti,
cioe' esattamente cio' che un'interrogazione relazionale sa gia' fare.

**Il grado massimo plausibile di trasbordi a piedi per fermata: 40.** E' la soglia
del primo vincolo di integrita'. *Perche' quel valore:* sulle reti reali il grado
osservato si attesta attorno a sette trasbordi per fermata a Roma e quattro e
mezzo a Torino, quindi quaranta e' abbondantemente sopra il caso peggiore
legittimo e scatta solo in presenza dell'anomalia che deve intercettare, cioe' le
fermate prive di coordinate che collassano tutte sullo stesso punto. Una soglia
vicina al grado osservato avrebbe prodotto falsi allarmi su ogni nodo di scambio
denso.

**Identificativi interi e coordinate in metri.** Gli identificativi testuali delle
fermate diventano numeri interi e le coordinate geografiche diventano metri interi
su una proiezione piana locale centrata sul baricentro delle fermate della citta'.
*Alternativa scartata:* passare al programma logico le stringhe e le coordinate in
gradi. *Perche' no:* il grounding su stringhe e' sensibilmente piu' lento, e i
confronti di distanza in gradi richiederebbero aritmetica in virgola mobile dentro
le regole. *Perche' non sposta conoscenza fuori dalla base:* la corrispondenza e'
biunivoca e viene conservata, il risultato si ritraduce esattamente, e il cambio
di unita' e' l'analogo del conservare gli orari in secondi anziche' nella forma
`HH:MM:SS`; la regola che stabilisce *quali* coppie costituiscano un trasbordo
resta interamente dentro il programma logico e opera sulle coordinate cosi' come
le riceve.

**Il tempo di cammino e' discretizzato in quattro bande.** *Alternativa scartata:*
il calcolo continuo del tempo dalla distanza. *Perche' no:* produrrebbe un valore
distinto per quasi ogni coppia, moltiplicando gli atomi da istanziare senza
aggiungere informazione utile, dato che un tempo di trasbordo ha senso al mezzo
minuto e non al metro. Resta un'approssimazione, dichiarata come tale fra i limiti
nelle conclusioni.

**I vincoli di integrita' sono scelti perche' possano essere violati.** Il
criterio e' esposto nel sommario. Sul piano del collaudo, tutti e quattro sono
verificati costruendo il dato che li viola, controllando che il programma diventi
insoddisfacibile e che torni soddisfacibile disattivando i soli vincoli:
altrimenti l'insoddisfacibilita' potrebbe venire da qualunque altra parte del
programma e il test non proverebbe nulla.

**Il campionamento per prossimita' dal baricentro geometrico.** Le sottoreti su
cui si misura la complessita' sono ottenute prendendo le N fermate piu' vicine a
un centro fisso, derivato dai dati come la fermata piu' vicina al baricentro
geometrico di tutte le fermate della citta': per Roma la **70841, S.
SABA/AVENTINO**, per Torino la **962, Fermata 1873 - PUGLIA C.3**. *Alternativa
scartata:* il campionamento casuale. *Perche' no:* cinquanta fermate estratte a
sorte fra le ottomila di Roma finirebbero sparse a chilometri l'una dall'altra e
non genererebbero quasi nessun trasbordo a piedi, quindi la curva misurerebbe il
costo di un problema che non somiglia a quello vero. *Perche' il centro non e'
scelto a mano:* un centro scelto a occhio renderebbe il campione una decisione
degli autori invece che una proprieta' dei dati. *Il prezzo, che va dichiarato:*
i risultati valgono per una porzione connessa e densa di rete e non sono
estrapolabili a un campione sparso di pari cardinalita'; la valutazione mostra che
questo limite si manifesta davvero, perche' la curva sovrastima il costo sulla
rete completa.

**Tre ripetizioni per ogni combinazione.** *Perche' tre e non una:* i tempi
dipendono dal carico della macchina e una singola esecuzione non ne
documenterebbe la variabilita'. *Perche' non di piu':* il numero di atomi e quello
di regole sono deterministici, quindi le ripetizioni informano solo sui tempi, la
cui dispersione risulta gia' contenuta a tre ripetizioni.

**La materializzazione per la ricerca esclude la chiusura transitiva.** La
relazione `raggiungibile` risponde a domande di connettivita' globale che il
pianificatore pone di rado, mentre `trasbordo_ammissibile`, quella effettivamente
consumata dal grafo tempo-espanso, e' molto piu' piccola e cresce linearmente. La
materializzazione destinata alla ricerca esclude percio' la chiusura, riducendo il
costo di un ordine di grandezza, e la calcola soltanto quando serva davvero. Che
la scelta si possa compiere a valle, disattivando l'interruttore `con_chiusura`
invece di riformulare le regole, e' una conseguenza diretta della natura
dichiarativa della rappresentazione.

## Valutazione

La misura risponde a due domande: fino a che dimensione di rete questa base di
conoscenza resta utilizzabile, e quale delle sue regole ne determina il costo.
Sono state misurate cinque dimensioni crescenti, da cinquanta a duemila fermate,
su entrambe le citta', con tre ripetizioni indipendenti per ogni combinazione. Per
ciascuna esecuzione si registrano il numero di atomi generati, il tempo di
grounding e il tempo di solving, tenuti separati perche' misurano due cose
diverse: il primo e' il costo di istanziare le regole sui dati, il secondo quello
di risolvere il programma proposizionale che ne risulta.

Una precisazione sulle deviazioni standard riportate. Il numero di atomi e quello
di regole sono grandezze **deterministiche**: a parita' di dati e di programma
clingo genera sempre la stessa istanziazione, la loro deviazione standard sulle
tre ripetizioni e' nulla per costruzione, e riportarla serve unicamente a
documentare che le ripetizioni sono state eseguite. La variabilita' reale sta nei
tempi.

Tabella 1 — Roma, media e deviazione standard su tre ripetizioni.

| Fermate | Atomi | Grounding (s) | Solving (s) | Trasbordi derivati |
| ---: | ---: | ---: | ---: | ---: |
| 50 | 7.334 ± 0 | 0,012 ± 0,001 | 0,0006 ± 0,0001 | 436 |
| 150 | 24.463 ± 0 | 0,048 ± 0,006 | 0,0015 ± 0,0001 | 1.096 |
| 400 | 70.612 ± 0 | 0,160 ± 0,048 | 0,0039 ± 0,0003 | 2.738 |
| 1000 | 724.410 ± 0 | 1,692 ± 0,139 | 0,0150 ± 0,0003 | 7.232 |
| 2000 | 2.358.444 ± 0 | 5,707 ± 0,753 | 0,0380 ± 0,0008 | 13.938 |

La tabella va letta per righe, perche' il salto e' fra la terza e la quarta. Fino
a quattrocento fermate la crescita e' quasi lineare nel numero di fermate: da 50 a
400, cioe' otto volte le fermate, gli atomi passano da 7.334 a 70.612, meno di
dieci volte, e i trasbordi derivati da 436 a 2.738, poco piu' di sei volte. Da 400
a 1000 gli atomi decuplicano, da 70.612 a 724.410, mentre le fermate solo si
duplicano e mezzo: e' li' che il comportamento cambia natura. Da 1000 a 2000, con
un semplice raddoppio delle fermate, gli atomi triplicano. I trasbordi derivati,
nel frattempo, continuano a crescere quasi linearmente — 7.232 e poi 13.938,
esattamente un raddoppio — il che localizza il fenomeno: non sono i trasbordi a
esplodere, ma qualcos'altro che li usa. Il tempo di grounding segue gli atomi
fedelmente, da 0,012 a 5,707 secondi, mentre il solving resta tre ordini di
grandezza sotto, da 0,0006 a 0,0380 secondi.

Tabella 2 — Torino, media e deviazione standard su tre ripetizioni.

| Fermate | Atomi | Grounding (s) | Solving (s) | Trasbordi derivati |
| ---: | ---: | ---: | ---: | ---: |
| 50 | 3.141 ± 0 | 0,005 ± 0,000 | 0,0003 ± 0,0000 | 164 |
| 150 | 13.862 ± 0 | 0,021 ± 0,000 | 0,0010 ± 0,0000 | 688 |
| 400 | 34.018 ± 0 | 0,052 ± 0,006 | 0,0024 ± 0,0002 | 1.616 |
| 1000 | 136.729 ± 0 | 0,245 ± 0,012 | 0,0072 ± 0,0008 | 4.498 |
| 2000 | 438.374 ± 0 | 0,910 ± 0,042 | 0,0190 ± 0,0029 | 9.542 |

Torino mostra la stessa forma ma spostata. Il salto da 400 a 1000 c'e' anche qui,
136.729 atomi contro 34.018, cioe' quattro volte, ma e' meno violento del
decuplicarsi di Roma; e a duemila fermate Torino si ferma a 438.374 atomi contro i
2.358.444 di Roma, un fattore 5,4 a parita' di numero di fermate. Sul piano dei
tempi la differenza e' pratica prima che teorica: 0,910 secondi contro 5,707 per
istanziare la stessa dimensione di problema. I trasbordi derivati crescono anche
qui quasi linearmente, 4.498 e poi 9.542.

![**Figura 1.** Costo della base di conoscenza al crescere del numero di fermate, in scala doppio logaritmica, per le due citta'. I pannelli (a), (b) e (c) riportano rispettivamente gli atomi generati, il tempo di grounding e il tempo di solving, come media su tre ripetizioni indipendenti con barre di deviazione standard; sugli atomi le barre sono nulle per costruzione, trattandosi di una grandezza deterministica. Il pannello (d) confronta la variante con indice spaziale, a linea continua, con quella che confronta tutte le coppie di fermate, a linea tratteggiata, eseguita solo fino a quattrocento fermate perche' oltre quella soglia il suo costo quadratico non aggiunge informazione. Dati grezzi in `results/complessita_kb.csv`.](../results/complessita_kb.png)

**Da dove nasce la crescita.** La pendenza delle curve in scala doppio logaritmica
e' l'esponente di crescita. Su tutto l'intervallo misurato gli atomi crescono come
`n^1,59` a Roma e come `n^1,30` a Torino, ma il dato interessante e' che la
pendenza **aumenta con la dimensione**: sull'ultimo raddoppio, da mille a duemila
fermate, entrambe le citta' si assestano attorno a `n^1,70`. Non e' una crescita
polinomiale di ordine fisso, e' una crescita che accelera. Disattivando la sola
ricorsione e rieseguendo la stessa istanza si ottiene l'attribuzione diretta,
senza doverla dedurre dalla forma della curva.

Tabella 3 — Quota di atomi generata dalla chiusura transitiva.

| Fermate | Roma | Torino |
| ---: | ---: | ---: |
| 50 | 31,5% | 32,2% |
| 150 | 45,7% | 35,2% |
| 400 | 52,6% | 35,7% |
| 1000 | 88,0% | 54,9% |
| 2000 | 92,9% | 70,4% |

Le due colonne raccontano la stessa storia a velocita' diverse. A cinquanta
fermate le due citta' sono indistinguibili, 31,5% e 32,2%: la ricorsione produce
meno di un terzo degli atomi e il costo e' dominato dalla generazione delle coppie
candidate e dal calcolo delle distanze. A centocinquanta le strade divergono, con
Roma al 45,7% e Torino ferma al 35,2%, e a quattrocento il divario si consolida,
52,6% contro 35,7%. Il salto avviene fra 400 e 1000 su Roma, dove la quota passa
dal 52,6% all'88,0%, e fra 1000 e 2000 su Torino, dal 54,9% al 70,4%: e' la stessa
transizione, traslata di un punto della griglia. A duemila fermate, su Roma, il
92,9% degli atomi nasce dalla sola chiusura transitiva, e ogni altra regola
contribuisce insieme per il restante sette per cento.

E' questa la regola che domina il grounding, e il motivo e' strutturale: la
chiusura transitiva di una relazione e' quadratica nella dimensione della
componente connessa su cui viene calcolata, e man mano che la sottorete si allarga
le fermate finiscono quasi tutte nella stessa componente. Le altre regole restano
invece lineari nel numero di coppie candidate, che l'indice spaziale mantiene
proporzionale al numero di fermate — ed e' esattamente cio' che si osserva nelle
Tabelle 1 e 2, dove i trasbordi derivati raddoppiano quando raddoppiano le
fermate.

Il tempo di solving, due ordini di grandezza inferiore a quello di grounding,
conferma la lettura. Il programma, una volta istanziato, e' sostanzialmente
deterministico: non ci sono scelte da compiere, perche' la negazione e'
stratificata e la ricorsione e' positiva, quindi il modello e' unico e il
risolutore non deve esplorare alcuno spazio di ricerca. **Il costo di questa base
di conoscenza e' interamente un costo di istanziazione, non di ricerca**, e ne
discende che ogni tentativo di ottimizzazione va rivolto alla forma delle regole e
non alla configurazione del risolutore.

**Perche' le due reti si comportano in modo diverso.** A parita' di numero di
fermate Roma costa costantemente piu' di Torino, e il divario si allarga: a
cinquanta fermate il rapporto fra gli atomi e' 2,3, a duemila e' 5,4. La
differenza non sta nelle dimensioni assolute delle due reti, che sono
confrontabili, 8.301 fermate contro 7.073, ma nella **densita' locale**. Nella
sottorete campionata attorno al centro, Roma deriva stabilmente attorno a sette
trasbordi per fermata, Torino attorno a quattro e mezzo. Un rapporto di densita'
di circa 1,5 diventa un rapporto di 5,4 sul numero di atomi proprio per via della
chiusura transitiva: una componente connessa piu' densa e' anche piu' grande, e il
costo della chiusura cresce con il quadrato della sua dimensione. E' il risultato
che giustifica l'aver misurato due citta' anziche' una, perche' con una sola rete
non si sarebbe potuto distinguere fra un costo intrinseco della formulazione e un
costo dipendente dalla topologia; con due si vede che la forma della crescita e'
la stessa e che a cambiare e' solo la costante.

**Il costo dell'indice spaziale, e la verifica della sua semantica.**

Tabella 4 — Atomi generati con e senza indice spaziale.

| Fermate | Roma, con | Roma, senza | Torino, con | Torino, senza |
| ---: | ---: | ---: | ---: | ---: |
| 50 | 7.334 | 10.222 | 3.141 | 7.377 |
| 150 | 24.463 | 63.727 | 13.862 | 55.330 |
| 400 | 70.612 | 375.992 | 34.018 | 345.082 |

Riga per riga, il risparmio non e' un fattore costante ma **cresce con il numero
di fermate**. A cinquanta fermate l'indice fa risparmiare 1,4 volte su Roma
(7.334 contro 10.222) e 2,3 su Torino (3.141 contro 7.377): poco, perche' su un
campione tanto piccolo quasi tutte le coppie sono comunque vicine. A
centocinquanta il rapporto sale a 2,6 e 4,0; a quattrocento arriva a 5,3 e 10,1.
La ragione e' che la variante esaustiva genera un numero di coppie quadratico
mentre quella indicizzata lo mantiene proporzionale al numero di fermate, quindi
il rapporto fra le due cresce linearmente. Vale la pena notare che il risparmio e'
maggiore su Torino, che e' la rete meno densa: dove le fermate sono piu' sparse
l'indice scarta una frazione maggiore di coppie, mentre su una rete fitta molte
coppie sono davvero vicine e vanno confrontate comunque. Estrapolando alla rete
intera di Roma, la variante esaustiva dovrebbe istanziare circa 69 milioni di
coppie, il che spiega perche' non sia praticabile a piena scala e perche' la riga
a 1000 e 2000 fermate manchi dalla tabella.

La verifica che conta non e' pero' quella sul costo ma quella sulla semantica. A
ogni dimensione in cui entrambe le varianti sono state eseguite l'insieme dei
trasbordi derivati e' risultato **identico**: stessi trasbordi, stessi tempi
minimi, stessi attributi di accessibilita' e di utilita'. L'indice restringe
l'ordine di istanziazione, non l'insieme delle conclusioni, e l'argomentazione
geometrica esposta nel sommario trova qui la sua conferma sperimentale.

**La rete intera.** La curva si ferma a duemila fermate perche' oltre quella
soglia il campionamento per prossimita' comincia a coincidere con la rete intera e
il confronto fra dimensioni perde significato. La rete intera e' pero' stata
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

Le righe vanno lette a coppie. **Fermate e fatti in ingresso** dicono che i due
problemi sono di taglia paragonabile: 8.301 contro 7.073 fermate, 55.894 contro
44.187 fatti, un rapporto di circa 1,25. **Atomi e tempo di grounding** dicono che
i due costi non lo sono affatto: 4,5 milioni contro 959 mila atomi, un rapporto di
4,7, e 11,3 contro 2,1 secondi, un rapporto di 5,4. Il fattore quattro di
differenza fra il rapporto degli ingressi e quello dei costi e' l'effetto della
densita' gia' discusso. **Il tempo di solving** conferma per l'ultima volta la
sproporzione: 0,09 secondi su Roma, cioe' meno di un centesimo del tempo speso a
istanziare. **I trasbordi derivati**, 41.266 e 21.130, sono la relazione che il
resto del sistema consumera', e il loro rapporto, 1,95, e' molto piu' vicino a
quello delle fermate che a quello degli atomi: l'uscita utile del modulo cresce
con la rete, non con il costo. **Di cui utili**, 24.554 e 11.439, dice che circa
tre trasbordi su cinque portano davvero a una linea nuova, quindi la regola di
utilita' scarta i due quinti restanti prima che diventino archi del grafo. **Di
cui accessibili**, 0 e 7.382, e' la riga che merita una discussione a parte.

L'intera base di conoscenza di Roma si istanzia in undici secondi e mezzo, costo
pienamente sostenibile per un'elaborazione da eseguire una volta al giorno, quando
l'orario statico cambia. Va segnalato che il numero di atomi sulla rete intera di
Roma, 4,5 milioni, e' **inferiore** ai 26 milioni che l'esponente `n^1,70` misurato
sull'ultimo raddoppio avrebbe fatto prevedere: la ragione e' che il campionamento
per prossimita' seleziona la porzione piu' densa della rete, quella centrale, e
allargandosi alla periferia la densita' cala, le componenti connesse si
frammentano e la chiusura transitiva cresce meno del previsto. E' la conferma
sperimentale del limite dichiarato fra le decisioni di progetto, e va letta come
tale: la curva misura correttamente il costo su porzioni dense di rete e
sovrastima quello sulla rete completa.

**Un risultato negativo sulla poverta' dei dati.** Delle 8.301 fermate di Roma,
**tutte** dichiarano `wheelchair_boarding` uguale a zero, che nella codifica dello
standard significa "informazione non disponibile"; lo stesso vale per il campo
corrispondente su tutte le 179.177 corse. Inoltre **nessuna** fermata di Roma
dichiara una `parent_station`: la gerarchia delle stazioni, in quell'archivio, non
esiste. Torino si comporta diversamente, con 2.722 fermate dichiarate accessibili,
1.075 esplicitamente non accessibili e 3.276 senza informazione, e 47.023 corse su
60.580 dichiarate accessibili; ma anche li' soltanto due fermate su 7.073
appartengono a una stazione.

Le conseguenze si leggono nella riga "di cui accessibili" della Tabella 5. Su Roma
la regola dell'accessibilita' deriva **zero** trasbordi accessibili: non perche'
sia sbagliata, ma perche' il suo antecedente non e' mai soddisfatto, dal momento
che nessuna fermata risulta accessibile e non esiste alcuna stazione da cui
ereditare il dato. Su Torino la stessa regola funziona e deriva 7.382 trasbordi
accessibili su 21.130, poco piu' di un terzo. Quanto alla gerarchia dei tempi
minimi, il suo primo livello non riceve alcun fatto su nessuna delle due citta',
perche' nessuna pubblica `transfers.txt`, e il secondo livello si applica a due
sole fermate in tutto il progetto: su questi dati l'eredita' con default collassa
quasi ovunque sul terzo livello, quello del cammino all'aperto piu' il margine.

Sarebbe disonesto presentare come funzionante una gerarchia a tre livelli di cui,
sul campo, ne opera stabilmente uno solo. Va detto con precisione che cosa questo
dimostri e che cosa no. **Dimostra** che la formulazione e' piu' generale dei dati
disponibili, il che e' una scelta deliberata: la base di conoscenza e' scritta per
il formato GTFS e non per due archivi particolari, e su un'azienda che pubblichi
`transfers.txt` e una gerarchia di stazioni i primi due livelli entrerebbero in
funzione senza modificare una riga. **Non dimostra** che quei livelli siano utili
in pratica su Roma e Torino, perche' su Roma e Torino non lo sono, e il loro
collaudo e' percio' affidato a dati costruiti. Ne discende inoltre una conseguenza
operativa per il resto del progetto: la distinzione fra `raggiungibile` e
`raggiungibile_accessibile`, sul piano della rappresentazione una delle parti piu'
interessanti, e' misurabile soltanto su Torino, e ogni risultato
sull'accessibilita' va riferito a quella citta' e non alla media delle due.

# Sezione Argomento 2 — Ricerca di soluzioni

## Sommario

Il problema si formula come **ricerca su grafo di stati** [1, cap. 3], con tre
particolarita' che lo distinguono dal caso trattato nel testo del corso e che sono
l'oggetto di questa sezione. La prima e' che il costo di un arco dipende
dall'istante in cui lo si percorre, perche' fra una corsa e la successiva si
aspetta: lo stato deve percio' includere il tempo, e la rappresentazione adottata
e' quella tempo-espansa, in cui i nodi sono gli eventi di passaggio anziche' le
fermate [7]. La seconda e' che lo stato deve includere anche il numero di cambi
gia' effettuati, che e' insieme un criterio di valutazione e un vincolo. La terza
e' che non esiste una funzione di costo scalare: i criteri sono tre e non
commensurabili, quindi la ricerca non restituisce una soluzione ma un insieme di
soluzioni non dominate [9].

La domanda a cui il pianificatore deve rispondere non e' "qual e' il percorso piu'
corto fra A e B" ma "partendo da A alle otto, qual e' il primo momento in cui posso
essere in B". Gli archi di cambio fra fermate diverse sono quelli derivati dalla
base di conoscenza descritta nell'argomento precedente, che stabilisce quali
trasbordi esistano e quanto tempo richiedano come minimo. Il costo che si
minimizza e' l'**orario di arrivo**, non la durata del viaggio: partire piu' tardi
non e' peggio se si arriva prima, mentre minimizzando la durata si preferirebbe un
viaggio di venti minuti che parte fra due ore a uno di venticinque che parte
adesso, il che non e' quello che chiede chi sta alla fermata.

**Perche' la terna non basta, e come lo stato si sdoppia.** Lo stato naturale
sarebbe la terna `(fermata, istante, cambi effettuati)`, ma la terna da sola non
e' sufficiente a contare correttamente i cambi. Stando a una fermata a un dato
istante, "restare a bordo" e "salire di nuovo" sono situazioni indistinguibili se
non si sa su quale corsa ci si trovi: un viaggiatore che percorre dieci fermate
senza mai scendere passerebbe per dieci stati successivi, ciascuno dei quali
sembrerebbe una salita, e la ricerca gli attribuirebbe dieci cambi. Il conteggio
dei cambi, che e' uno dei tre criteri, sarebbe sistematicamente sbagliato senza
che nulla lo segnali: non produrrebbe un errore ma itinerari valutati male.

Lo stato si sdoppia percio' in due forme che condividono la terna come parte
osservabile. **A terra** si e' a una fermata, a un certo istante, dopo un certo
numero di cambi, e da li' si puo' salire su una corsa, trasbordare verso una
fermata vicina o camminare. **A bordo** si e' su una corsa specifica, appena
arrivati a un suo passaggio, e da li' si puo' proseguire senza cambiare oppure
scendere. L'identita' della corsa e' l'unica informazione aggiuntiva rispetto alla
terna, ed e' quella che rende il conteggio corretto per costruzione anziche' per
convenzione. Il cambio si conta alla **salita** e non alla discesa: scendere a
destinazione costerebbe altrimenti un cambio che il viaggiatore non percepisce, e
due itinerari identici tranne che per la fermata finale risulterebbero diversi su
un criterio.

**La dimostrazione che questa euristica e' ammissibile.** La ricerca mono-criterio
usa A* [1, cap. 3][8] con un'euristica che divide la distanza in linea d'aria fra
la fermata corrente e la destinazione per la velocita' massima presente nella
rete. L'ammissibilita' non e' una proprieta' generale di questa forma: dipende da
come `V` viene scelto su questi dati, e va percio' dimostrata.

Sia `n` uno stato la cui fermata dista `d` metri in linea d'aria dalla
destinazione, e sia `V` la velocita' massima fra due fermate consecutive presente
nell'orario. Ogni itinerario che porti da `n` alla destinazione e' una successione
finita di spostamenti fra fermate. La somma delle loro lunghezze non puo' essere
inferiore a `d`, perche' il segmento e' il cammino piu' breve fra due punti del
piano e la spezzata che li congiunge e' almeno altrettanto lunga. Ciascuno di
quegli spostamenti impiega almeno la propria lunghezza divisa `V`, perche' `V` e'
per costruzione un limite superiore alla velocita' di ogni spostamento della rete.
Il tempo residuo reale e' percio' almeno `d / V`, che e' il valore restituito
dall'euristica. Le attese alle fermate e i tempi minimi di trasbordo si sommano a
quel tempo e possono solo aumentarlo, quindi non intaccano il limite. L'euristica
non sovrastima mai il costo residuo, ed e' percio' ammissibile.

L'euristica e' inoltre **consistente**, perche' e' della forma `d(x)/V` con `d`
distanza euclidea, che soddisfa la disuguaglianza triangolare: per ogni arco da
`x` a `y` di costo `c` vale `h(x) <= c + h(y)`, dal momento che la distanza
euclidea fra `x` e la destinazione non supera la somma della distanza fra `x` e
`y` e di quella fra `y` e la destinazione, e che `c` non e' inferiore al tempo
minimo per coprire il tratto da `x` a `y`. Ne segue che ogni stato viene estratto
dalla coda gia' con il suo costo definitivo e non e' necessario riaprirlo.

La dimostrazione e' verificata anche per campionamento: un test estrae stati a
caso, calcola il costo residuo reale con una ricerca esaustiva e controlla che
l'euristica non lo superi mai. La verifica serve perche' un'euristica non
ammissibile non solleverebbe alcun errore e non rallenterebbe nulla: restituirebbe
semplicemente itinerari peggiori, in silenzio.

**Perche' i tre criteri non si riducono a uno.** Ogni itinerario e' valutato su
orario di arrivo, numero di cambi e minuti trascorsi a piedi. Ridurli a una sola
grandezza richiederebbe di decidere quanto valga un cambio espresso in minuti, e
la risposta dipende da chi viaggia: chi porta una valigia, chi ha poco tempo e chi
ha difficolta' motorie darebbero tre risposte diverse, e nessuna e' piu' corretta
delle altre. Un itinerario che arriva cinque minuti prima ma con un cambio in piu'
non e' migliore ne' peggiore, e' un altro compromesso. Cio' che si puo' invece
affermare senza arbitrio e' che un itinerario non serve a nessuno se ne esiste un
altro non peggiore su tutti e tre i criteri e strettamente migliore su almeno uno:
la ricerca restituisce percio' l'insieme delle soluzioni non dominate [9],
lasciando la scelta finale a chi viaggia — o, nel caso di questo progetto, al
criterio probabilistico dell'argomento successivo, che consuma esattamente
quell'insieme.

**Il modello dei ritardi non entra in questa fase.** Va detto esplicitamente,
perche' e' una scelta di perimetro e non un'omissione: la ricerca descritta qui
lavora sull'orario **programmato** e non usa in alcun modo i ritardi.

## Strumenti utilizzati

La ricerca mono-criterio impiega **A\*** [8] e, come termine di paragone senza
euristica, l'algoritmo di **Dijkstra**; entrambi sono usati nella loro forma
standard e sono trattati nel testo del corso [1, cap. 3], insieme alle nozioni di
ammissibilita' e consistenza di un'euristica. La rappresentazione tempo-espansa
del problema di orario e' quella descritta da Pyrga e altri [7]. La ricerca
multi-criterio e' una ricerca a etichette con potatura per dominanza, nella forma
abituale per i problemi di cammino multi-obiettivo [9]. La coda di priorita' e'
quella della libreria standard di Python, `heapq`; il calcolo delle distanze e la
manipolazione delle strutture del grafo usano **numpy** [10]; le figure sono
prodotte con **matplotlib** [17].

Sono originali di questo progetto, e per questo esposti nel sommario e fra le
decisioni di progetto anziche' qui, la dimostrazione di ammissibilita' e
consistenza dell'euristica geografica su questi dati e la relazione di dominanza
fra stati a terra su cui si fonda la scelta della chiave di stato.

## Decisioni di Progetto

**Il grafo copre una finestra temporale di 120 minuti, non la giornata.** Il grafo
parte dall'orario di partenza richiesto e dura un orizzonte prefissato.
*Alternative scartate:* costruire il grafo dell'intera giornata di servizio,
oppure adottare la rappresentazione tempo-dipendente, che comprime il tempo negli
archi anziche' espanderlo nei nodi. *Perche' no alla giornata:* l'orario di Roma
contiene 5,6 milioni di passaggi al giorno, e il grafo corrispondente non e' un
oggetto che si costruisca per rispondere a una singola interrogazione. *Perche'
120 minuti:* e' anche cio' che una interrogazione usa davvero, perche' nessuno
accetta di attendere quattro ore alla fermata; la Tabella 6 mostra che l'orizzonte
di due ore costa dodici megabyte su Roma, cioe' abbastanza poco da poter
ricostruire il grafo a ogni interrogazione invece di conservarlo. *Il prezzo, che
e' una limitazione dei risultati e non una nota implementativa:* la ricerca trova
l'ottimo **dentro la finestra**, e un itinerario che richiedesse di attendere
oltre l'orizzonte non verrebbe trovato affatto. La valutazione riporta su quante
coppie la finestra si sia rivelata sufficiente, e quel numero e' esso stesso un
risultato.

**La chiave di stato a terra non contiene l'istante.** E' la decisione che ha
avuto l'effetto piu' grande sul costo della ricerca. *Alternativa scartata:* la
lettura letterale della terna, che era l'implementazione iniziale e che tratta
come distinti due arrivi alla stessa fermata in istanti diversi. E' corretta, ma
su una finestra di due ore produce centinaia di stati per ogni fermata, uno per
ogni orario a cui vi si possa arrivare.

*Perche' si puo' fare a meno dell'istante.* Vale una relazione di dominanza:
trovarsi alla stessa fermata, con lo stesso numero di cambi, ma **prima**, e'
sempre almeno altrettanto buono. Ogni prosecuzione disponibile allo stato piu'
tardivo e' disponibile anche a quello piu' precoce, perche' le corse partono agli
stessi orari per entrambi e le azioni possibili da una fermata dipendono
dall'istante solo attraverso il vincolo di non poter salire su una corsa gia'
partita; un istante anteriore rilassa quel vincolo senza irrigidirne altri, e
attendere non costa nulla. Gli stati con istante posteriore sono percio' dominati.
Identificando uno stato a terra con la sola coppia `(fermata, cambi)` e
conservando l'istante di arrivo piu' precoce, quegli stati spariscono senza che
alcuna soluzione vada perduta: non e' un'approssimazione, e l'ottimo resta
garantito. Le due formulazioni convivono nel codice, perche' altrimenti il
confronto non sarebbe riproducibile: il parametro `istante_nella_chiave` riattiva
quella storica.

**Il tetto sul numero di cambi: quattro.** *Perche' esiste:* e' un vincolo di
realismo prima che di costo, perche' un itinerario con sei cambi non verrebbe
scelto da nessuno. *Perche' quattro:* sulle reti esaminate la frontiera di Pareto
contiene mediamente cinque soluzioni con un numero di cambi ben inferiore, quindi
il tetto non taglia soluzioni che sarebbero state scelte. *La conseguenza non
ovvia:* il tetto interagisce con la rappresentazione dello stato, e la valutazione
mostra che rimuovere i cambi dalla chiave di stato in sua presenza produce
itinerari sbagliati.

**L'euristica usa il massimo vero delle velocita', difetti dell'orario compresi.**
`V` e' il massimo effettivo delle velocita' fra fermate consecutive presenti
nell'orario: **297,1 km/h a Roma e 500,8 a Torino**. *Alternativa scartata:* un
valore fisicamente plausibile per un mezzo urbano, per esempio 80 km/h. *Perche'
no:* il limite deve valere per il grafo che si sta cercando, non per la fisica;
se l'orario dichiara un movimento, quel movimento nel grafo esiste, e
un'euristica tarata su una velocita' inferiore lo sovrastimerebbe, perdendo
l'ammissibilita' dimostrata nel sommario. *Alternativa scartata, la seconda:*
correggere l'orario eliminando gli archi anomali. *Perche' no:* significherebbe
modificare il dato in ingresso per far funzionare meglio un algoritmo, e il
progetto misura il comportamento del metodo sui dati reali, difetti compresi. La
valutazione riporta il costo di questa scelta, che e' alto.

**Una variante non ammissibile, come confronto e solo come confronto.** Per
quantificare quanto costi l'ammissibilita' e' stata implementata anche una
variante con `V` pari al **99,9-esimo percentile** delle velocita' invece che al
massimo: 55,2 km/h a Roma e 82,0 a Torino. *Perche' il p99,9 e non un altro
percentile:* e' il valore piu' alto fra quelli fisicamente plausibili, quindi
massimizza il confronto restando difendibile come scelta ingegneristica; un
percentile piu' basso avrebbe reso l'euristica piu' aggressiva ma il confronto
meno informativo. *Perche' non diventa la variante predefinita:* **non e'
ammissibile** e A* non garantisce piu' l'ottimo. E' dichiarata come tale ovunque
compaia — nel codice, nella colonna `tipo_velocita` di
`results/ricerca_astar.csv`, che marca ogni riga con il valore di `V` usato e con
la sua natura, e nella didascalia della Figura 2. La variante ammissibile resta
l'unica che produce risultati ufficiali del progetto.

**Cinquanta coppie origine-destinazione per citta', estratte con un seme
dichiarato.** *Perche' un campione e non tutte le coppie:* le coppie possibili su
Roma sono circa 34 milioni. *Perche' cinquanta:* e' il numero che rende
l'esperimento completo eseguibile in pochi minuti anche nella variante storica
della chiave di stato, che impiega decine di secondi per interrogazione. *Perche'
un seme dichiarato:* il campione dev'essere riproducibile, altrimenti il confronto
fra varianti misurerebbe anche la fortuna dell'estrazione. Le coppie sono estratte
fra le fermate effettivamente servite nella finestra, perche' una fermata senza
corse nella finestra produrrebbe un'interrogazione senza soluzione per ragioni che
non riguardano la ricerca.

**Le coppie irrisolte non vengono escluse dal campione.** *Alternativa scartata:*
riestrarre finche' tutte le cinquanta coppie sono risolvibili. *Perche' no:*
darebbe una falsa impressione di completezza e nasconderebbe proprio il limite
della finestra temporale, che e' un risultato da riportare.

## Valutazione

Il confronto e' stato eseguito su cinquanta coppie origine-destinazione per
citta', con partenza alle 08:00 e orizzonte di 120 minuti. Le varianti condividono
lo stesso codice e differiscono solo per l'euristica o per la chiave di stato,
cosi' che il confronto isoli l'elemento in esame.

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

La lettura per righe mostra una crescita **fortemente sublineare**. Sedici volte
la finestra, da 15 a 240 minuti, moltiplica gli eventi di Roma solo per 2,6, da
120.725 a 315.000, e gli archi per 3,0, da 291.306 a 871.117. Quadruplicando
l'orizzonte da 60 a 240 minuti gli archi poco piu' che raddoppiano, da 410.436 a
871.117. La ragione si legge nel confronto fra la prima riga e la differenza fra
le righe: a quindici minuti il grafo di Roma ha gia' 291.306 archi, e i trasbordi
a terra derivati dalla base di conoscenza sono 41.266 a Roma e 21.130 a Torino,
gli stessi a qualunque ora. Una parte cospicua del grafo non dipende dunque dalla
finestra, ed e' quella parte a rendere il primo punto tanto alto e la pendenza
successiva tanto bassa. Torino si comporta allo stesso modo con costanti minori,
da 50.548 a 118.263 eventi. La colonna dei megabyte e' quella che decide la
strategia: il grafo di due ore di Roma occupa 11,9 MB, e anche quello di quattro
ore ne occupa 17,0, quindi ricostruirlo a ogni interrogazione e' praticabile e
conservarlo non serve.

Sulle cinquanta coppie esaminate per citta' la finestra di due ore si e' rivelata
sufficiente in **43 casi su 50 a Roma e 39 su 50 a Torino**, cioe' nell'86% e nel
78%. Le sette e le undici coppie rimaste corrispondono a collegamenti che nella
finestra considerata non esistono, tipicamente fra periferie opposte servite da
linee a bassa frequenza. Non sono state escluse dal campione: la loro percentuale
e' essa stessa un risultato, e delimita la generalita' di tutto cio' che segue
alle coppie collegate entro due ore.

**La relazione di dominanza vale due ordini di grandezza.** La misura che ha fatto
scoprire il fenomeno riguarda un'interrogazione di Torino, su cui la formulazione
con l'istante nella chiave espandeva **6,4 milioni di stati in 224 secondi**,
mentre quella con la chiave ridotta ne espande **45 mila in 0,7 secondi**,
restituendo lo stesso orario di arrivo. Poiche' quella prima interrogazione non
era stata estratta con un seme dichiarato, l'esperimento e' stato ripetuto in
forma riproducibile sulla prima coppia risolta del campione di Torino, la
3176 → 3492 estratta con il seme 20260826.

| Formulazione dello stato a terra | Stati espansi | Secondi |
| --- | ---: | ---: |
| `(fermata, istante, cambi)` | 1.464.312 | 60,39 |
| `(fermata, cambi)` | 23.597 | 0,61 |

Su questa coppia il rapporto e' di 62 volte sugli stati e di 99 volte sul tempo,
con lo stesso identico orario di arrivo. Che il rapporto sul tempo superi quello
sugli stati non e' un'anomalia: la coda di priorita' cresce con il numero di stati
aperti, quindi ogni singola estrazione costa di piu' quando gli stati sono
milioni. La coincidenza degli orari di arrivo prima e dopo conferma
sperimentalmente l'argomentazione di dominanza esposta fra le decisioni di
progetto. Vale la pena osservare che senza questa riformulazione l'intera campagna
sperimentale finale, che prevede migliaia di interrogazioni, non sarebbe
eseguibile: a duecento secondi per interrogazione, mille interrogazioni
richiederebbero due giorni e mezzo di calcolo.

**L'euristica geografica: un risultato negativo.**

Tabella 7 — Confronto delle varianti di ricerca. Media e deviazione standard sulle
coppie risolte: 43 per Roma, 39 per Torino. La colonna "non ottime" conta le
interrogazioni in cui la variante restituisce un orario di arrivo diverso da
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

Le righe vanno confrontate a gruppi di tre. Su **Roma**, Dijkstra espande 37.156
stati in 0,514 secondi; A* ammissibile ne espande 34.391, cioe' il 7,7% in meno,
ma impiega 0,743 secondi, cioe' il 44% in **piu'**. Su **Torino** il quadro e'
identico e piu' netto: 13.783 stati contro 13.301, un risparmio del 3,8%, e 0,201
secondi contro 0,311, cioe' il 55% in piu'. Il risultato principale e' dunque
negativo, e conviene enunciarlo senza attenuazioni: **l'euristica ammissibile
risparmia meno del dieci per cento degli stati e fa impiegare ad A\* piu' tempo di
Dijkstra**. Calcolare l'euristica costa piu' dei nodi che fa evitare.

Le colonne delle deviazioni standard meritano una nota: sono dello stesso ordine
delle medie — 32.062 su 37.156 stati a Roma — perche' le coppie
origine-destinazione hanno difficolta' molto diverse fra loro, dalle vicine alle
attraversamenti completi della citta'. La dispersione riguarda le interrogazioni,
non la misura, e infatti la colonna del risparmio, che confronta le varianti
sulla **stessa** interrogazione, ha deviazione standard molto piu' contenuta:
2,6% su una media del 7,7%.

La colonna `V` spiega il fallimento. L'ammissibilita' obbliga a scegliere il
massimo vero delle velocita', che vale 82,5 m/s a Roma e 139,1 a Torino, cioe'
**297,1 e 500,8 km/h**. Quei valori non vengono da coordinate sbagliate, come si
potrebbe supporre, ma dalla tabella oraria: gli archi anomali coprono distanze del
tutto ordinarie, duecento o quattrocento metri, in **tre secondi di orario
programmato**. Sono 135 archi su 1.752.603 a Torino e 1.063 su 5.343.307 a Roma.
Con un `V` di cinquecento chilometri orari l'euristica stima in pochi secondi un
tempo residuo che ne vale centinaia, resta quasi ovunque prossima a zero, e A* si
comporta quasi come Dijkstra pagando in piu' il calcolo della distanza. Che il
difetto sia piu' grave su Torino — 500,8 contro 297,1 km/h — spiega perche' il
risparmio sia li' ancora minore, 3,8% contro 7,7%.

Tabella 8 — Distribuzione delle velocita' fra fermate consecutive, misurata
sull'orario programmato.

| Citta' | Archi | Mediana | p99 | p99,9 | Massimo | Sopra 150 km/h |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Roma | 5.343.307 | 15,6 km/h | 34,4 km/h | 55,2 km/h | 297,1 km/h | 1.063 |
| Torino | 1.752.603 | 16,4 km/h | 56,2 km/h | 82,0 km/h | 500,8 km/h | 135 |

Questa tabella e' la diagnosi del problema, e va letta da sinistra a destra. Le
**mediane** sono quasi identiche e del tutto plausibili, 15,6 e 16,4 km/h: le due
reti, nel caso tipico, si comportano come ci si aspetta da un mezzo urbano. Il
**p99** resta ragionevole, 34,4 e 56,2 km/h, valori compatibili con tratte
extraurbane o metropolitane. Il **p99,9** e' ancora difendibile, 55,2 e 82,0 km/h.
Il **massimo** e' fuori scala: 297,1 e 500,8 km/h. Fra il p99,9 e il massimo c'e'
dunque un fattore 5,4 su Roma e 6,1 su Torino, concentrato in una frazione di
archi che l'ultima colonna quantifica: 1.063 su 5,3 milioni e 135 su 1,75
milioni, cioe' lo 0,02% e lo 0,008%. **Meno di un arco su cinquemila determina il
valore di `V`, e con esso l'efficacia dell'euristica su tutti gli altri.** E' la
ragione per cui il risultato negativo non e' un fallimento del metodo ma il metodo
che funziona correttamente su dati imperfetti.

La variante non ammissibile, tarata sul p99,9, risparmia il 35,8% e il 20,6% degli
stati, da quattro a cinque volte piu' dell'ammissibile, e su Roma riesce anche a
essere piu' rapida di A* ammissibile, 0,586 secondi contro 0,743, pur restando
sopra Dijkstra. Il dato piu' interessante e' pero' nell'ultima colonna: **su
nessuna delle 82 interrogazioni risolte la variante non ammissibile ha restituito
un orario di arrivo diverso dall'ottimo**. La garanzia formale e la sua violazione
pratica sono due cose distinte, e i dati dicono che su questa rete la seconda non
si manifesta. Cio' non autorizza a rinunciare alla garanzia: un campione di
ottantadue interrogazioni non dimostra che non esista una coppia su cui la
variante sbagli, e la differenza fra "non abbiamo trovato controesempi" e "non
esistono controesempi" e' esattamente cio' che una dimostrazione fornisce e una
misura no.

**Il costo dei cambi nello stato, e perche' non e' spreco.** Tenere il numero di
cambi nello stato moltiplica lo spazio di ricerca. La variante che proietta via i
cambi, identificando uno stato a terra con la sola fermata, espande **11.734 stati
contro 34.391 a Roma** e **4.817 contro 13.301 a Torino**, cioe' circa un terzo in
entrambe le citta'. Preso da solo, il numero suggerirebbe che i cambi nello stato
costino un fattore tre di lavoro inutile, e che rimuoverli sia un'ottimizzazione
gratuita.

La misura dice pero' anche un'altra cosa, che il solo conteggio degli stati
nasconderebbe: la variante proiettata **restituisce l'itinerario sbagliato su 5
interrogazioni su 40 a Roma e su 4 su 39 a Torino**, cioe' su nove su
settantanove, oltre l'undici per cento.

Il meccanismo e' stato isolato sperimentalmente ed e' l'interazione con il tetto
di quattro cambi. Con i cambi proiettati via, uno stato raggiunto per primo
attraverso un percorso che ha gia' speso quattro cambi viene marcato come
visitato, e un percorso successivo che vi arrivi con un solo cambio viene scartato
perche' non migliora l'orario di arrivo — salvo che quel secondo percorso avrebbe
potuto proseguire per altri tre cambi, mentre il primo era esaurito. La
dominanza, in altre parole, non vale piu': arrivare prima non e' sufficiente se si
arriva con meno cambi residui. La verifica decisiva e' la ripetizione
dell'esperimento con un tetto di dodici cambi, che porta le discrepanze a **zero**
su entrambe le citta': conferma che la causa e' il tetto e non un difetto della
proiezione in se'. Il fattore tre non e' dunque spreco ma il **prezzo della
correttezza** in presenza di un vincolo sul numero di cambi, ed e' anche la
ragione per cui il progetto mantiene una sola struttura di stato invece di due
implementazioni: la variante proiettata esiste unicamente come termine di paragone
di questa misura.

**La frontiera di Pareto sui dati reali.** La ricerca multi-criterio restituisce
in media **5,72 ± 2,83 soluzioni non dominate a Roma** e **5,05 ± 2,89 a Torino**.
Il numero e' significativo: se esistesse un itinerario ottimo unico la frontiera
ne conterrebbe uno solo, e la deviazione standard sarebbe nulla. Che ne contenga
mediamente cinque, con una dispersione ampia, significa che su una tipica coppia
origine-destinazione ci sono cinque compromessi genuinamente diversi fra
rapidita', numero di cambi e minuti a piedi, e che il loro numero varia molto da
coppia a coppia. E' precisamente il fatto che rende interessante la domanda di
ricerca del progetto: se l'itinerario ottimo fosse unico, massimizzare la
probabilita' di arrivo entro un orario si ridurrebbe a un problema di
riordinamento, e non ci sarebbe nulla da scegliere.

![**Figura 2.** Costo del grafo ed effetto dell'euristica, su cinquanta coppie origine-destinazione per citta' con partenza alle 08:00 e finestra di 120 minuti. Il pannello (a) riporta la crescita del grafo con l'orizzonte temporale, in scala doppio logaritmica. Il pannello (b) confronta gli stati espansi da A* ammissibile con quelli di Dijkstra sulle stesse interrogazioni: la nuvola aderisce alla bisettrice, che e' la rappresentazione visiva del risparmio quasi nullo. Il pannello (c) confronta la distribuzione del risparmio per le due varianti; **le scatole tratteggiate corrispondono all'euristica NON ammissibile**, che non garantisce l'ottimo e non produce alcun risultato ufficiale del progetto. Il pannello (d) mostra il costo dei cambi nello stato: la variante proiettata espande circa un terzo degli stati, ma sbaglia l'itinerario su nove interrogazioni su 79. Dati grezzi in `results/ricerca_astar.csv`, `results/grafo_finestra.csv` e `results/velocita_archi.csv`.](../results/ricerca_astar.png)

Nessuno dei risultati riportati in questa sezione dipende da un modello dei
ritardi: sono tutti calcolati sull'orario programmato pubblicato dalle due
aziende.

# Sezione Argomento 3 — Ragionamento e incertezza

## Sommario

Il problema si formula come **calcolo di una probabilita' su una successione di
eventi dipendenti** [1, cap. 9]. La particolarita' di questo caso e' triplice. La
variabile aleatoria non e' l'esito di una coincidenza ma l'orario di arrivo, che
e' continuo e va discretizzato. Le dipendenze non hanno la forma usuale, perche'
il ritardo si propaga *dentro* una corsa e si azzera *attraversando* un cambio, il
che rende la catena markoviana ma con una struttura di condizionamento che va
esplicitata. E soprattutto una coincidenza persa non e' un fallimento assorbente
ma un ritardo, perche' chi perde l'autobus prende quello dopo: l'evento negativo
non termina il processo, lo sposta.

Il modulo assegna a ciascun itinerario la probabilita' di arrivare a destinazione
entro una scadenza `T`, e sceglie quello che la massimizza. Riceve come candidati
gli itinerari non dominati prodotti dalla ricerca multi-criterio descritta
nell'argomento precedente — mediamente fra cinque e sei per ogni coppia
origine-destinazione — e come modello dei ritardi una distribuzione condizionata
alla linea, alla posizione lungo la corsa e al ritardo osservato a monte.

**Perche' l'obiettivo probabilistico non e' una penalizzazione del tempo.** La
tentazione naturale, di fronte al problema, e' evitare la probabilita' e
correggere l'orario: penalizzare gli itinerari con coincidenze tese, per esempio
sommando al tempo di viaggio un termine proporzionale alla strettezza dei margini.
Sarebbe piu' semplice e non richiederebbe alcun modello dei ritardi. Non funziona,
e la ragione non e' di accuratezza ma di struttura. Una penalizzazione della forma
"tempo di viaggio piu' lambda per la tensione delle coincidenze" induce **un solo
ordinamento** sugli itinerari: fissato lambda esiste un migliore, ed e' sempre lo
stesso. La quantita' P(arrivo <= T) induce invece **una famiglia di ordinamenti
indicizzata da T**, e nessuna scelta di lambda puo' riprodurre una famiglia con un
elemento solo.

L'inversione si vede su due itinerari costruiti apposta. Il primo, A, arriva
cinquanta minuti dopo la partenza secondo l'orario, ma la sua unica coincidenza ha
due minuti di margine. Il secondo, B, arriva cinquantacinque minuti dopo, con
dodici minuti di margine.

| Scadenza T | P(A) | P(B) | Migliore |
| ---: | ---: | ---: | :---: |
| +50 min | 0,078 | 0,000 | A |
| +55 min | 0,337 | 0,236 | A |
| +60 min | 0,498 | 0,827 | **B** |
| +70 min | 0,912 | 0,990 | **B** |
| +120 min | 0,998 | 1,000 | **B** |

Le righe mostrano l'inversione avvenire fra i cinquantacinque e i sessanta minuti.
A cinquanta minuti B ha probabilita' esattamente nulla, perche' il suo orario di
arrivo programmato cade gia' oltre la scadenza e nemmeno la puntualita' perfetta
basterebbe; A ha 0,078, poco, ma non zero. A cinquantacinque A conduce ancora,
0,337 contro 0,236. A sessanta l'ordine si e' rovesciato e il distacco e' ampio,
0,498 contro 0,827: B ha ormai margine sufficiente e la sua coincidenza tiene,
mentre quella di A continua a saltare in circa la meta' dei casi. A settanta e a
centoventi B resta davanti ma le due probabilita' convergono verso uno, e la
scelta smette di contare. Nessun ordinamento fisso puo' contenere entrambe le
risposte. L'esempio rende immediato il meccanismo ma resta un caso costruito: la
dimostrazione empirica su un campione e' nella valutazione.

**Perche' il prodotto ingenuo delle probabilita' sarebbe sbagliato in questa
catena.** Calcolare P(arrivo <= T) richiede di comporre le distribuzioni di
ritardo lungo la successione delle tappe. La composizione ovvia — il prodotto
delle probabilita' di prendere ciascuna coincidenza — e' sbagliata per due ragioni
di **segno opposto**, e nessuna delle due e' trascurabile. Che siano di segno
opposto e' cio' che rende l'errore insidioso: non c'e' garanzia che si compensino,
e la loro somma algebrica dipende dall'itinerario, quindi il prodotto ingenuo non
e' nemmeno una stima distorta in modo uniforme, che si potrebbe correggere.

**Sovrastima**, perche' tratta come indipendenti eventi che non lo sono. Il
ritardo con cui un mezzo arriva alla fermata di discesa non e' indipendente da
quello con cui e' partito: e' lo stesso veicolo, e i ritardi si accumulano lungo
il percorso. Se un autobus e' gia' in ritardo di cinque minuti alla quinta
fermata, e' verosimilmente in ritardo anche alla dodicesima. Il prodotto delle
marginali assume invece che ogni coincidenza sia un'estrazione nuova, e cosi'
facendo attribuisce all'itinerario una capacita' di recuperare che il veicolo non
ha. Nel caso limite di correlazione perfetta lungo la corsa, la probabilita'
congiunta di prendere due coincidenze consecutive coincide con la piu' piccola
delle due marginali, non con il loro prodotto, che e' sensibilmente minore.

**Sottostima**, perche' considera fallimento definitivo una coincidenza persa. Chi
perde un autobus prende quello successivo e arriva piu' tardi, il che puo'
benissimo essere ancora entro T. Ignorare il recupero cancella proprio il fenomeno
che la domanda di ricerca vuole misurare: un itinerario e' robusto anche perche',
quando perde una coincidenza, ne trova un'altra presto. E' una proprieta' della
**rete** e non del singolo itinerario, e senza il recupero due itinerari con la
stessa coincidenza tesa ma frequenze molto diverse — una linea ogni cinque minuti
e una ogni quaranta — risulterebbero identici, mentre sono l'uno robusto e
l'altro fragile.

La struttura corretta e' **markoviana con azzeramento**. Presa una coincidenza,
l'arrivo a valle dipende dal ritardo del nuovo mezzo e non da quanto per poco la
si e' presa: l'informazione sul ritardo precedente si perde attraversando il
cambio, perche' il veicolo su cui si sale non sa nulla di quello da cui si e'
scesi. Il ritardo si propaga percio' dentro una corsa, non fra una corsa e la
successiva, e la catena va rappresentata come una successione di tappe in cui, a
ciascuna, si sceglie quale corsa si riesca effettivamente a prendere fra quella
pianificata e i recuperi disponibili. Il condizionamento fra salita e discesa e'
esplicito: la distribuzione del ritardo alla discesa viene richiesta al modello
passandogli il ritardo alla salita. E' il punto in cui il calcolo smette di
trattare come indipendenti eventi che non lo sono, ed e' anche la ragione per cui
l'interfaccia del modello dei ritardi prevede fin dalla prima versione un campo
per il ritardo a monte.

**Due calcoli indipendenti della stessa quantita'.** La probabilita' e' calcolata
sia per convoluzione numerica su griglia sia per campionamento [1, cap. 9][11].
Averne due non e' ridondanza: sulla catena a piu' coincidenze non esiste una forma
chiusa contro cui verificare il risultato, e la concordanza fra due
implementazioni che non condividono nulla e' l'unica verifica non circolare
disponibile. L'unico caso con soluzione analitica — una sola tappa, senza
correlazione, con la corsa sempre prendibile — e' usato come ancoraggio nei test,
e li' entrambi i metodi coincidono con la ripartizione del ritardo entro due punti
percentuali.

## Strumenti utilizzati

Il calcolo impiega due metodi standard, la **convoluzione numerica** di
distribuzioni discretizzate su griglia e il **campionamento Monte Carlo**, per i
quali si rimanda al testo del corso [1, cap. 9] e alla trattazione di Robert e
Casella [11]. Le distribuzioni continue e le loro funzioni di ripartizione
provengono da **scipy.stats** [12]; la propagazione sulla griglia e il
campionamento usano **numpy** [10], con generatori pseudocasuali espliciti
inizializzati da un seme dichiarato; le figure sono prodotte con **matplotlib**
[17].

Sono originali di questo progetto, e per questo esposti nel sommario e fra le
decisioni di progetto anziche' qui: l'argomentazione sulla non riducibilita'
dell'obiettivo probabilistico a una penalizzazione del tempo di viaggio, l'analisi
delle due ragioni di segno opposto per cui il prodotto ingenuo delle probabilita'
sbaglia su questa catena, e la struttura markoviana con azzeramento e recupero con
cui la successione delle coincidenze e' modellata.

## Decisioni di Progetto

**L'interfaccia del modello dei ritardi e' fissata prima dei dati.** Il contratto
fra il calcolo di probabilita' e il modello dei ritardi e' stato progettato prima
che i dati reali fossero disponibili, e comprende fin dall'inizio il campo per il
ritardo a monte che rende esprimibile il condizionamento. *Perche' cosi':*
aggiungere quel campo a posteriori avrebbe richiesto di riscrivere il calcolo, e
il campo esiste per una ragione di modello, non per una disponibilita' di dato.
*La contromisura che ne discende:* esiste un'implementazione **sintetica** che
soddisfa l'interfaccia, usata per far girare e collaudare il codice mentre la
raccolta prosegue, e un modello sintetico e' per costruzione indistinguibile da
uno vero attraverso l'interfaccia. E' esattamente questo a renderlo pericoloso:
senza un controllo esplicito, una dimenticanza basterebbe a pubblicare numeri
calcolati su ritardi inventati senza che nulla lo segnali. Il presidio ha tre
livelli — ogni modello espone un attributo che dichiara se sia sintetico; ogni
script che scriva in `results/` invoca un controllo che solleva un errore a meno
che non sia stato concesso il permesso esplicito; e ogni file di risultati porta
il nome del modello che lo ha prodotto, cosi' l'origine resta leggibile anche a
distanza di mesi.

**Una coincidenza persa e' un ritardo, non un fallimento, con un tetto di due
recuperi.** Quando la catena perde una coincidenza, il calcolo prosegue sulla
corsa successiva della stessa linea dalla stessa fermata. *Alternativa scartata:*
il fallimento secco, in cui perdere una coincidenza azzera la probabilita' di
arrivo. *Perche' no:* e' molto piu' semplice da calcolare ma rende
P(arrivo <= T) sistematicamente pessimistica e, soprattutto, cancella il fenomeno
che la domanda di ricerca vuole misurare, come argomentato nel sommario. *Perche'
il tetto e' due:* il numero di corse successive da considerare va limitato perche'
il calcolo termini, e due recuperi coprono, sulle frequenze urbane osservate, un
orizzonte confrontabile con i margini della griglia di scadenze. *Il tetto va
dichiarato e misurato:* sulle 1.920 valutazioni della griglia sperimentale la
quota media di massa di probabilita' che esaurisce i recuperi e' del **9,2%**,
circa un caso su undici. E' abbastanza da meritare questa menzione e non
abbastanza da governare i risultati; oltre un quarto il tetto direbbe piu' sul
proprio valore che sul mondo, e andrebbe alzato.

**La griglia temporale della convoluzione: passo di 10 secondi su un orizzonte di
4 ore.** *Alternative valutate e misurate:* passi di 5, 30 e 60 secondi, riportati
nella Tabella 9. *Perche' 10:* e' il punto in cui l'errore smette di scendere in
modo apprezzabile — da 0,0049 a passo 10 a 0,0039 a passo 5 — mentre il costo
resta praticamente invariato. *Perche' l'orizzonte e' 4 ore:* deve contenere la
coda della distribuzione dell'orario di arrivo anche dopo due recuperi su una
linea a bassa frequenza, e quattro ore la contengono con margine.

**La griglia dei ritardi per il condizionamento: da -300 a +1800 secondi, passo
10.** E' la griglia su cui si discretizza il ritardo alla salita per richiedere al
modello la distribuzione condizionata alla discesa. *Perche' vale per entrambi i
metodi:* usarla anche nel Monte Carlo isola, nel confronto fra i due, l'errore
della sola griglia **temporale** della convoluzione, che e' cio' che interessa
misurare, invece di mescolarlo con quello del condizionamento. *Perche' il limite
inferiore e' negativo:* un mezzo puo' passare in anticipo, e troncare a zero
introdurrebbe una distorsione sistematica a favore della puntualita'.

**Una guardia sulla conservazione della massa.** Il calcolo verifica che la massa
di probabilita' si conservi lungo la catena e solleva un errore altrimenti.
*Perche' esiste:* una prima versione restituiva probabilita' maggiori di uno,
perche' usava la massa **discretizzata** per la probabilita' di prendere una
corsa e la ripartizione **continua** per quella di mancarla; le due non sommano a
uno, e l'errore si accumulava lungo la catena. *Perche' e' collaudata di
proposito:* un test sbilancia deliberatamente la ripartizione e verifica che la
guardia scatti, perche' senza quel test la guardia sarebbe codice di cui non
sappiamo se funziona.

**La correlazione lungo la corsa e' un parametro, non una costante.** Il modello
accetta un parametro in [0, 1] che governa quanto il ritardo osservato a monte si
trasferisca alla fermata di discesa; il valore usato negli esperimenti e' **0,7**.
*Alternative scartate:* ignorare del tutto il ritardo a monte, oppure cablare un
valore fisso. *Perche' no alla prima:* renderebbe la catena artificialmente
ottimistica, perche' tratterebbe come indipendenti il ritardo alla salita e quello
alla discesa dello stesso mezzo, che e' precisamente la sovrastima descritta nel
sommario. *Perche' no alla seconda:* significherebbe scrivere il resto del
progetto attorno a un numero inventato, mentre il modello appreso dai dati avra'
la correlazione che i dati mostrano, che potrebbe essere molto diversa. *Una
proprieta' utile del parametro:* a correlazione nulla il condizionamento non ha
effetto e P(arrivo <= T) di una singola tappa coincide con la ripartizione del
ritardo, ed e' esattamente l'ancoraggio analitico usato nei test.

**L'insieme candidato e' la frontiera di Pareto, e la misura che lo giustifica.**
*Il limite, che e' piu' affilato di quanto sembri:* la frontiera e' calcolata su
criteri deterministici — orario di arrivo, numero di cambi, minuti a piedi — e
**collassa fra loro gli itinerari che differiscono solo per il margine sulle
coincidenze**, che e' precisamente la dimensione da cui dipende la robustezza.
Massimizzare su un insieme privo delle alternative rilevanti non sarebbe un limite
da dichiarare in una nota: sarebbe un esperimento incapace di rispondere alla
domanda posta. *La contromisura preparata:* generare, per ogni soluzione della
frontiera, le varianti che partono con la corsa precedente o successiva sulla
stessa linea, allargando l'insieme nella dimensione dei margini. *Perche' non e'
stata implementata:* il dubbio e' stato risolto **prima** di costruire il
pianificatore, misurando quanto P vari lungo la frontiera. La risposta e' che
varia molto: l'ampiezza fra la soluzione migliore e la peggiore e' mediamente di
**0,44**, e solo una coppia su quattordici sta sotto 0,05. La frontiera e' quindi
gia' abbastanza ricca.

*Una distinzione metodologica che vale la pena riportare.* La prima versione di
questa misura dava un'ampiezza di **0,66**, ed era viziata: includeva fra i
candidati anche gli itinerari il cui arrivo *programmato* cadeva gia' dopo la
scadenza, che hanno probabilita' prossima a zero per costruzione. Quella misura
non rispondeva alla domanda posta, perche' registrava soprattutto che un
itinerario piu' lento arriva piu' tardi — il che non e' una scoperta — invece di
quanto due itinerari ugualmente plausibili si distinguano in affidabilita'.
Restringendo ai soli itinerari **nominalmente fattibili** il valore scende a 0,44,
ed e' quello a rispondere. La differenza fra 0,66 e 0,44 e' esattamente la
velocita' travestita da robustezza.

**La scadenza e' relativa all'itinerario piu' veloce.** T e' definita come orario
di arrivo dell'itinerario piu' veloce piu' un margine, e il margine varia su una
griglia di **0, 5, 10, 15, 20 e 30 minuti**. *Alternativa scartata:* una scadenza
assoluta, per esempio l'orario di un appuntamento. *Perche' no:* introdurrebbe una
scelta arbitraria sull'appuntamento, e i risultati dipenderebbero da quella invece
che dal metodo. *Perche' la definizione relativa:* aderisce alla domanda di
ricerca, che parla di confronto "a parita' di tempo di viaggio nominale".
*Perche' una griglia e non un valore:* le tre grandezze in funzione del margine
sono la dimostrazione empirica di non riducibilita', e un valore solo non
mostrerebbe alcuna dipendenza da T. *Perche' il margine zero e' incluso benche'
degenere:* e' il punto in cui il criterio probabilistico non puo' guadagnare
nulla, e serve a delimitare il campo di applicabilita' dal basso. *Il prezzo, da
dichiarare:* la definizione e' **severa verso il criterio probabilistico**, perche'
ogni itinerario piu' lento di un certo scarto sull'orario deve recuperare quello
scarto prima ancora di poter competere; e' aritmetica della definizione, non una
proprieta' del modello, e implica che il vantaggio misurato vada letto come un
limite inferiore.

**Il tratto a piedi finale entra nel tempo di viaggio.** L'itinerario porta un
campo con i secondi di cammino dopo l'ultima discesa, e tutti i calcoli ne tengono
conto. *Perche' e' stato necessario:* la prima versione del convertitore
costruiva le tappe dai soli tratti percorsi a bordo, quindi calcolava la
probabilita' di arrivare **alla fermata di discesa** invece che a destinazione;
sul campione di Torino il **54% dei candidati termina con un tratto a piedi**,
quindi per piu' della meta' degli itinerari il tempo di viaggio era sottostimato,
e sistematicamente a favore proprio di quelli che camminano di piu'. Il confronto
fra strategie ne sarebbe uscito falsato nella direzione peggiore, perche' la
strategia del margine fisso tende a scegliere itinerari con piu' cammino. *Perche'
resta separato dalle tappe:* non e' soggetto a ritardi, si cammina sempre alla
stessa velocita', e trattarlo come una tappa gli attribuirebbe una varianza che
non ha. *La verifica:* dopo la correzione l'orario di arrivo ricostruito
dall'itinerario coincide esattamente con quello dell'etichetta di Pareto su tutti
i 106 candidati esaminati; prima divergeva su tutti quelli con coda a piedi.

**Un test che falliva a intermittenza non e' stato archiviato.** I parametri delle
distribuzioni sintetiche sono derivati da `hashlib.blake2b` e non dalla funzione
`hash` incorporata. La ragione merita di essere riportata perche' dice qualcosa
sul metodo prima che sul codice. Un test deterministico ha cominciato a fallire in
circa due esecuzioni su tre della suite completa, passando sempre quando eseguito
da solo. La tentazione naturale, di fronte a un test che "a volte fallisce", e'
allargarne la tolleranza o dichiararlo instabile. La causa era invece un difetto
vero: il modello usava `hash((seme, route_id))` per derivare i parametri, e
**Python randomizza l'hash delle stringhe a ogni processo**, quindi lo stesso
identificativo di linea produceva parametri diversi a ogni esecuzione. Il modello
si dichiarava deterministico dato un seme e non lo era, e la verifica fatta
inizialmente — due chiamate nello stesso processo — era proprio quella incapace di
rivelarlo. Le conseguenze sarebbero andate ben oltre il test: **ogni esperimento
di questa sezione sarebbe stato irriproducibile**, e il difetto si sarebbe
manifestato solo come numeri che cambiano fra un'esecuzione e l'altra senza
spiegazione, in un progetto che dichiara la riproducibilita' fra i propri
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
senza un permesso esplicito. I risultati sui ritardi reali sono oggetto
dell'argomento successivo, non ancora concluso. Le sezioni precedenti non sono
interessate da questa avvertenza: i loro risultati sono calcolati sulla topologia
della rete e sull'orario programmato pubblicati dalle due aziende.

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

Le quattro righe della convoluzione vanno lette sulla colonna del costo prima che
su quella dell'errore, perche' e' li' che si trova la sorpresa. Passando da 60 a 5
secondi di passo, cioe' raffinando la griglia di dodici volte, l'errore migliora
di quasi dieci volte, da 0,0385 a 0,0039, ma il costo passa da 87 a 96
millisecondi: **nove millisecondi in tutto**. La griglia temporale non e' dunque
cio' che rende costosa la convoluzione. Il costo di base di 87 millisecondi e'
speso altrove, ed e' il numero di interrogazioni al modello dei ritardi: una per
ogni bin di ritardo alla salita e per ogni corsa candidata, perche' ognuna
richiede la distribuzione condizionata corrispondente.

Le quattro righe del Monte Carlo si comportano come ci si aspetta da uno stimatore
campionario: centuplicando i campioni da 100 a 10.000 l'errore scende di poco piu'
di dieci volte, da 0,0271 a 0,0026, che e' la legge della radice; e il costo cresce
in modo quasi proporzionale ai campioni oltre le prime migliaia, da 8 a 25 a 151
millisecondi.

Il confronto fra i due blocchi e' **il risultato non atteso** della sezione. Ci si
aspettava che la convoluzione fosse il metodo esatto e il campionamento
l'approssimazione economica. La riga del Monte Carlo con 10.000 campioni e la riga
della convoluzione con passo 10 s dicono il contrario: **0,0026 di errore contro
0,0049, e 25 millisecondi contro 89**. Il campionamento e' quasi due volte piu'
accurato e tre volte e mezzo piu' rapido. E la dominanza non riguarda solo quella
coppia di righe: il Monte Carlo con 1.000 campioni costa 8 millisecondi, cioe' un
decimo della convoluzione piu' economica, con un errore di 0,0107 che e' meno di
un terzo di quello della convoluzione a passo 60. Non esiste una scelta dei
parametri per cui la convoluzione risulti preferibile su entrambi gli assi.

Nonostante questo la convoluzione resta il metodo usato dal pianificatore, per una
proprieta' che la Tabella 9 non misura: e' **deterministica**. Due esecuzioni danno
lo stesso numero, mentre il Monte Carlo ha rumore campionario, e con un errore
tipico di 0,0026 due itinerari le cui probabilita' distino meno di quel valore
potrebbero scambiarsi di posto fra un'esecuzione e l'altra. Poiche' il
pianificatore confronta cinque candidati fra loro e ne sceglie uno, il rumore si
trasformerebbe in una scelta irriproducibile, che e' un difetto peggiore di tre
millesimi di errore. Il campionamento e' percio' relegato al ruolo di verifica,
dove la sua accuratezza superiore serve davvero e il suo rumore non decide nulla.

![**Figura 3.** Accuratezza e costo dei due metodi di calcolo, su distribuzioni sintetiche. Nel pannello (a) l'asse orizzontale porta il parametro di ciascun metodo, che ha significato diverso per i due: passo della griglia in secondi per la convoluzione, numero di campioni per il Monte Carlo. Il pannello (b) e' quello che conta: mette accuratezza e costo sugli stessi assi, e mostra che la curva del Monte Carlo giace interamente in basso a sinistra rispetto a quella della convoluzione. Dati grezzi in `results/conv_vs_montecarlo.csv`.](../results/conv_vs_montecarlo.png)

**La griglia della scadenza, e la dimostrazione empirica di non riducibilita'.**

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

Le tre colonne vanno lette una alla volta, e ciascuna dice una cosa diversa.

**L'ampiezza sulla frontiera** parte quasi nulla e cresce in modo monotono su
entrambe le citta': 0,026 e 0,024 a margine zero, poi 0,279 e 0,290 a cinque
minuti, fino a 0,562 e 0,478 a trenta. Il salto piu' violento e' il primo, da zero
a cinque minuti, dove l'ampiezza si decuplica. La ragione e' che a margine nullo
tutti i candidati hanno probabilita' prossima a zero e non c'e' nulla da
distinguere; appena la scadenza si allarga, gli itinerari cominciano a
differenziarsi, e la frontiera si rivela ricca. E' la misura che giustifica l'uso
della frontiera di Pareto come insieme candidato, ed e' anche quella che, nella
sua prima versione viziata, dava 0,66 anziche' 0,44.

**La coincidenza fra la scelta robusta e quella piu' veloce scende
monotonamente**, dall'85% al 62% su Roma e dall'88% al 55% su Torino, senza una
sola inversione su dodici righe. E' la dimostrazione empirica di non riducibilita'
annunciata nel sommario: al variare della sola scadenza, a parita' di rete, di
orario e di modello dei ritardi, il criterio probabilistico cambia idea su una
frazione crescente delle coppie — dal 12-15% al 38-45%. Nessun ordinamento fisso
sugli itinerari puo' produrre questo comportamento, perche' un ordinamento fisso
sceglierebbe sempre lo stesso itinerario e la coincidenza sarebbe costante. La
misura sostituisce l'esempio a due itinerari costruito nel sommario, perche' e'
fatta su ottanta coppie estratte e non su un caso scelto ad arte.

**Il guadagno non e' monotono**, e la sua forma a campana e' il risultato piu'
informativo della sezione. Su Roma sale da 0,001 a 0,040, 0,068, 0,080 e 0,084,
per poi ricadere a 0,049; su Torino da 0,009 a 0,040, 0,058, 0,098 e 0,096, per
poi ricadere a 0,061. Il massimo e' fra i quindici e i venti minuti su entrambe le
citta'. A margine nullo il guadagno vale praticamente zero perche' la scadenza
coincide con l'arrivo programmato del piu' veloce e nessun itinerario ha speranze
apprezzabili: non c'e' niente da guadagnare quando tutti falliscono. A trenta
minuti torna a scendere perche' la scadenza e' cosi' larga che quasi tutti
arrivano: non c'e' niente da guadagnare nemmeno quando tutti riescono. Va notato
che il massimo del guadagno **non coincide** con il massimo dell'ampiezza sulla
frontiera, che continua a crescere fino a trenta minuti: la frontiera resta
diversificata anche quando la scelta non conta piu', perche' distinguere gli
itinerari e sceglierne uno che valga la pena sono due cose diverse.

Le deviazioni standard del guadagno sono grandi rispetto alle medie — 0,188 su
0,080 a Roma — e la ragione e' che il guadagno e' nullo su tutte le coppie in cui
la scelta robusta coincide con la piu' veloce, che sono la maggioranza, e
concentrato sulle poche in cui differisce. La distribuzione e' quindi fortemente
asimmetrica, con una massa in zero e una coda positiva.

La lettura d'insieme e' che questo **non e' un limite del metodo ma il suo campo
di applicabilita'**: il ragionamento probabilistico serve quando la scadenza e'
abbastanza stretta da rendere il fallimento possibile e abbastanza larga da
rendere il successo raggiungibile. Fuori da quell'intervallo la risposta non
dipende dal criterio, e un modello dei ritardi non ripaga la propria complessita'.

![**Figura 4.** Le tre grandezze in funzione del margine sulla scadenza, su quaranta coppie per citta' e con modello dei ritardi sintetico. Il pannello (b) e' la dimostrazione di non riducibilita': la coincidenza fra scelta robusta e scelta piu' veloce scende al crescere del margine, quindi l'ordinamento fra itinerari dipende dalla scadenza. Il pannello (c) mostra la forma a campana del guadagno. Le barre di deviazione standard del pannello (c) scendono sotto lo zero, ma si tratta di un artefatto: la deviazione standard e' simmetrica mentre la distribuzione non lo e', e la differenza per singola coppia non e' **mai** negativa, in nessuna delle 480 combinazioni esaminate. Dati grezzi in `results/robusto_griglia_T.csv`.](../results/robusto_griglia_T.png)

**Il confronto con le strategie di riferimento.** Le tre baseline non sono
avversari di comodo: rappresentano cio' che si fa realmente in assenza di un
modello dei ritardi. La **piu' veloce** e' il pianificatore di qualunque
applicazione di viaggio, ed e' il termine di paragone naturale perche' e' quello
che l'utente ha oggi. **Meno cambi** e' cio' che fa chi ha imparato per esperienza
che ogni trasbordo e' un'occasione di perdere una coincidenza, ma non sa
quantificarlo. Il **margine fisso** e' la baseline che conta: rappresenta la
persona ragionevole che si da' una regola — accetto solo itinerari in cui ogni
coincidenza ha almeno cinque minuti di margine, e fra quelli prendo il piu' veloce
— ed e' una strategia sensata, gratuita e quella che il pianificatore
probabilistico deve battere per giustificare la propria esistenza. Quando nessun
itinerario soddisfa la regola, la strategia allenta il vincolo invece di
rinunciare, perche' fingere che non risponda la giudicherebbe solo sui casi
facili. Tutte e quattro le strategie scelgono dallo stesso insieme di candidati e
vengono valutate con lo stesso calcolo di P(arrivo <= T): il confronto misura
quindi la strategia di scelta e non il metodo di valutazione.

Tabella 11 — Probabilita' media di arrivo entro la scadenza, su tutte le coppie e
tutti i margini della griglia.

| Strategia | Roma | Torino |
| --- | ---: | ---: |
| robusto | **0,555 ± 0,374** | **0,570 ± 0,367** |
| piu' veloce | 0,501 ± 0,363 | 0,509 ± 0,373 |
| meno cambi | 0,429 ± 0,411 | 0,388 ± 0,418 |
| margine fisso | 0,403 ± 0,418 | 0,426 ± 0,420 |

La prima riga e la seconda distano poco, 0,555 contro 0,501 su Roma e 0,570 contro
0,509 su Torino, cioe' circa cinque-sei punti percentuali: e' il vantaggio del
criterio probabilistico sulla strategia che l'utente ha oggi, mediato su tutta la
griglia di scadenze, comprese quelle degeneri agli estremi dove il guadagno e'
nullo per costruzione. La Tabella 10 mostra che nell'intervallo utile il vantaggio
sale a otto-dieci punti.

La terza e la quarta riga stanno sensibilmente piu' in basso, fra 0,388 e 0,429, e
qui ci sono due osservazioni, di cui la seconda inattesa.

La prima e' che il pianificatore robusto **non perde mai** contro nessuna
baseline: su tutte e 480 le combinazioni di citta', coppia e margine la sua
probabilita' e' maggiore o uguale a quella di ciascuna alternativa. Va detto pero'
che questo non e' un risultato ma un **controllo di correttezza**: le quattro
strategie scelgono dallo stesso insieme e il pianificatore massimizza per
definizione la grandezza con cui tutte vengono poi valutate, quindi perdere
sarebbe stato un difetto dell'implementazione. Il risultato e' semmai di quanto
vince, che e' il contenuto della Tabella 10.

La seconda e' che la strategia del **margine fisso e' la peggiore delle tre su
Roma**, 0,403 contro 0,429 di "meno cambi", e la penultima su Torino. Il fatto
merita attenzione perche' contraddice l'intuizione: la regola dei cinque minuti e'
pensata proprio per proteggere dalle coincidenze perse, che sono il fenomeno in
esame. La spiegazione sta nell'interazione con la definizione della scadenza. Con
T ancorata all'arrivo del piu' veloce, imporre cinque minuti di margine su **ogni**
coincidenza costringe a scegliere itinerari sensibilmente piu' lenti sull'orario,
e lo svantaggio di partenza supera il beneficio della maggiore affidabilita': si
guadagna in probabilita' di prendere ogni singola coincidenza e si perde in
probabilita' di arrivare in tempo, che e' la grandezza che conta. La regola del
margine fisso e' una difesa contro le coincidenze perse che **non guarda alla
scadenza**, e in un problema in cui la scadenza e' il vincolo si difende dal
rischio sbagliato. E' precisamente il tipo di errore che un criterio
probabilistico esplicito evita, perche' P(arrivo <= T) contiene T e la regola dei
cinque minuti no. Le deviazioni standard delle due ultime righe, oltre 0,41,
superano quelle delle prime due e confermano la lettura: sono strategie che
funzionano molto bene su alcune coppie e molto male su altre, mentre il criterio
probabilistico e' piu' uniforme.

Va ricordato un'ultima volta che tutti i numeri di questa sezione sono calcolati
su ritardi inventati. Dicono che il metodo distingue gli itinerari, che il calcolo
e' corretto e riproducibile, e in quale intervallo di scadenze il criterio
probabilistico cambia le decisioni. Se il vantaggio misurato qui si conservi sui
ritardi reali di Roma e di Torino e' esattamente la domanda a cui l'argomento
successivo dovra' rispondere.

# Sezione Argomento 4 — Apprendimento supervisionato e apprendimento con incertezza

## Sommario

Il problema si formula come **stima di una distribuzione condizionata a partire da
esempi osservati** [1, cap. 7 e cap. 10]. La particolarita' di questo caso e' che
la grandezza da apprendere non e' un'etichetta ne' un valore atteso, ma l'intera
distribuzione del ritardo: al modulo che compone le probabilita' lungo la catena
delle coincidenze non basta sapere che una linea accumula in media tre minuti,
perche' una linea che ritarda sempre di tre minuti e una che ritarda di zero o di
dieci a giorni alterni producono probabilita' di coincidenza molto diverse. La
seconda particolarita' e' che gli esempi non sono indipendenti: due passaggi della
stessa corsa a fermate consecutive sono osservazioni dello stesso veicolo, e la
loro dipendenza e' precisamente cio' che il modello deve catturare, non un
disturbo da eliminare.

Questo modulo stimera' dai dati raccolti sul campo le distribuzioni che
l'argomento precedente compone. Fino a oggi quel ragionamento e' stato collaudato
su distribuzioni sintetiche, che permettono di verificare il calcolo ma non dicono
nulla sul trasporto pubblico reale; sostituirle con distribuzioni apprese e' cio'
che trasforma il metodo in un risultato sperimentale.

La grandezza da stimare e' la distribuzione dello scostamento di un passaggio
dall'orario programmato, condizionata alla linea, alla fascia oraria, alla
posizione lungo la corsa e al ritardo gia' osservato a monte sulla stessa corsa.
Le prime tre variabili spiegano quanto una linea sia strutturalmente puntuale in
un certo momento della giornata e in un certo punto del percorso; l'ultima e'
quella che rende esprimibile la correlazione dentro una corsa, ed e' la ragione
per cui l'interfaccia del modello dei ritardi la prevede fin dalla prima versione.

**La raccolta dei dati e' completa e funzionante**, ed e' l'unica parte di questo
argomento gia' conclusa. Un sistema installato su una macchina virtuale sempre
accesa interroga a intervalli fissi i due feed GTFS Real-Time [14] di ciascuna
citta', `trip_updates` e `vehicle_positions`, conserva i dump grezzi, archivia
l'orario statico ogni volta che cambia e consolida ogni notte le osservazioni
della giornata in formato colonnare, calcolando lo scostamento fra orario
osservato e orario programmato. Alla data di scrittura risultano **quattro
giornate consolidate per 74 MB di dati colonnari**, e la copertura reale misurata
sul 27 agosto e' del **100% su entrambe le citta'**.

La copertura non e' pero' l'unica grandezza da guardare, e il registro delle
interruzioni tiene traccia di cio' che la copertura non vede. Lo stesso 27 agosto
vi compare una finestra di **32 minuti su Torino** con causa
`errori_di_rete_prolungati`, mentre Roma raccoglieva regolarmente. E' la prima
interruzione di quel tipo: tutte le precedenti avevano causa
`processo_non_attivo`, cioe' il collector spento. La distinzione fra le due cause
non e' contabile ma **metodologica**, e va portata avanti fino alla stima. Quando
il collector e' spento non sappiamo che cosa sia accaduto sulla rete in quella
finestra: l'informazione esisteva e noi non l'abbiamo raccolta, quindi quei
minuti vanno esclusi dal backtesting, perche' altrimenti una coincidenza mai
osservata verrebbe scambiata per una coincidenza persa. Quando invece e' il feed
a non rispondere, l'informazione **non era disponibile nemmeno a un passeggero
reale** in quel momento: e' una condizione del mondo, non una lacuna della
raccolta, e un pianificatore che in quel momento avesse dovuto decidere si
sarebbe trovato senza dati esattamente come noi. Trattare i due casi allo stesso
modo scarterebbe proprio le finestre in cui il problema e' piu' difficile e in
cui un metodo robusto dovrebbe distinguersi.

Cio' che manca e' la stima vera e propria: la scelta della famiglia di
distribuzioni, il raggruppamento delle condizioni con numerosita' campionaria
sufficiente, la validazione della bonta' di adattamento su dati non usati per la
stima, e il confronto fra il modello appreso e quello sintetico sulle stesse
coppie origine-destinazione. La valutazione di questo argomento sara' percio'
anche la risposta finale alla domanda di ricerca del progetto.

## Strumenti utilizzati

La stima impieghera' **scikit-learn** [13] per la parte di apprendimento
supervisionato e **scipy.stats** [12] per l'adattamento delle distribuzioni e i
test di bonta' di adattamento; le nozioni di stima, validazione e sovradattamento
sono quelle del testo del corso [1, cap. 7], e il trattamento dei modelli
probabilistici appresi quelle del capitolo successivo [1, cap. 10]. La
manipolazione dei dati colonnari usa **pandas** [6] e il formato Parquet tramite
**pyarrow**. La raccolta gia' in esercizio usa **gtfs-realtime-bindings** [14] per
interpretare il formato protobuf dei feed e la sola libreria standard di Python
per le richieste HTTP.

## Decisioni di Progetto

Le decisioni gia' prese riguardano la raccolta, e sono vincolanti per la stima
perche' determinano che cosa sara' disponibile. Sono riportate qui perche' e' in
questo argomento che i dati raccolti vengono consumati.

**Si conserva una riga a ogni cambio della previsione, non solo l'ultima.** Per
ogni passaggio, identificato da `(trip_id, stop_sequence)`, si conserva una riga a
ogni cambio del valore osservato, con il timestamp della prima comparsa di quel
valore. *Alternative scartate:* una riga per passaggio, conservando solo l'ultima
osservazione; oppure una riga per ogni dump, senza alcuna deduplica. *Perche' no
alla prima:* una previsione che cambia nel corso della giornata **non e' un
duplicato**, e' l'evoluzione della stima dell'azienda, e dice quanto quella
previsione fosse affidabile con un certo anticipo; e' informazione che potrebbe
servire come variabile esplicativa e che non e' ricostruibile a posteriori se la
si getta ora. *Perche' no alla seconda:* conserverebbe soprattutto ripetizioni.
*Un dettaglio deliberato:* l'implementazione registra i **cambi** anziche' i
valori distinti in senso insiemistico, quindi una previsione che torna a un valore
gia' visto viene conservata come evento a se'; e' voluto, perche' un'oscillazione
e' informazione sulla stabilita' della stima, e perche' riconoscere i valori gia'
visti richiederebbe di tenere in memoria l'intero insieme dei valori di ogni
passaggio, che su Roma significa decine di milioni di voci.

**Il risultato negativo che accompagna quella scelta.** Il presupposto della regola
era che lo stesso passaggio comparisse identico in centinaia di dump consecutivi e
che la deduplica scartasse quindi la quasi totalita' delle righe. Misurato sui
dati reali non e' cosi': su 98 dump di Roma, 1.982.754 `stop_time_update` hanno
prodotto 1.361.088 righe, cioe' il **68,6%** del totale, perche' Roma ricalcola la
previsione quasi a ogni giro e ogni passaggio riceve in media 10,9 valori
distinti, fino a un massimo di 76; su Torino la quota e' il 65,1% con 5,4 valori
per passaggio. La proiezione a giornata piena e' di circa **20 milioni di righe al
giorno per Roma** e 2,2 milioni per Torino, dell'ordine dei 280 milioni di righe
su due settimane. La regola resta quella scelta, perche' la motivazione che la
giustifica non e' il risparmio ma la conservazione di un'informazione
irripetibile; va pero' registrato che il beneficio in volume che le era stato
attribuito non si e' verificato, e che il dimensionamento di questo argomento va
fatto su questi numeri e non su quelli attesi. Le politiche alternative `ultimo` e
`fasce` restano implementate proprio per poter cambiare idea sulla base di una
misura invece che di una previsione.

**La chiave di join e' `(trip_id, stop_sequence)`, non quella naturale.**
*Alternativa scartata:* la chiave naturale `(trip_id, stop_id, stop_sequence)`,
che era la prima implementazione. *Perche' e' stata abbandonata:* eseguendo il
consolidamento sui dati veri il numero di passaggi conservati non tornava, 4.691
invece dei 13.092 misurati. La causa e' che **GTT non include mai lo `stop_id`**
nei `stop_time_update`, identificando la fermata con il solo `stop_sequence`,
mentre Roma si comporta all'opposto e lo fornisce sempre. Con la chiave naturale
il join su Torino non trovava mai corrispondenza: la colonna `stop_id` restava
vuota, l'orario programmato nullo e il ritardo non calcolabile, e i dati di Torino
sarebbero stati inutilizzabili senza che nulla lo segnalasse. *Perche' la chiave
ridotta e' altrettanto precisa:* la specifica GTFS [5] garantisce che
`stop_sequence` sia univoco dentro una corsa. *Il controllo che ne discende:*
quando il feed fornisce anche lo `stop_id` si usa quello del feed e si verifica
che coincida con quello statico, e una divergenza viene contata e segnalata,
perche' significherebbe che la corsa in circolazione non e' quella che l'orario
descrive.

**L'orario statico e' archiviato a ogni cambiamento, ed e' un requisito e non una
precauzione.** Il ritardo e' uno scostamento da un orario programmato, e
quell'orario cambia: confrontare un'osservazione di oggi con l'orario di due
settimane fa produrrebbe ritardi inventati. Ogni giorno si verifica se l'archivio
sia cambiato e, in caso affermativo, se ne conserva una nuova revisione; un
indice associa a ogni data la revisione valida quel giorno.

*Quanto spesso cambia, misurato.* Sui quattro giorni finora mappati, dal 25 al 28
agosto, **Roma ha prodotto quattro revisioni distinte su quattro giorni** e
**Torino due su quattro**: l'archivio di Torino e' cambiato una volta, fra il 25 e
il 26 agosto, passando da **19.905.201 a 20.264.224 byte**. La lettura corretta
non e' dunque che Roma aggiorna l'orario e Torino no, ma che **entrambe lo
aggiornano, con frequenza diversa**. E' la differenza che trasforma
l'archiviazione giornaliera da precauzione a requisito: se avessimo scaricato il
GTFS una volta sola, per esempio il 27 agosto, i dump del 25 sarebbero oggi
associati a un orario sbagliato **per entrambe le citta'**, e ogni ritardo
calcolato su quel giorno sarebbe uno scostamento da un orario che quel giorno non
era in vigore. L'errore non si sarebbe manifestato come un'eccezione ma come
ritardi plausibili e falsi.

*Perche' il confronto dell'impronta e non il download.* L'archivio di Roma pesa
48,5 MB per revisione, quindi scaricarlo ogni giorno per scoprire che nulla e'
cambiato costerebbe quella banda per nulla; il file `.md5` che l'azienda pubblica
accanto all'archivio ne costa 59 byte. *Alternativa scartata:* fidarsi
dell'intestazione HTTP `Last-Modified`, che molti server aggiornano a ogni
rigenerazione anche quando il contenuto e' identico e che quindi non
distinguerebbe una revisione vera da una ripubblicazione. *Il caso di Torino:*
GTT non pubblica alcun `.md5`, quindi per quella citta' il meccanismo ripiega
sullo scaricamento dell'archivio e sul confronto della sua impronta — piu' costoso
ma corretto, e sostenibile perche' l'archivio di Torino pesa venti megabyte
scarsi.

**Si raccolgono entrambi i feed, non solo `trip_updates`.** *Perche':* i
`trip_updates` portano le previsioni di orario, che sono cio' che serve al
modello, ma i `vehicle_positions` portano la posizione effettiva e permettono di
distinguere una corsa soppressa da una corsa semplicemente non aggiornata, che nel
primo feed sono indistinguibili.

## Valutazione

La valutazione di questo argomento non e' ancora stata eseguita. Comprendera' la
bonta' di adattamento delle distribuzioni stimate, misurata su dati non usati per
la stima; il confronto fra il modello appreso e quello sintetico a parita' di
coppie origine-destinazione e di griglia di scadenze; e la ripetizione, sui
ritardi reali, dell'esperimento della griglia della scadenza riportato
nell'argomento precedente, che e' la risposta alla domanda di ricerca del
progetto. Ogni risultato sara' riportato come media e deviazione standard su piu'
giornate di raccolta, in modo che la variabilita' fra giorni feriali e festivi e
fra condizioni di traffico diverse sia visibile e non nascosta in un valore unico.

# Sezione Argomento 5 — Soddisfacimento di vincoli

## Sommario

Il problema si formula come **soddisfacimento di vincoli** [1, cap. 4]. La
particolarita' di questo caso e' che le variabili non sono grandezze elementari ma
scelte fra itinerari gia' calcolati: il pianificatore descritto nell'argomento
sulla ricerca produce, per ogni tratta, l'insieme delle soluzioni non dominate su
orario di arrivo, cambi e minuti a piedi, e qui si decide **quale** di quelle
soluzioni usare su ciascuna tratta di un viaggio che ne ha piu' d'una.

La situazione modellata e' quella di chi deve toccare piu' luoghi nella stessa
giornata: essere in stazione fra le 9:00 e le 9:15, poi in ufficio entro le 10:00.
Ogni singola tratta e' un problema gia' risolto; cio' che non e' risolto e' la
loro **compatibilita' reciproca**, ed e' li' che vive questo argomento.

**Variabili, domini, vincoli.** Le variabili sono le tratte del viaggio, una per
ciascuna. Il dominio di una tratta e' l'insieme degli itinerari non dominati che
la percorrono, ciascuno con l'istante da cui e' eseguibile, l'orario di arrivo, il
numero di cambi e i secondi di cammino. I vincoli sono cinque. La **precedenza**
impone di non ripartire prima di essere arrivati e di aver trascorso alla tappa il
tempo per cui ci si e' fermati. La **finestra** impone che l'arrivo a una tappa
intermedia cada fra due estremi, e l'estremo inferiore non e' decorativo: se devo
essere in stazione fra le 9:00 e le 9:15, arrivare alle 8:40 e' una violazione e
non un vantaggio. Il **budget dei cambi** limita il numero totale di trasbordi
dell'intera giornata, e il **budget del cammino** i minuti totali a piedi. La
**scadenza** vincola l'arrivo finale.

**Che cosa rende questo un problema di vincoli e non una ricerca sequenziale.** E'
la domanda che decide se l'argomento abbia diritto di esistere, e va affrontata
prima di ogni altra cosa.

Con i soli vincoli di precedenza il problema **si risolverebbe da sinistra a
destra**, scegliendo su ogni tratta l'itinerario che arriva prima e senza mai
tornare indietro. La ragione e' la stessa dominanza che nell'argomento sulla
ricerca permette di togliere l'istante dalla chiave di stato: arrivare prima, a
parita' di tutto il resto, non puo' nuocere, perche' ogni prosecuzione disponibile
a chi arriva tardi lo e' anche a chi arriva presto. Se il modello si fermasse li',
chiamarlo soddisfacimento di vincoli sarebbe una millanteria.

Cio' che rompe quella proprieta' sono i **due budget globali**. Non sono stati
introdotti per accoppiare le variabili: sono i vincoli che un viaggiatore reale
ha, e l'accoppiamento e' una loro conseguenza. Nessuno accetta dodici cambi in una
mattina, e le aziende di trasporto pubblicano tempi minimi di trasbordo proprio
perche' il cambio ha un costo che non e' solo di tempo. Il tetto sul cammino e'
ancora piu' concreto, ed e' stringente per chi ha ridotta mobilita' — la stessa
persona per cui la base di conoscenza del primo argomento deriva la relazione
`accessibile`.

Sotto un budget globale la dominanza cade, perche' un itinerario che arriva prima
puo' **consumare cambi che serviranno piu' avanti**. Il caso seguente lo dimostra
in modo verificabile a mano.

> Viaggio in tre tappe, tetto globale di **quattro cambi**, sosta minima di cinque
> minuti a ogni tappa intermedia.
>
> *Prima tappa*, con finestra 09:00–09:15: l'itinerario `X1` arriva alle 09:05 con
> tre cambi, l'itinerario `X2` alle 09:12 con un cambio. Entrambi rispettano la
> finestra.
> *Seconda tappa*: `Y1` esige di essere pronti alle 09:10 e costa un cambio, `Y2`
> alle 09:20 e ne costa due.
> *Terza tappa*: un solo itinerario, che esige di essere pronti alle 09:55 e costa
> un cambio.
>
> La strategia sequenziale sceglie `X1`, perche' arriva prima. Con la sosta di
> cinque minuti puo' poi prendere `Y1`, che parte esattamente alle 09:10: ha speso
> quattro cambi, e alla terza tappa ne servirebbe un quinto. **Dichiara l'istanza
> infattibile.**
>
> Scegliendo invece `X2`, che arriva **sette minuti piu' tardi**, la sosta impone
> di attendere fino alle 09:17 e quindi di prendere `Y2`. Il totale e'
> 1 + 2 + 1 = quattro cambi esatti, e il viaggio si conclude. **La soluzione
> esiste**, e per trovarla bisogna scegliere sulla prima tappa un itinerario
> peggiore sul criterio locale.

E' l'assenza di sottostruttura ottima, ed e' cio' che distingue un problema di
soddisfacimento di vincoli da una successione di decisioni indipendenti. Il caso
e' costruito, quindi dimostra che il fenomeno e' **possibile**; quanto sia
frequente su istanze ricavate dalla rete vera e' la misura riportata nella
valutazione, ed e' stata fatta prima di costruirci sopra qualunque altra cosa.

## Strumenti utilizzati

La formulazione e le nozioni di variabile, dominio, vincolo e propagazione sono
quelle del testo del corso [1, cap. 4]. I domini provengono dalla ricerca
multi-criterio a etichette gia' descritta [9]; la potatura del risolutore completo
usa un limite inferiore sul consumo residuo, che e' la forma piu' semplice di
propagazione all'indietro su un vincolo di somma.

Non vi sono dipendenze aggiuntive: i due risolutori sono scritti in Python puro
sopra le strutture gia' esistenti, e l'esperimento riusa il grafo tempo-espanso e
il pianificatore degli argomenti precedenti.

E' originale di questo progetto, e per questo esposto nel sommario, il
controesempio a tre tappe che dimostra l'assenza di sottostruttura ottima sotto un
budget globale.

## Decisioni di Progetto

**I domini si costruiscono da una griglia di istanti di disponibilita'.** Il
pianificatore viene interrogato su ogni tratta a partire da tre istanti, sfalsati
di dieci minuti, e l'unione delle frontiere risultanti forma il dominio. *Perche'
non un solo istante:* il dominio sarebbe povero e la scelta quasi obbligata, cioe'
un problema di vincoli senza vincoli da soddisfare. *Perche' non piu' di tre:*
ogni istante e' una ricerca di Pareto completa, e il costo dell'esperimento cresce
linearmente. *La conseguenza sul modello, da dichiarare:* ogni candidato conserva
l'istante da cui e' stato calcolato, e il vincolo di precedenza si scrive su
quello. Un itinerario calcolato per chi e' pronto alle 09:20 e' eseguibile da
chiunque sia pronto entro le 09:20, quindi la formulazione e' corretta ed e'
leggermente **conservativa**: un viaggiatore pronto alle 09:12 potrebbe in teoria
prendere qualcosa che la griglia non offre. Il vantaggio e' che i domini restano
**statici**, come un problema di vincoli richiede; ricalcolarli in funzione della
scelta precedente li renderebbe dinamici e trasformerebbe il problema in
un'altra cosa.

**I budget sono derivati dai dati, non scelti a occhio.** Per ogni istanza si
calcola il minimo di cambi ottenibile guardando ogni tratta separatamente, e il
tetto e' quel minimo piu' un margine che varia da zero a tre. *Perche' cosi':* un
tetto fisso confronterebbe istanze non confrontabili, perche' un viaggio fra
periferie richiede intrinsecamente piu' cambi di uno in centro, e un tetto sotto
il minimo renderebbe l'istanza infattibile per aritmetica invece che per
interazione fra le tappe — misurando la nostra scelta della soglia e non il
fenomeno. *Perche' il minimo per tratta e' un limite inferiore valido:* minimizza
ogni tratta ignorando precedenza e finestre, quindi non puo' superare il consumo
di una soluzione vera, ed e' anche il limite usato per potare la ricerca completa.

**Il budget del cammino e' lasciato largo di proposito.** Il margine sul cammino
e' di trenta minuti, abbastanza da non stringere quasi mai. *Perche':*
l'esperimento isola l'effetto del budget sui **cambi**, e lasciar stringere
entrambi mescolerebbe due cause in un solo numero. Il vincolo resta implementato e
collaudato, e stringerlo e' l'esperimento naturale successivo.

**Il confronto e' con la strategia sequenziale piu' forte, non con un fantoccio.**
Il risolutore greedy scarta i candidati che sforerebbero il budget **mentre**
procede, invece di accorgersene alla fine. *Perche':* un greedy che si accorge
dello sforamento solo alla fine fallirebbe piu' spesso, e la misura direbbe piu'
sulla debolezza del confronto che sulla natura del problema. La sola cosa che il
greedy non fa e' tornare indietro, che e' esattamente la proprieta' in esame.

**Piu' grafi brevi invece di uno lungo.** Un viaggio di quattro tratte casuali
attraversa la citta' per cinque o sei ore, ma il costo di una ricerca cresce con
l'orizzonte del grafo: misurato su Roma, la stessa ricerca costa **2,87 secondi**
su un orizzonte di 150 minuti e **38,63 secondi** su uno di 420, perche' il numero
di stati raggiungibili cresce con la finestra. Si costruisce percio' una
successione di sei grafi da 150 minuti sfalsati di un'ora, e ogni tratta viene
cercata su quello che copre il suo istante di disponibilita'. *La conseguenza:*
l'orizzonte effettivo di ciascuna ricerca resta fra i 90 e i 150 minuti,
confrontabile con i 120 minuti dell'argomento sulla ricerca, e vale la stessa
limitazione gia' dichiarata li': si trova l'ottimo dentro la finestra, e una
tratta che richiedesse un'attesa piu' lunga non verrebbe trovata affatto.

**Le catene che si interrompono si conservano per il prefisso.** Se la terza
tratta di una catena non ha alcun itinerario nella finestra, le prime due restano
utilizzabili come istanza a due tappe. *Perche' non si scarta tutto:* butterebbe
via istanze valide e farebbe sembrare il fenomeno piu' raro di quanto sia. Una
catena viene scartata solo sotto le due tratte, sotto le quali non esiste viaggio
multi-tappa.

## Valutazione

La misura riportata qui e' stata fatta **prima** di costruire qualunque altra cosa
sopra la formulazione, perche' e' quella che poteva invalidarla. La domanda e'
semplice: su istanze ricavate dalla rete vera, quanto spesso la strategia
sequenziale dichiara infattibile un viaggio che una soluzione ce l'ha? Se la
risposta fosse "quasi mai", il viaggio multi-tappa non sarebbe un problema di
soddisfacimento di vincoli e l'argomento andrebbe chiuso come risultato negativo.

**Come sono costruite le istanze.** Per ciascuna citta' si estraggono venticinque
successioni di cinque fermate, con un seme dichiarato, fra le fermate
effettivamente servite; da ogni successione si ricavano i domini tratta per
tratta, interrogando il pianificatore da tre istanti di disponibilita' sfalsati di
dieci minuti. Da ogni catena si ritagliano poi i viaggi a due, tre e quattro
tappe, e per ciascuno si fanno variare i tetti sui cambi da zero a tre sopra il
minimo ottenibile. Le catene utilizzabili sono state **20 su 25 a Roma** e **17 su
25 a Torino**: le altre si interrompono sotto le due tratte perche' una tratta non
ha alcun itinerario nella finestra, ed e' la stessa limitazione gia' misurata
nell'argomento sulla ricerca, dove la finestra non bastava sul 14-22% delle
coppie. Delle catene utilizzabili, 11 a Roma e 13 a Torino arrivano alle quattro
tratte complete.

I domini contengono **15,7 ± 5,6 itinerari per tratta**: sono abbastanza ricchi
perche' la scelta sia una scelta vera e non un'assegnazione obbligata, il che e'
il primo requisito perche' il problema sia interessante.

**Il risultato principale.** Su **244 istanze risolubili, la strategia sequenziale
ne dichiara infattibili 45, cioe' il 18,4%**: 16,5% a Roma e 20,3% a Torino. Quasi
una istanza su cinque richiede di tornare indietro su una scelta gia' fatta. Il
fenomeno costruito a mano nel sommario non e' dunque una curiosita' di laboratorio:
e' frequente.

Tabella 12 — Effetto del margine sul tetto dei cambi. Il margine e' lo scarto fra
il tetto imposto e il minimo ottenibile guardando ogni tratta separatamente;
margine zero significa che ogni tratta deve usare il proprio itinerario con meno
cambi. Aggregata sui viaggi a due, tre e quattro tappe.

| Citta' | Margine | Istanze | Risolubili | Il greedy risolve | Il greedy sbaglia |
| --- | ---: | ---: | ---: | ---: | ---: |
| Roma | 0 | 47 | 15 | 11 | 4 (26,7%) |
| Roma | 1 | 47 | 26 | 22 | 4 (15,4%) |
| Roma | 2 | 47 | 37 | 30 | 7 (18,9%) |
| Roma | 3 | 47 | 43 | 38 | 5 (11,6%) |
| Torino | 0 | 44 | 15 | 9 | 6 (40,0%) |
| Torino | 1 | 44 | 29 | 19 | 10 (34,5%) |
| Torino | 2 | 44 | 37 | 31 | 6 (16,2%) |
| Torino | 3 | 44 | 42 | 39 | 3 (7,1%) |

La tabella va letta su due colonne insieme. La colonna **risolubili** cresce in
modo netto con il margine — da 15 a 43 su Roma, da 15 a 42 su Torino — e non
sorprende: allentando il tetto, istanze prima impossibili diventano possibili. A
margine zero **meno di un terzo** delle istanze ha una soluzione, il che dice che
imporre a ogni tratta il proprio itinerario piu' economico in cambi e' un vincolo
molto severo una volta che le tratte devono anche incastrarsi fra loro.

La colonna **il greedy sbaglia** e' quella che risponde alla domanda, e su Torino
scende in modo monotono: 40,0%, 34,5%, 16,2%, 7,1%. Piu' il budget e' stretto,
piu' spesso la strategia sequenziale si acceca da sola scegliendo l'arrivo piu'
precoce. Roma segue lo stesso andamento con un'oscillazione fra il margine 1 e il
2, 15,4% contro 18,9%, che su numeri di questa taglia — quattro e sette casi — non
e' distinguibile dal rumore campionario. Il verso pero' e' inequivocabile agli
estremi, 26,7% contro 11,6%. **E' la conferma sperimentale che a far fallire il
greedy sia il budget globale**, perche' allentando quello e lasciando tutto il
resto invariato il fallimento si dirada.

**Le righe non hanno tutte lo stesso peso, e la percentuale da sola non lo dice.**
La quota di fallimento e' calcolata sulle sole istanze risolubili, e quel
denominatore varia moltissimo lungo la tabella: a margine tre poggia su 43 e 42
casi, a margine zero su 15 e 15. Le due righe a margine zero, che sono anche
quelle con le percentuali piu' alte, sono percio' le **meno solide** della
tabella: il 26,7% di Roma sono quattro casi su quindici e il 40,0% di Torino sei
su quindici, e uno o due casi in piu' o in meno sposterebbero la percentuale di
sei o sette punti. Vanno lette come indicazione della direzione, non come stima
del valore. Le righe a margine due e tre, con denominatori fra 37 e 43, reggono
invece un'interpretazione quantitativa. La stessa cautela vale per la Tabella 13,
dove il 33,3% di Roma a quattro tappe sono **quattro casi su dodici**, mentre
l'11,8% a due tappe poggia su 68: la monotonia della colonna e' significativa
perche' si presenta identica su entrambe le citta', ma il valore dell'ultima riga
di Roma non lo e' altrettanto. In generale, in queste due tabelle il denominatore
cala proprio dove la percentuale cresce, e leggere le percentuali senza guardare
la colonna "risolubili" porterebbe a sopravvalutare gli estremi.

Va notato che il fallimento **non scompare** nemmeno a margine tre, dove resta
all'11,6% e al 7,1%. Il tetto continua a stringere in qualche istanza anche
quando e' generoso, il che e' coerente con il fatto che il minimo per tratta e' un
limite inferiore non raggiungibile: nulla garantisce che esista un'assegnazione
che lo realizzi su tutte le tratte contemporaneamente.

Tabella 13 — Effetto del numero di tappe, aggregata sui quattro margini.

| Citta' | Tappe | Istanze | Risolubili | Il greedy risolve | Il greedy sbaglia |
| --- | ---: | ---: | ---: | ---: | ---: |
| Roma | 2 | 80 | 68 | 60 | 8 (11,8%) |
| Roma | 3 | 64 | 41 | 33 | 8 (19,5%) |
| Roma | 4 | 44 | 12 | 8 | 4 (33,3%) |
| Torino | 2 | 68 | 58 | 48 | 10 (17,2%) |
| Torino | 3 | 56 | 35 | 28 | 7 (20,0%) |
| Torino | 4 | 52 | 30 | 22 | 8 (26,7%) |

Questa e' la lettura piu' pulita dell'esperimento, perche' la crescita e'
**monotona su entrambe le citta' senza eccezioni**: 11,8%, 19,5%, 33,3% a Roma e
17,2%, 20,0%, 26,7% a Torino. Ogni tappa aggiunta rende piu' probabile che una
scelta locale ottima precluda il resto del viaggio, ed e' esattamente cio' che ci
si attende quando le variabili sono accoppiate da un vincolo di somma: piu' sono
le variabili che condividono un budget, piu' modi ci sono di spenderlo male. Su un
viaggio a quattro tappe a Roma la strategia sequenziale sbaglia in **un caso su
tre**.

La colonna **risolubili** cala al crescere delle tappe — 68, 41, 12 a Roma — per
due ragioni distinte che vale la pena separare: le catene lunghe sono meno
numerose, perche' alcune si interrompono prima; e a parita' di margine un viaggio
con piu' tappe ha piu' vincoli da soddisfare contemporaneamente. Il calo e' piu'
marcato a Roma, dove restano dodici istanze risolubili su quarantaquattro a
quattro tappe: e' la riga a cui si applica la cautela enunciata sopra sulla
sottigliezza della base.

**Il costo della risoluzione e' trascurabile, e la conseguenza non e' ovvia.** Il
risolutore completo esplora in media 209 assegnazioni parziali, con un massimo di
3.115, e impiega **0,07 ms in media e 1,1 ms nel caso peggiore**; a quattro tappe
la media sale a 410 nodi e 0,13 ms. Il confronto con l'argomento sulla base di
conoscenza e' istruttivo: li' il costo era interamente di istanziazione e non di
ricerca, e qui accade qualcosa di analogo ma spostato di un livello. **Tutto il
costo di questo modulo sta nel costruire i domini**, cioe' nelle ricerche di
Pareto che li producono — nell'ordine dei secondi ciascuna — mentre il
soddisfacimento dei vincoli su quei domini e' gratuito.

Ne discende una conseguenza pratica che va dichiarata perche' contraddice
un'attesa iniziale. Riscrivere il risolutore come programma a vincoli in Answer
Set Programming, che era il passo successivo previsto, **non porterebbe alcun
guadagno di prestazioni**, dal momento che la risoluzione costa gia' meno di un
millesimo di secondo. Porterebbe altro, e sarebbe comunque utile: la possibilita'
di aggiungere un vincolo senza riscrivere codice, e la dimostrazione che lo stesso
strumento usato in modo puramente deduttivo nel primo argomento sa anche cercare.
Ma la giustificazione sarebbe di espressivita', non di velocita', e presentarla
altrimenti sarebbe scorretto.

**Che cosa manca a questo argomento.** Sono state eseguite la formulazione, il
controesempio e la misura che la giustifica; restano fuori tre cose, dichiarate
qui e riprese fra gli sviluppi possibili. La **codifica in Answer Set
Programming** dei vincoli, con il confronto fra il costo di istanziazione e quello
di ricerca sullo stesso strumento del primo argomento. La **transizione di fase**,
cioe' la mappa della soddisfacibilita' e del costo al variare congiunto
dell'ampiezza delle finestre e dei due budget, di cui la colonna "risolubili" delle
tabelle qui sopra e' soltanto una sezione. E il **budget del cammino**, che in
questo esperimento e' stato lasciato largo di proposito per isolare l'effetto dei
cambi, e che stringendolo produrrebbe un secondo accoppiamento indipendente dal
primo — quello che interessa piu' da vicino il passeggero a ridotta mobilita' per
cui la base di conoscenza deriva la relazione di accessibilita'.

Questo argomento non ha una figura. Le tabelle riportano due sezioni di una
superficie a due parametri, e disegnarla per intero e' esattamente
l'esperimento sulla transizione di fase che non e' stato eseguito: una figura
costruita sui soli dati disponibili mostrerebbe due linee, non la superficie, e
direbbe meno delle tabelle. Dati grezzi in `results/csp_greedy.csv`, 364 righe.

Nessun risultato di questo argomento dipende da un modello dei ritardi: sono tutti
calcolati sull'orario programmato pubblicato dalle due aziende.

# Conclusioni

Il sistema realizzato deriva da dati aperti una relazione che quei dati non
contengono, cerca su di essa gli itinerari non dominati fra tre criteri, e sceglie
fra questi quello che massimizza la probabilita' di arrivare entro una scadenza.
Le tre parti sono state misurate separatamente, e ciascuna ha prodotto un
risultato che vale la pena riassumere.

La base di conoscenza si e' rivelata sostenibile a piena scala — undici secondi e
mezzo per istanziare l'intera rete di Roma, 4,5 milioni di atomi — e la misura ha
attribuito il costo a una regola precisa, la chiusura transitiva, che a duemila
fermate genera da sola il 92,9% degli atomi. Poiche' quella relazione serve di
rado al pianificatore, il costo si riduce di un ordine di grandezza
disattivandola, e il fatto che la scelta si possa compiere a valle senza
riformulare le regole e' una proprieta' della rappresentazione dichiarativa, non
un accorgimento implementativo. Il confronto fra due citta' ha inoltre mostrato
che a determinare il costo non e' la dimensione della rete ma la sua densita'
locale: a parita' di fermate Roma costa 5,4 volte Torino.

La ricerca ha prodotto due risultati negativi, entrambi istruttivi. L'euristica
geografica, benche' dimostrabilmente ammissibile, risparmia il 7,7% degli stati a
Roma e il 3,8% a Torino e fa impiegare ad A* piu' tempo di Dijkstra, perche'
l'ammissibilita' obbliga a tarare la velocita' massima su archi anomali
dell'orario che dichiarano quattrocento metri percorsi in tre secondi: meno di un
arco su cinquemila determina il valore di `V` e con esso l'efficacia dell'euristica
su tutti gli altri. La misura del costo dei cambi nello stato ha invece mostrato
che un'ottimizzazione apparentemente gratuita — proiettare via il conteggio dei
cambi, che riduce di due terzi gli stati espansi — restituisce l'itinerario
sbagliato su nove interrogazioni su settantanove, e la causa isolata
sperimentalmente e' l'interazione con il tetto sul numero di cambi. In direzione
opposta, la relazione di dominanza sugli stati a terra ha ridotto lo spazio di
ricerca da 6,4 milioni di stati in 224 secondi a 45 mila in 0,7, senza alcuna
perdita di ottimalita': e' la differenza fra una campagna sperimentale eseguibile
e una che non lo e'.

Il ragionamento probabilistico ha mostrato di non essere riducibile a una
penalizzazione del tempo di viaggio: al variare della sola scadenza, la scelta
robusta si discosta da quella piu' veloce su una frazione crescente delle coppie,
dal dodici-quindici per cento a margine nullo al trentotto-quarantacinque per
cento a trenta minuti. Il guadagno ha una forma a campana con massimo fra i
quindici e i venti minuti di margine, dove il criterio probabilistico guadagna fra
otto e dieci punti percentuali di probabilita' di arrivo, ed e' quello il campo di
applicabilita' del metodo. Un risultato inatteso e' che la strategia di riferimento
piu' plausibile, quella che impone cinque minuti di margine su ogni coincidenza,
risulta la peggiore delle tre: si difende dalle coincidenze perse senza guardare
alla scadenza, e in un problema in cui la scadenza e' il vincolo si difende dal
rischio sbagliato. Questi numeri sono pero' calcolati su distribuzioni di ritardo
sintetiche, e qualificano il metodo, non il trasporto pubblico di Roma o di
Torino.

Il viaggio con piu' tappe obbligate si e' rivelato un problema di soddisfacimento
di vincoli anche nei fatti, e non solo nella formulazione. La verifica era la
condizione perche' l'argomento avesse diritto di esistere ed e' stata fatta per
prima: su 244 istanze risolubili ricavate dalla rete vera, la strategia
sequenziale che sceglie a ogni tappa l'arrivo piu' precoce senza mai tornare
indietro ne dichiara infattibili **45, cioe' il 18,4%**. La quota cresce in modo
monotono su entrambe le citta' con il numero di tappe — dall'11,8% al 33,3% a
Roma, dal 17,2% al 26,7% a Torino — e cala allentando il tetto sui cambi, che e'
la conferma sperimentale di quale vincolo produca l'accoppiamento. Un
sottoprodotto inatteso della misura riguarda il costo: il soddisfacimento dei
vincoli e' gratuito, meno di un millesimo di secondo per istanza, e tutto il costo
del modulo sta nel calcolare i domini.

## Problematiche non affrontate, e possibili estensioni

Le lacune che seguono sono dichiarate per esteso, perche' un elenco preciso di
cio' che manca e' piu' utile di una sezione che lo nasconda, e perche' ciascuna di
esse e' un punto da cui un altro gruppo potrebbe ripartire.

**La risposta alla domanda di ricerca non c'e' ancora.** E' la lacuna piu'
importante. Il vantaggio del criterio probabilistico e' stato misurato su ritardi
inventati; se si conservi sui ritardi reali e' esattamente cio' che resta da
verificare. La raccolta e' completa e funzionante, con quattro giornate gia'
consolidate per 74 MB, ma la stima delle distribuzioni e il conseguente
backtesting non sono stati eseguiti.

**Una strada considerata e scartata, con la ragione: i Knowledge Graph e le
ontologie.** L'ipotesi e' stata valutata concretamente — pubblicare la base di
conoscenza come grafo RDF con un vocabolario OWL minimo per fermate, stazioni,
linee, trasbordi e accessibilita', e interrogarla in SPARQL sfruttando la
gerarchia delle classi e un reasoner. E' stata scartata, e la ragione non e' di
tempo.

La ragione debole e' che non siamo riusciti a formulare una domanda a cui il
grafo rispondesse meglio di quanto gia' facciamo. La gerarchia di classi con
sussunzione, i cammini di proprieta' per la chiusura transitiva dei trasbordi, le
proprieta' simmetriche e inverse: sono tutte cose che le regole del primo
argomento derivano gia', e in piu' con il tempo minimo difettibile lungo la
catena, che un cammino di proprieta' non sa calcolare. Un'ontologia costruita
sopra fatti che deriviamo gia', interrogata con query di complessita' logica
inferiore a quella delle regole che abbiamo scritto, sarebbe una piccola ontologia
usata come base di dati.

La ragione forte e' che **sarebbe stato un regresso di espressivita'**. OWL e' un
formalismo **monotono**: aggiungere assiomi non puo' mai togliere conclusioni. Ma
le due proprieta' migliori della nostra base di conoscenza sono esattamente
quelle che la monotonia esclude. L'eredita' difettibile del tempo minimo di
trasbordo, in cui una dichiarazione dell'azienda sovrascrive il default di
stazione che a sua volta sovrascrive il default di cammino, non e' esprimibile in
OWL, perche' richiede che una regola piu' specifica **disattivi** una piu'
generale. La non monotonia dell'accessibilita' lo e' ancora meno: nel nostro
programma l'aggiunta del fatto che un ascensore e' fuori servizio **rimuove**
quattro conclusioni gia' derivate, e nessun formalismo monotono puo' comportarsi
cosi'. Tradurre la base di conoscenza in un'ontologia avrebbe significato buttare
via cio' che la rende difendibile come base di conoscenza e conservarne la parte
che qualunque base di dati saprebbe replicare: avremmo aggiunto un capitolo che
indebolisce l'argomento del capitolo precedente.

Va detto per completezza che restava possibile una versione minima, cioe'
esportare il grafo come artefatto di **interoperabilita'**, dichiarando
esplicitamente che non e' un contributo di rappresentazione. Anche quella e' stata
scartata, perche' spende ore per un'etichetta e perche' chi legge "Knowledge
Graph" e trova una serializzazione ha piu' motivi di penalizzare che di premiare.
La scelta di Answer Set Programming e' stata dunque compiuta sapendo che cosa
comportava, e questo paragrafo ne e' il conto.

**Le altre lacune di copertura del programma.** Le **reti bayesiane** non
compaiono ancora: la dipendenza fra
il ritardo alla salita e quello alla discesa e' rappresentata da un
condizionamento diretto fra due variabili, non da una struttura grafica su cui
eseguire inferenza generale. Una rete bayesiana permetterebbe di aggiungere
variabili esplicative come il meteo, il giorno della settimana o lo stato del
traffico, e di ragionare anche in senso diagnostico, per esempio inferendo dalla
propagazione osservata dei ritardi quale tratto della rete sia congestionato. Il
**soddisfacimento di vincoli** e' invece trattato, ma solo in parte: la
formulazione e la misura che la giustifica sono state eseguite, la codifica
dichiarativa e l'esplorazione dello spazio dei parametri no, come dettagliato piu'
avanti.

**Che cosa manca al viaggio multi-tappa.** Dell'argomento sul soddisfacimento di
vincoli sono state eseguite la formulazione, il controesempio che dimostra
l'assenza di sottostruttura ottima e la misura che ne stabilisce la frequenza.
Restano fuori tre cose. La **codifica dei vincoli in Answer Set Programming**, che
non porterebbe guadagno di prestazioni — la risoluzione costa gia' meno di un
millesimo di secondo — ma permetterebbe di aggiungere un vincolo senza riscrivere
codice, e mostrerebbe lo stesso strumento usato in modo deduttivo nel primo
argomento impiegato per cercare. La **transizione di fase**, cioe' la mappa della
soddisfacibilita' e del costo al variare congiunto dell'ampiezza delle finestre e
dei due budget, di cui le tabelle attuali sono due sezioni. E il **budget del
cammino**, lasciato largo di proposito per isolare l'effetto dei cambi: stringerlo
produrrebbe un accoppiamento indipendente dal primo, ed e' quello che riguarda piu'
da vicino il passeggero a ridotta mobilita' per cui la base di conoscenza deriva
la relazione di accessibilita'.

**I limiti che vengono dai dati.** Nessuna delle due aziende pubblica
`transfers.txt`, quindi il primo livello della gerarchia dei tempi minimi di
trasbordo non riceve alcun fatto; solo due fermate in tutto il progetto
appartengono a una stazione, quindi neppure il secondo. Sui dati disponibili
l'eredita' con default collassa quasi ovunque sul terzo livello, e i primi due sono
collaudati solo su dati costruiti. Roma non dichiara l'accessibilita' di alcuna
fermata — tutte le 8.301 riportano il codice "informazione non disponibile" — e
non dichiara alcuna stazione, quindi la regola dell'accessibilita' vi deriva zero
conclusioni e ogni risultato su quel tema e' riferibile alla sola Torino.
Aggiungere una terza citta' con un archivio piu' ricco renderebbe misurabile cio'
che oggi e' soltanto rappresentabile, e sarebbe l'estensione con il miglior
rapporto fra costo e valore.

**Su Roma il tempo reale copre solo la rete di superficie.** E' un limite emerso
verificando i dati raccolti, e restringe l'ambito del progetto piu' di quanto il
resto del documento lasci intendere. L'orario statico di Roma dichiara quattro
linee di metropolitana con **6.614 corse programmate**, ma nel feed GTFS
Real-Time non compare **nessuna** di esse: delle trecentodieci linee osservate in
tempo reale, tutte sono autobus. Torino si comporta diversamente e trasmette
anche il tram. La conseguenza non e' soltanto descrittiva. Il grafo tempo-espanso
continua a contenere la metropolitana romana, perche' viene dall'orario statico,
ma su quelle corse non esiste alcuna osservazione di ritardo: **su Roma il
modello dei ritardi sara' quindi un modello dei ritardi degli autobus, non del
trasporto pubblico romano**, e ogni risultato che lo impieghi va letto con questa
restrizione. Un itinerario romano che passi per la metropolitana riceverebbe una
probabilita' di arrivo fondata, per quel tratto, sul nulla. La valutazione finale
andra' percio' ristretta alle coppie servite dalla sola superficie, oppure estesa
con un'assunzione esplicita e dichiarata sui ritardi della metropolitana.

**I limiti del modello geometrico.** La distanza fra due fermate e' quella in linea
d'aria e non quella effettivamente percorribile a piedi: in presenza di una
ferrovia, di un fiume o di una tangenziale fra due fermate vicine il tempo di
trasbordo derivato e' ottimistico, e lo e' in modo sistematico perche' l'errore ha
sempre lo stesso segno. Integrare un grafo stradale eliminerebbe
l'approssimazione, al prezzo di una dipendenza da una fonte dati aggiuntiva e di
un costo di calcolo delle distanze molto superiore. Il tempo di cammino e' inoltre
discretizzato in quattro bande anziche' calcolato con continuita', scelta motivata
dal fatto che un tempo di trasbordo ha senso al mezzo minuto e non al metro, ma
che resta un'approssimazione.

**I limiti della ricerca.** Il grafo copre una finestra di due ore a partire
dall'orario richiesto, e la ricerca trova percio' l'ottimo *dentro la finestra*:
su cinquanta coppie origine-destinazione per citta' la finestra si e' rivelata
sufficiente in quarantatre casi a Roma e trentanove a Torino, e sulle restanti non
esiste alcun itinerario nella finestra considerata. Quelle coppie non sono state
escluse dal campione, ma la loro esistenza limita la generalita' dei risultati
alle coppie collegate entro due ore, che sono tipicamente quelle non fra periferie
opposte. La ricerca impone inoltre un tetto di quattro cambi, che e' un vincolo di
realismo ma che interagisce con la rappresentazione dello stato in modo non ovvio,
come la valutazione ha mostrato.

**I limiti del modello probabilistico.** Il numero di recuperi dopo una
coincidenza persa e' limitato a due, e sulle valutazioni della griglia il 9,2%
della massa di probabilita' esaurisce quel tetto: e' abbastanza da meritare una
menzione, e un valore piu' alto renderebbe il risultato piu' dipendente dal tetto
che dal modello. La scadenza e' definita in modo relativo all'itinerario piu'
veloce, scelta che aderisce alla domanda di ricerca ma che e' severa verso il
criterio probabilistico e che rende il vantaggio misurato un limite inferiore.
L'insieme dei candidati e' la frontiera di Pareto, che collassa fra loro gli
itinerari differenti solo per il margine sulle coincidenze; la misura ha mostrato
che la frontiera e' comunque abbastanza ricca, con un'ampiezza media di 0,44, ma
un insieme candidato costruito apposta nella dimensione dei margini resta
un'estensione possibile e sarebbe il modo naturale di verificare se il vantaggio
misurato cresca. Infine il modello tratta la correlazione lungo la corsa con un
solo parametro scalare, mentre nella realta' essa dipende verosimilmente dal tratto
di percorso e dall'ora, e stimarla in forma condizionata e' parte del lavoro
rimasto.

# Riferimenti Bibliografici

[1] D. L. Poole, A. K. Mackworth. *Artificial Intelligence: Foundations of
Computational Agents*. 3ª edizione, Cambridge University Press, 2023. Testo di
riferimento del corso; i richiami nel documento indicano il capitolo pertinente.

[2] G. Brewka, T. Eiter, M. Truszczyński. *Answer Set Programming at a Glance*.
Communications of the ACM, 54(12):92-103, 2011.

[3] M. Gelfond, V. Lifschitz. *The Stable Model Semantics for Logic Programming*.
Proceedings of the 5th International Conference on Logic Programming, pp.
1070-1080, 1988.

[4] M. Gebser, R. Kaminski, B. Kaufmann, T. Schaub. *Multi-shot ASP solving with
clingo*. Theory and Practice of Logic Programming, 19(1):27-82, 2019. Sistema e
documentazione: <https://potassco.org/clingo/>.

[5] *General Transit Feed Specification (GTFS) Schedule Reference*.
<https://gtfs.org/schedule/reference/>.

[6] W. McKinney. *Data Structures for Statistical Computing in Python*.
Proceedings of the 9th Python in Science Conference, pp. 56-61, 2010.
Documentazione: <https://pandas.pydata.org/>.

[7] E. Pyrga, F. Schulz, D. Wagner, C. Zaroliagis. *Efficient models for timetable
information in public transportation systems*. ACM Journal of Experimental
Algorithmics, 12:2.4:1-2.4:39, 2008.

[8] P. E. Hart, N. J. Nilsson, B. Raphael. *A Formal Basis for the Heuristic
Determination of Minimum Cost Paths*. IEEE Transactions on Systems Science and
Cybernetics, 4(2):100-107, 1968.

[9] E. Q. V. Martins. *On a multicriteria shortest path problem*. European Journal
of Operational Research, 16(2):236-245, 1984.

[10] C. R. Harris et al. *Array programming with NumPy*. Nature, 585:357-362,
2020.

[11] C. P. Robert, G. Casella. *Monte Carlo Statistical Methods*. 2ª edizione,
Springer, 2004.

[12] P. Virtanen et al. *SciPy 1.0: fundamental algorithms for scientific
computing in Python*. Nature Methods, 17:261-272, 2020.

[13] F. Pedregosa et al. *Scikit-learn: Machine Learning in Python*. Journal of
Machine Learning Research, 12:2825-2830, 2011.

[14] *GTFS Realtime Reference*. <https://gtfs.org/realtime/reference/>.
Associazione Python: `gtfs-realtime-bindings`.

[15] Roma Mobilità. Dati aperti del trasporto pubblico di Roma: orario statico
<https://romamobilita.it/sites/default/files/rome_static_gtfs.zip> e feed
real-time `rome_rtgtfs_trip_updates_feed.pb` e
`rome_rtgtfs_vehicle_positions_feed.pb` sullo stesso dominio.

[16] Gruppo Torinese Trasporti. Dati aperti del trasporto pubblico di Torino:
orario statico <https://www.gtt.to.it/open_data/gtt_gtfs.zip> e feed real-time
<https://percorsieorari.gtt.to.it/das_gtfsrt/>.

[17] J. D. Hunter. *Matplotlib: A 2D Graphics Environment*. Computing in Science &
Engineering, 9(3):90-95, 2007.
