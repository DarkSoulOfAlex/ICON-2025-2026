"""Composizione delle probabilita' lungo la catena delle coincidenze.

Calcola P(arrivo <= T) per un itinerario, dato un modello dei ritardi. E' il
cuore del progetto: e' qui che l'obiettivo passa da "arrivare presto secondo
l'orario" a "arrivare entro T con alta probabilita'".

**Perche' il prodotto ingenuo delle probabilita' e' sbagliato.** La tentazione e'
scrivere P(arrivo <= T) come prodotto delle probabilita' di prendere ciascuna
coincidenza. Sbaglia per due ragioni di segno opposto, e nessuna delle due e'
trascurabile.

Sovrastima, perche' tratta come indipendenti eventi che non lo sono. Lo stesso
mezzo in ritardo alla quinta fermata e' verosimilmente in ritardo alla
dodicesima: il ritardo si accumula lungo la corsa, e la probabilita' congiunta di
due coincidenze prese non e' il prodotto delle due marginali.

Sottostima, perche' considera fallimento definitivo una coincidenza persa. Chi
perde un autobus prende quello dopo e arriva piu' tardi, il che puo' benissimo
essere ancora entro T. Ignorare il recupero cancella proprio il fenomeno che la
domanda di ricerca vuole misurare: un itinerario e' robusto anche perche', quando
perde una coincidenza, ne trova un'altra presto.

**La struttura vera e' markoviana con azzeramento.** Presa una coincidenza,
l'arrivo a valle dipende dal ritardo del nuovo mezzo e non da quanto per poco la
si e' presa: l'informazione sul ritardo precedente si perde. Il ritardo si
propaga percio' *dentro* una corsa, non *attraverso* un cambio, e la catena va
modellata come una successione di tappe in cui a ogni tappa si sceglie quale
corsa si riesce effettivamente a prendere.

Il modulo offre due modi di calcolare la stessa quantita', per poterli
confrontare: :func:`probabilita_convoluzione`, che propaga le distribuzioni su
una griglia temporale discreta, e :func:`probabilita_montecarlo`, che simula la
catena. Il confronto fra i due e' un artefatto del documento.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from time import perf_counter

import numpy as np

from src.delays.interfaccia import Distribuzione, ModelloRitardo, Tratta

log = logging.getLogger("planner")

# Griglia temporale della convoluzione: passo di 10 secondi su quattro ore.
# Il passo e' un parametro dell'accuratezza e viene misurato, non assunto.
PASSO_SECONDI = 10
ORIZZONTE_SECONDI = 4 * 3600

# Griglia dei ritardi su cui si discretizza il condizionamento fra salita e
# discesa della stessa corsa. Vale per entrambi i metodi, cosi' il confronto
# isola l'errore della griglia TEMPORALE della convoluzione, che e' cio' che
# interessa misurare, invece di mescolarlo con quello del condizionamento.
RITARDO_MINIMO = -300
RITARDO_MASSIMO = 1800
PASSO_RITARDO = 10

INFINITO = 1 << 62


class ErrorePianificatore(Exception):
    """L'itinerario non e' valutabile cosi' com'e'."""


# =============================================================================
# Rappresentazione di un itinerario
# =============================================================================


@dataclass(frozen=True)
class Salita:
    """Una corsa che si puo' prendere per percorrere una tappa."""

    trip_id: str
    route_id: str
    partenza_programmata: int
    arrivo_programmato: int


@dataclass(frozen=True)
class Tappa:
    """Una tratta percorsa a bordo, con le alternative per recuperarla.

    ``alternative`` e' ordinata per orario di partenza: la prima e' la corsa
    pianificata, le successive sono i recuperi possibili sulla stessa linea da
    quella fermata. Averle qui, e non altrove, e' cio' che permette al calcolo di
    rappresentare una coincidenza persa come un ritardo invece che come un
    fallimento.
    """

    fermata_salita: str
    sequenza_salita: int
    fermata_discesa: str
    sequenza_discesa: int
    tempo_minimo_trasbordo: int
    alternative: tuple[Salita, ...]

    def __post_init__(self) -> None:
        if not self.alternative:
            raise ErrorePianificatore("una tappa deve avere almeno una corsa")


