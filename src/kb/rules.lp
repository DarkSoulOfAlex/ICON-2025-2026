%%%============================================================================
%%% BASE DI CONOSCENZA DEI TRASBORDI
%%%
%%% Deriva la relazione di trasbordo fra fermate del trasporto pubblico a
%%% partire dai soli fatti che il GTFS mette a disposizione.
%%%
%%% Perche' questa e' una base di conoscenza e non un database interrogato.
%%% Nessuna delle due aziende del progetto (Roma Mobilita', GTT Torino)
%%% pubblica transfers.txt: la relazione di trasbordo NON ESISTE nei dati di
%%% partenza. Non c'e' alcuna tabella da leggere, filtrare o giuntare. Tutto
%%% cio' che segue e' derivato da fermate, coordinate, gerarchia delle stazioni
%%% e accessibilita' dichiarata, applicando regole che un'interrogazione
%%% relazionale non saprebbe esprimere: eredita' difettibile, negazione per
%%% fallimento, ricorsione e vincoli che rifiutano il modello.
%%%
%%% Ogni regola porta l'annotazione [NON-SQL] con la ragione per cui non e'
%%% sostituibile da una SELECT, e ogni negazione l'annotazione [NEGAZIONE].
%%%============================================================================

%%%----------------------------------------------------------------------------
%%% PARAMETRI
%%%
%%% Sono #const e non fatti perche' sono parametri del modello, non conoscenza
%%% sul mondo: cambiarli e' un esperimento, non un aggiornamento dei dati.
%%%----------------------------------------------------------------------------

% Distanza massima di un trasbordo a piedi, in metri.
#const soglia_piedi = 250.

% Tempo minimo per un trasbordo fra due banchine della stessa stazione.
% Piu' alto del tempo di puro cammino: dentro una stazione si percorrono
% sottopassi, scale e tornelli.
#const tempo_stazione = 180.

% Margine aggiunto al tempo di cammino all'aperto: attraversamenti, semafori,
% l'attesa di capire da che parte si va.
#const margine_piedi = 60.

% Oltre questo tempo di cammino un trasbordo non e' piu' considerato
% praticabile da chi ha ridotta mobilita'.
#const tempo_piedi_max_sedia = 180.

% Numero di trasbordi a piedi oltre il quale una fermata e' sospetta: vedere
% il vincolo di integrita' 4.
#const grado_massimo_plausibile = 40.

% Interruttore dei vincoli di integrita'. Serve alla diagnostica: quando il
% programma risulta insoddisfacibile si rilancia con con_vincoli=0 per capire
% quale vincolo abbia rifiutato il modello, invece di restare senza risposta.
#const con_vincoli = 1.

% Interruttori usati SOLO dalla misura di complessita', per attribuire il costo
% alle singole regole invece di dedurlo. Con con_indice=0 la regola `candidata`
% confronta tutte le coppie di fermate: serve a verificare che l'indice non
% cambi il risultato e a misurare quanto costa non averlo. Con con_chiusura=0 la
% ricorsione non viene calcolata: la differenza fra le due esecuzioni misura
% quanti atomi nascano dalla sola chiusura transitiva.
#const con_indice = 1.
#const con_chiusura = 1.

%%%----------------------------------------------------------------------------
%%% FATTI ATTESI DAL GTFS (generati da src/kb/engine.py)
%%%
%%%   fermata(F).              F e' una fermata fisica (location_type = 0)
%%%   coord(F, X, Y).          posizione in METRI interi su un piano locale
%%%   cella(F, I, J).          cella dell'indice spaziale a cui F appartiene
%%%   in_stazione(F, S).       F e' una banchina della stazione S
%%%   accesso_sedia(F, V).     0 = non dichiarato, 1 = accessibile, 2 = no
%%%   serve(R, F).             la linea R ferma in F
%%%   dichiarato(F1, F2, T).   trasbordo dichiarato in transfers.txt
%%%   ascensore_fuori_servizio(F).   informazione contingente, opzionale
%%%
%%% Le coordinate arrivano gia' in metri su una proiezione piana locale invece
%%% che in gradi. Non e' conoscenza spostata fuori dalla KB: e' un cambio di
%%% unita' di misura sui dati in ingresso, esattamente come conservare gli orari
%%% in secondi invece che in "HH:MM:SS". La regola che decide quali coppie siano
%%% trasbordi resta interamente qui sotto.
%%%----------------------------------------------------------------------------

%%%============================================================================
%%% 1. INDICE SPAZIALE
%%%
%%% Confrontare tutte le coppie di fermate significa istanziare N^2 atomi: su
%%% Roma, con 8.301 fermate, sono circa 69 milioni di coppie, e il grounding non
%%% termina in tempo utile. L'indice restringe il confronto alle fermate che
%%% stanno nella stessa cella o in una delle otto adiacenti.
%%%
%%% L'indice NON altera la semantica, e la ragione e' geometrica: il lato della
%%% cella e' pari alla soglia di cammino, quindi due fermate a meno di
%%% `soglia_piedi` metri non possono cadere in celle non adiacenti. L'insieme
%%% dei trasbordi derivati e' percio' identico a quello che si otterrebbe
%%% confrontando tutte le coppie. La condizione lato >= soglia e' verificata da
%%% engine.py prima di generare i fatti.
%%%
%%% Non e' clustering: non c'e' nulla di appreso, nessun centroide, nessuna
%%% funzione obiettivo. E' un'indicizzazione deterministica sulle coordinate,
%%% l'equivalente spaziale di un indice su una colonna.
%%%============================================================================

scarto(-1..1).

candidata(F1, F2) :-
    con_indice = 1,
    cella(F1, I1, J1),
    scarto(DI), scarto(DJ),
    cella(F2, I1 + DI, J1 + DJ),
    F1 != F2.

% Variante esaustiva, attiva solo quando l'indice e' disattivato.
candidata(F1, F2) :-
    con_indice = 0,
    fermata(F1),
    fermata(F2),
    F1 != F2.

%%%============================================================================
%%% 2. DISTANZA E TEMPO DI CAMMINO
%%%============================================================================

% Distanza al quadrato, in metri quadri. Si lavora sul quadrato perche' la
% radice quadrata non e' esprimibile in aritmetica intera senza generare un
% candidato per ogni valore possibile, il che moltiplicherebbe il grounding per
% il numero di metri della soglia.
distanza2(F1, F2, D2) :-
    candidata(F1, F2),
    coord(F1, X1, Y1),
    coord(F2, X2, Y2),
    D2 = (X1 - X2) * (X1 - X2) + (Y1 - Y2) * (Y1 - Y2).

% Bande di cammino: soglia al quadrato -> secondi. Discretizzare a bande invece
% di calcolare un tempo esatto e' una scelta di modello, non un'approssimazione
% subita: un tempo di trasbordo ha senso al mezzo minuto, non al metro.
banda_piedi(  2500,  60).   % fino a  50 m
banda_piedi( 10000, 120).   % fino a 100 m
banda_piedi( 40000, 180).   % fino a 200 m
banda_piedi( 62500, 240).   % fino a 250 m

% [NON-SQL] Il tempo di cammino e' il MINIMO fra i tempi di tutte le bande che
% contengono la distanza: un aggregato calcolato su una relazione a sua volta
% derivata (distanza2), non una colonna da leggere. Se nessuna banda contiene la
% distanza, l'aggregato non produce nulla e la coppia semplicemente non e' un
% trasbordo a piedi: e' la soglia che emerge dalle regole, non un WHERE.
tempo_piedi(F1, F2, T) :-
    distanza2(F1, F2, D2),
    T = #min { S : banda_piedi(M, S), D2 <= M },
    T <= 240.

trasbordo_a_piedi(F1, F2) :- tempo_piedi(F1, F2, _).

%%%============================================================================
%%% 3. STAZIONI
%%%============================================================================

% Due banchine distinte della stessa stazione. La relazione non e' nei dati:
% il GTFS dichiara solo il legame banchina -> stazione, ed e' questa regola a
% derivarne la relazione fra pari.
stessa_stazione(F1, F2) :-
    in_stazione(F1, S),
    in_stazione(F2, S),
    F1 != F2.

%%%============================================================================
%%% 4. TEMPO MINIMO DI TRASBORDO: EREDITA' DIFETTIBILE
%%%
%%% [NON-SQL] E' la regola piu' significativa del progetto. Il tempo minimo non
%%% e' un valore memorizzato da cercare: e' il risultato di una gerarchia di
%%% priorita' con eccezioni. Vale il dato dichiarato dall'azienda; in sua
%%% assenza vale la regola della stazione; in assenza di entrambi vale il tempo
%%% di cammino piu' un margine.
%%%
%%% Una SELECT puo' riprodurre questo comportamento solo se la gerarchia di
%%% priorita' e' gia' scritta dentro la query, cioe' se la conoscenza sta nel
%%% codice dell'interrogazione e non nella base di conoscenza. Qui la gerarchia
%%% e' dichiarata: aggiungere un livello significa aggiungere una regola, non
%%% riscrivere le altre.
%%%
%%% [NEGAZIONE] I tre `not` qui sotto sono l'unico meccanismo che realizza la
%%% priorita'. La negazione e' STRATIFICATA: `dichiarato` e' un fatto in
%%% ingresso, `stessa_stazione` dipende solo da `in_stazione`, e nessuno dei due
%%% dipende, nemmeno indirettamente, da `tempo_minimo_trasbordo`. Il grafo delle
%%% dipendenze non ha quindi cicli che attraversino una negazione, e il
%%% programma ha un unico modello ben definito.
%%%============================================================================

% Livello 1 (massima priorita'): quanto dichiara l'azienda.
tempo_minimo_trasbordo(F1, F2, T) :-
    dichiarato(F1, F2, T).

% Livello 2: stessa stazione, salvo che l'azienda dica altro.
tempo_minimo_trasbordo(F1, F2, tempo_stazione) :-
    stessa_stazione(F1, F2),
    not dichiarato(F1, F2, _).

% Livello 3: cammino all'aperto, salvo i due casi precedenti.
tempo_minimo_trasbordo(F1, F2, T + margine_piedi) :-
    tempo_piedi(F1, F2, T),
    not dichiarato(F1, F2, _),
    not stessa_stazione(F1, F2).

%%%============================================================================
%%% 5. TRASBORDO AMMISSIBILE E TRASBORDO UTILE
%%%============================================================================

trasbordo_ammissibile(F1, F2, T) :-
    tempo_minimo_trasbordo(F1, F2, T),
    fermata(F1),
    fermata(F2).

% [NON-SQL] Un trasbordo e' utile se da' accesso ad almeno una linea che dalla
% fermata di partenza non era gia' raggiungibile. La condizione e' una negazione
% su una relazione (`serve`) quantificata: "esiste una linea R che serve F2 e
% che NON serve F1". Non e' una giunzione, e' una differenza insiemistica
% calcolata per ogni coppia.
% [NEGAZIONE] Stratificata: `serve` e' un fatto in ingresso.
trasbordo_utile(F1, F2) :-
    trasbordo_ammissibile(F1, F2, _),
    serve(R, F2),
    not serve(R, F1).

%%%============================================================================
%%% 6. ACCESSIBILITA': DEFAULT CON ECCEZIONI
%%%
%%% [NON-SQL] Qui la conoscenza e' NON MONOTONA: aggiungere un fatto TOGLIE
%%% conclusioni. Dichiarare che un ascensore e' fuori servizio non aggiunge
%%% righe a un risultato, ne rimuove. Nessuna interrogazione relazionale ha
%%% questo comportamento, perche' in algebra relazionale aggiungere tuple a una
%%% relazione non puo' mai ridurre il risultato di una query positiva.
%%%============================================================================

% Il GTFS codifica 0 come "nessuna informazione, eredita dalla stazione".
% Questa e' quindi a sua volta un'eredita' con default.
% [NEGAZIONE] Stratificata: dipende solo dai fatti in ingresso.
fermata_accessibile(F) :-
    accesso_sedia(F, 1).

fermata_accessibile(F) :-
    accesso_sedia(F, 0),
    in_stazione(F, S),
    accesso_sedia(S, 1).

% Le eccezioni. Sono derivate, non dichiarate: un trasbordo a piedi troppo lungo
% diventa inaccessibile in forza della sua distanza, senza che nessuno lo
% annoti.
eccezione_accessibilita(F1, F2) :-
    tempo_piedi(F1, F2, T),
    T > tempo_piedi_max_sedia.

eccezione_accessibilita(F1, F2) :-
    trasbordo_ammissibile(F1, F2, _),
    ascensore_fuori_servizio(F1).

eccezione_accessibilita(F1, F2) :-
    trasbordo_ammissibile(F1, F2, _),
    ascensore_fuori_servizio(F2).

accessibile(F1, F2) :-
    trasbordo_ammissibile(F1, F2, _),
    fermata_accessibile(F1),
    fermata_accessibile(F2),
    not eccezione_accessibilita(F1, F2).

%%%============================================================================
%%% 7. RAGGIUNGIBILITA': CHIUSURA TRANSITIVA RICORSIVA
%%%
%%% [NON-SQL] La ricorsione e' esplicita e non ha profondita' nota a priori: il
%%% numero di trasbordi concatenati necessari a collegare due fermate dipende
%%% dalla rete e non e' limitabile in anticipo. Un'algebra relazionale di base
%%% non puo' esprimerla affatto; una WITH RECURSIVE puo', ma a quel punto si sta
%%% programmando la chiusura a mano, mentre qui il punto fisso e' calcolato dal
%%% risolutore a partire dalla definizione dichiarativa.
%%%
%%% E' anche la regola che domina il costo: la chiusura transitiva di una
%%% relazione densa cresce quadraticamente nel numero di fermate raggiungibili
%%% fra loro. La curva di complessita' misurata in results/complessita_kb.png
%%% serve proprio a mostrarlo.
%%%============================================================================

raggiungibile(F, F) :- fermata(F), con_chiusura = 1.

raggiungibile(F1, F3) :-
    raggiungibile(F1, F2),
    trasbordo_ammissibile(F2, F3, _).


% Analogo ristretto ai soli trasbordi accessibili: la stessa chiusura, calcolata
% su una relazione piu' piccola. Serve a rispondere alla domanda "un utente in
% sedia a rotelle puo' passare da qui a li'?", che non e' la stessa domanda.
raggiungibile_accessibile(F, F) :- fermata(F), fermata_accessibile(F), con_chiusura = 1.

raggiungibile_accessibile(F1, F3) :-
    raggiungibile_accessibile(F1, F2),
    accessibile(F2, F3).

%%%============================================================================
%%% 8. VINCOLI DI INTEGRITA'
%%%
%%% [NON-SQL] Un vincolo non filtra righe: RIFIUTA IL MODELLO. Se una sola
%%% coppia lo viola, il programma non ha alcuna risposta, non una risposta piu'
%%% corta. E' una condizione sull'intera interpretazione, di natura diversa da
%%% qualunque WHERE, e serve a garantire che cio' che esce dalla base di
%%% conoscenza sia coerente per costruzione invece che per controllo a valle.
%%%============================================================================

% Nota di onesta' intellettuale. Un vincolo che non puo' mai essere violato non
% dimostra nulla: e' commento travestito da logica. I quattro che seguono sono
% stati scelti perche' possono davvero scattare sui dati reali, e ciascuno
% corrisponde a un difetto documentato dei GTFS pubblicati. Vincoli tautologici
% come il divieto di trasbordo di una fermata con se stessa sono stati scartati
% proprio perche' la costruzione di `candidata` li rende impossibili per
% definizione.

% V1. Nessuna fermata puo' avere un numero implausibile di trasbordi a piedi.
% Intercetta il difetto piu' frequente dei dati aperti: le fermate con
% coordinate mancanti finiscono tutte nello stesso punto e risultano a distanza
% zero l'una dall'altra. Senza il vincolo diventerebbero un nodo di scambio
% inesistente ma enorme, e il pianificatore ci costruirebbe sopra itinerari
% impossibili. E' anche l'unico vincolo che usa un aggregato di cardinalita'.
:- fermata(F), #count { F2 : trasbordo_a_piedi(F, F2) } > grado_massimo_plausibile,
   con_vincoli = 1.

% V2. Nessun trasbordo puo' essere concesso in meno tempo di quanto ne serva a
% percorrerlo a piedi. Intercetta i tempi dichiarati troppo ottimisti, che
% renderebbero il pianificatore sistematicamente troppo fiducioso: e' un errore
% che in Fase 5 si manifesterebbe come coincidenze perse senza spiegazione
% apparente.
:- trasbordo_ammissibile(F1, F2, T), tempo_piedi(F1, F2, TP), T < TP,
   con_vincoli = 1.

% V3. Una banchina non puo' risultare accessibile se la stazione che la contiene
% e' dichiarata NON accessibile: se non si entra nella stazione non si raggiunge
% la banchina, per quanto la banchina sia attrezzata. E' una incoerenza che nei
% dati reali capita, perche' i due campi sono compilati da persone diverse in
% momenti diversi.
:- accessibile(F1, _), in_stazione(F1, S), accesso_sedia(S, 2), con_vincoli = 1.

% V4. Nessun trasbordo puo' richiedere tempo nullo o negativo. Diverse aziende
% pubblicano min_transfer_time = 0 in transfers.txt per indicare "coincidenza
% garantita"; preso alla lettera significherebbe teletrasporto, e un
% pianificatore che ci credesse dichiarerebbe probabilita' di arrivo
% sistematicamente ottimistiche.
:- trasbordo_ammissibile(_, _, T), T <= 0, con_vincoli = 1.

%%%============================================================================
%%% 9. USCITA
%%%============================================================================

#show trasbordo_ammissibile/3.
#show trasbordo_a_piedi/2.
#show accessibile/2.
#show trasbordo_utile/2.