@dataclass(frozen=True)
class Itinerario:
    """Una successione di tappe, a partire da un istante di partenza richiesto."""

    citta: str
    partenza_richiesta: int
    tappe: tuple[Tappa, ...]

    @property
    def cambi(self) -> int:
        """Numero di salite oltre la prima."""
        return max(0, len(self.tappe) - 1)

    @property
    def arrivo_programmato(self) -> int:
        return self.tappe[-1].alternative[0].arrivo_programmato

    @property
    def margini_programmati(self) -> tuple[int, ...]:
        """Margine, in secondi, di ogni coincidenza secondo il solo orario.

        E' la grandezza che una persona senza modello probabilistico userebbe per
        giudicare la robustezza di un itinerario, ed e' quella su cui si basa la
        baseline del margine fisso.
        """
        margini = []
        for precedente, corrente in zip(self.tappe, self.tappe[1:]):
            arrivo = precedente.alternative[0].arrivo_programmato
            partenza = corrente.alternative[0].partenza_programmata
            margini.append(partenza - arrivo - corrente.tempo_minimo_trasbordo)
        return tuple(margini)


@dataclass
class EsitoProbabilita:
    """Risultato di una valutazione, con cio' che serve a giudicarne la qualita'."""

    probabilita: float
    metodo: str
    secondi: float
    quota_fallimenti: float
    """Frazione di massa che non arriva affatto entro l'orizzonte."""
    quota_tetto_raggiunto: float
    """Frazione di massa che ha esaurito i recuperi disponibili.

    Va riportata: se fosse alta, il tetto influenzerebbe il risultato piu' del
    modello dei ritardi, e la misura direbbe piu' sul tetto che sul mondo.
    """
    ripetizioni: int = 0


# =============================================================================
# Strumenti comuni
# =============================================================================


def _griglia_ritardi() -> np.ndarray:
    return np.arange(RITARDO_MINIMO, RITARDO_MASSIMO + PASSO_RITARDO, PASSO_RITARDO, dtype=float)


def _pmf_da_distribuzione(distribuzione: Distribuzione, griglia: np.ndarray) -> np.ndarray:
    """Massa di probabilita' sui bin della griglia, dalle differenze della ripartizione.

    Il primo e l'ultimo bin assorbono le code oltre la griglia: la massa deve
    sommare a uno, altrimenti la probabilita' finale sarebbe sistematicamente
    sottostimata di una quantita' che dipende dalla griglia e non dal modello.
    """
    bordi = np.concatenate([[-np.inf], griglia[:-1] + PASSO_RITARDO / 2.0, [np.inf]])
    ripartizione = np.empty(bordi.size)
    ripartizione[0] = 0.0
    ripartizione[-1] = 1.0
    if bordi.size > 2:
        ripartizione[1:-1] = distribuzione.cdf_vettoriale(bordi[1:-1])
    massa = np.diff(ripartizione)
    massa[massa < 0] = 0.0
    totale = massa.sum()
    return massa / totale if totale > 0 else massa


def _tratta(itinerario: Itinerario, tappa: Tappa, salita: Salita, alla_discesa: bool,
            ritardo_a_monte: int | None = None) -> Tratta:
    return Tratta(
        citta=itinerario.citta,
        route_id=salita.route_id,
        trip_id=salita.trip_id,
        stop_id=tappa.fermata_discesa if alla_discesa else tappa.fermata_salita,
        stop_sequence=tappa.sequenza_discesa if alla_discesa else tappa.sequenza_salita,
        orario_programmato=salita.arrivo_programmato if alla_discesa else salita.partenza_programmata,
        ritardo_a_monte=ritardo_a_monte,
    )


# =============================================================================
# Metodo 1: convoluzione numerica
# =============================================================================


def probabilita_convoluzione(
    itinerario: Itinerario,
    modello: ModelloRitardo,
    scadenza: int,
    recuperi_massimi: int = 2,
    passo: int = PASSO_SECONDI,
) -> EsitoProbabilita:
    """P(arrivo <= scadenza) propagando le distribuzioni su una griglia temporale.

    A ogni tappa si calcola, per ciascuna corsa candidata, la probabilita' che
    sia **la prima** che si riesce a prendere: e' il prodotto delle probabilita'
    di aver mancato tutte le precedenti per la probabilita' di prendere questa.
    Poiche' i ritardi di corse diverse sono indipendenti, quel prodotto si
    fattorizza a parita' di istante in cui si e' pronti, ed e' per questo che la
    propagazione avviene su una griglia di istanti invece che in forma chiusa.

    Il condizionamento fra il ritardo alla salita e quello alla discesa della
    stessa corsa e' esplicito: per ogni bin del ritardo alla salita si interroga
    il modello con quel valore in ``ritardo_a_monte``. E' il punto in cui il
    calcolo smette di trattare come indipendenti eventi che non lo sono.
    """
    inizio = perf_counter()
    passi = ORIZZONTE_SECONDI // passo + 1
    istanti = itinerario.partenza_richiesta + np.arange(passi, dtype=np.int64) * passo

    # Massa concentrata sull'istante di partenza richiesto.
    pmf = np.zeros(passi)
    pmf[0] = 1.0
    perso = 0.0
    tetto_raggiunto = 0.0

    griglia_ritardi = _griglia_ritardi()

    for tappa in itinerario.tappe:
        pronto = _sposta(pmf, tappa.tempo_minimo_trasbordo, passo)
        candidate = tappa.alternative[: 1 + recuperi_massimi]

        # Probabilita' cumulata di aver gia' mancato tutte le corse precedenti,
        # in funzione dell'istante in cui si e' pronti.
        mancate = np.ones(passi)
        nuova = np.zeros(passi)

        for salita in candidate:
            distribuzione_salita = modello.distribuzione(_tratta(itinerario, tappa, salita, False))
            massa_ritardo = _pmf_da_distribuzione(distribuzione_salita, griglia_ritardi)

            # g[t]: si e' pronti a t e si sono mancate tutte le precedenti.
            g = pronto * mancate
            cumulata = np.concatenate([[0.0], np.cumsum(g)])

            for indice, ritardo in enumerate(griglia_ritardi):
                peso_ritardo = massa_ritardo[indice]
                if peso_ritardo <= 0.0:
                    continue
                partenza_reale = salita.partenza_programmata + ritardo
                # Si prende la corsa se si e' pronti non dopo la sua partenza.
                quanti = int(np.searchsorted(istanti, partenza_reale, side="right"))
                peso = peso_ritardo * float(cumulata[min(quanti, passi)])
                if peso <= 0.0:
                    continue
                distribuzione_arrivo = modello.distribuzione(
                    _tratta(itinerario, tappa, salita, True, ritardo_a_monte=int(ritardo))
                )
                massa_arrivo = _pmf_da_distribuzione(distribuzione_arrivo, griglia_ritardi)
                arrivi = salita.arrivo_programmato + griglia_ritardi
                posizioni = np.searchsorted(istanti, arrivi, side="left")
                validi = posizioni < passi
                np.add.at(nuova, posizioni[validi], peso * massa_arrivo[validi])
                perso += peso * float(massa_arrivo[~validi].sum())

            # Aggiorna la probabilita' di aver mancato anche questa corsa.
            #
            # La ripartizione va calcolata sulla STESSA massa discretizzata usata
            # sopra per la probabilita' di prenderla, non sulla ripartizione
            # continua della distribuzione: le due non coincidono esattamente, e
            # usarne una per "prendo" e l'altra per "perdo" non conserva la
            # massa. Il difetto si manifestava come probabilita' superiori a 1.
            ripartizione = _ripartizione_discreta(
                massa_ritardo, griglia_ritardi,
                istanti.astype(float) - salita.partenza_programmata,
            )
            # Si manca la corsa se e' partita PRIMA di essere pronti.
            mancate = mancate * ripartizione

        # La massa rimasta senza corsa presa ha esaurito i recuperi.
        residuo = float((pronto * mancate).sum())
        tetto_raggiunto += residuo
        perso += residuo
        pmf = nuova

    # La massa totale deve valere uno: cio' che arriva piu' cio' che si perde.
    # Una probabilita' superiore a uno non solleva eccezioni da nessuna parte e
    # si nota solo guardando i numeri, quindi il controllo va fatto qui.
    totale = float(pmf.sum()) + perso
    if not 0.999 <= totale <= 1.001:
        raise ErrorePianificatore(
            f"la massa di probabilita' vale {totale:.6f} invece di 1: "
            "la propagazione lungo la catena non conserva la probabilita'."
        )

    entro = float(pmf[istanti <= scadenza].sum())
    return EsitoProbabilita(
        probabilita=entro,
        metodo=f"convoluzione({passo}s)",
        secondi=perf_counter() - inizio,
        quota_fallimenti=perso,
        quota_tetto_raggiunto=tetto_raggiunto,
    )


def _ripartizione_discreta(
    massa: np.ndarray, griglia: np.ndarray, valori: np.ndarray
) -> np.ndarray:
    """P(ritardo < valore) secondo la massa discretizzata, non la forma continua.

    Serve a garantire che, per ogni corsa candidata, la probabilita' di prenderla
    e quella di mancarla sommino esattamente a uno. Mescolare la massa
    discretizzata con la ripartizione continua rompe quella somma di una
    quantita' che dipende dalla griglia, e l'errore si accumula lungo la catena.
    """
    cumulata = np.concatenate([[0.0], np.cumsum(massa)])
    posizioni = np.searchsorted(griglia, np.asarray(valori, dtype=float), side="left")
    return cumulata[np.clip(posizioni, 0, massa.size)]


def _sposta(pmf: np.ndarray, secondi: int, passo: int) -> np.ndarray:
    """Trasla una distribuzione discreta in avanti nel tempo."""
    salti = int(round(secondi / passo))
    if salti <= 0:
        return pmf.copy()
    spostata = np.zeros_like(pmf)
    if salti < pmf.size:
        spostata[salti:] = pmf[: pmf.size - salti]
    return spostata


# =============================================================================
# Metodo 2: campionamento Monte Carlo
# =============================================================================


def probabilita_montecarlo(
    itinerario: Itinerario,
    modello: ModelloRitardo,
    scadenza: int,
    campioni: int = 20_000,
    recuperi_massimi: int = 2,
    generatore: np.random.Generator | None = None,
) -> EsitoProbabilita:
    """P(arrivo <= scadenza) simulando la catena.

    Il condizionamento fra salita e discesa e' discretizzato sulla stessa griglia
    di ritardi usata dalla convoluzione: i campioni vengono raggruppati per bin
    del ritardo alla salita e per ogni gruppo si interroga il modello una volta
    sola. Senza questo raggruppamento servirebbe una interrogazione per campione,
    e centomila campioni costerebbero minuti invece di frazioni di secondo.
    """
    inizio = perf_counter()
    generatore = np.random.default_rng(20260826) if generatore is None else generatore

    pronto = np.full(campioni, float(itinerario.partenza_richiesta))
    vivo = np.ones(campioni, dtype=bool)
    tetto = np.zeros(campioni, dtype=bool)

    for tappa in itinerario.tappe:
        pronto = pronto + tappa.tempo_minimo_trasbordo
        candidate = tappa.alternative[: 1 + recuperi_massimi]
        preso = np.zeros(campioni, dtype=bool)
        ritardo_salita = np.zeros(campioni)
        indice_salita = np.full(campioni, -1, dtype=np.int64)

        for posizione, salita in enumerate(candidate):
            distribuzione = modello.distribuzione(_tratta(itinerario, tappa, salita, False))
            estratti = distribuzione.campiona(campioni, generatore)
            partenza_reale = salita.partenza_programmata + estratti
            prende = vivo & ~preso & (partenza_reale >= pronto)
            ritardo_salita[prende] = estratti[prende]
            indice_salita[prende] = posizione
            preso |= prende

        tetto |= vivo & ~preso
        vivo &= preso

        arrivo = np.full(campioni, float(INFINITO))
        # Raggruppamento per bin del ritardo alla salita: una interrogazione del
        # modello per bin invece che per campione.
        binato = np.clip(
            np.round(ritardo_salita / PASSO_RITARDO) * PASSO_RITARDO, RITARDO_MINIMO, RITARDO_MASSIMO
        )
        for posizione, salita in enumerate(candidate):
            su_questa = vivo & (indice_salita == posizione)
            if not su_questa.any():
                continue
            for valore in np.unique(binato[su_questa]):
                gruppo = su_questa & (binato == valore)
                quanti = int(gruppo.sum())
                distribuzione = modello.distribuzione(
                    _tratta(itinerario, tappa, salita, True, ritardo_a_monte=int(valore))
                )
                arrivo[gruppo] = salita.arrivo_programmato + distribuzione.campiona(
                    quanti, generatore
                )
        pronto = arrivo

    entro = float((vivo & (pronto <= scadenza)).sum()) / campioni
    return EsitoProbabilita(
        probabilita=entro,
        metodo=f"montecarlo({campioni})",
        secondi=perf_counter() - inizio,
        quota_fallimenti=float((~vivo).sum()) / campioni,
        quota_tetto_raggiunto=float(tetto.sum()) / campioni,
        ripetizioni=campioni,
    )


# =============================================================================
# Dal cammino della Fase 2 a un itinerario valutabile
# =============================================================================


def itinerario_da_cammino(
    grafo,
    cammino,
    partenza_richiesta: int,
    recuperi: int = 2,
) -> Itinerario | None:
    """Traduce un cammino del grafo tempo-espanso in un itinerario valutabile.

    Il cammino alterna stati a terra e a bordo; una tappa e' una successione
    massimale di stati a bordo della stessa corsa. Per ciascuna si cercano poi le
    corse successive della **stessa linea** dalla stessa fermata: sono le
    alternative con cui rappresentare una coincidenza persa come un ritardo
    anziche' come un fallimento.

    Restituisce ``None`` se il cammino non contiene alcun tratto a bordo, il che
    accade quando origine e destinazione sono collegate dal solo cammino a piedi.
    """
    from src.graph.time_expanded import ABordo, ATerra

    eventi_per_tappa: list[list[int]] = []
    terra_prima: list[ATerra] = []
    ultima_terra: ATerra | None = None

    for stato in cammino:
        if isinstance(stato, ATerra):
            ultima_terra = stato
            continue
        corsa = int(grafo.evento_corsa[stato.evento])
        if eventi_per_tappa and int(grafo.evento_corsa[eventi_per_tappa[-1][-1]]) == corsa:
            eventi_per_tappa[-1].append(stato.evento)
        else:
            eventi_per_tappa.append([stato.evento])
            terra_prima.append(ultima_terra)

    if not eventi_per_tappa:
        return None

    tappe: list[Tappa] = []
    arrivo_precedente: int | None = None

    for eventi, terra in zip(eventi_per_tappa, terra_prima):
        primo, ultimo = eventi[0], eventi[-1]
        # Il passaggio di salita e' quello che precede il primo evento della
        # tappa nella stessa corsa: gli eventi di una corsa sono contigui nei
        # vettori del grafo, ordinati per posizione lungo il percorso.
        salita_evento = primo - 1
        if salita_evento < 0 or int(grafo.evento_corsa[salita_evento]) != int(
            grafo.evento_corsa[primo]
        ):
            return None

        fermata_salita = int(grafo.evento_fermata[salita_evento])
        fermata_discesa = int(grafo.evento_fermata[ultimo])
        linea = grafo.linea_di_corsa[int(grafo.evento_corsa[primo])]

        pianificata = Salita(
            trip_id=grafo.corse[int(grafo.evento_corsa[primo])],
            route_id=linea,
            partenza_programmata=int(grafo.evento_partenza[salita_evento]),
            arrivo_programmato=int(grafo.evento_arrivo[ultimo]),
        )
        alternative = [pianificata] + _recuperi(
            grafo, fermata_salita, fermata_discesa, linea, pianificata.partenza_programmata, recuperi
        )

        if arrivo_precedente is None:
            minimo = max(0, (terra.istante if terra else partenza_richiesta) - partenza_richiesta)
        else:
            minimo = max(0, (terra.istante if terra else arrivo_precedente) - arrivo_precedente)

        tappe.append(
            Tappa(
                fermata_salita=grafo.fermate[fermata_salita],
                sequenza_salita=int(grafo.evento_sequenza[salita_evento]),
                fermata_discesa=grafo.fermate[fermata_discesa],
                sequenza_discesa=int(grafo.evento_sequenza[ultimo]),
                tempo_minimo_trasbordo=int(minimo),
                alternative=tuple(alternative),
            )
        )
        arrivo_precedente = pianificata.arrivo_programmato

    return Itinerario(citta=grafo.citta, partenza_richiesta=partenza_richiesta, tappe=tuple(tappe))


def _recuperi(
    grafo, fermata_salita: int, fermata_discesa: int, linea: str, dopo: int, quanti: int
) -> list[Salita]:
    """Corse successive della stessa linea, dalla stessa fermata alla stessa fermata."""
    if quanti <= 0:
        return []
    candidati = grafo.partenze_per_fermata.get(fermata_salita)
    if candidati is None:
        return []

    trovati: list[Salita] = []
    for evento in candidati:
        evento = int(evento)
        if int(grafo.evento_partenza[evento]) <= dopo:
            continue
        corsa = int(grafo.evento_corsa[evento])
        if grafo.linea_di_corsa[corsa] != linea:
            continue
        # Si segue la corsa finche' non tocca la fermata di discesa cercata.
        corrente = evento
        arrivo = None
        for _ in range(200):
            seguente = int(grafo.evento_seguente[corrente])
            if seguente < 0:
                break
            if int(grafo.evento_fermata[seguente]) == fermata_discesa:
                arrivo = int(grafo.evento_arrivo[seguente])
                break
            corrente = seguente
        if arrivo is None:
            continue
        trovati.append(
            Salita(
                trip_id=grafo.corse[corsa],
                route_id=linea,
                partenza_programmata=int(grafo.evento_partenza[evento]),
                arrivo_programmato=arrivo,
            )
        )
        if len(trovati) >= quanti:
            break
    return trovati
