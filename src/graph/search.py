"""Ricerca di itinerari sul grafo tempo-espanso.

Contiene due ricerche. La prima e' mono-criterio e cerca il primo orario di
arrivo possibile; la seconda e' multi-criterio e restituisce la frontiera di
Pareto su orario di arrivo, numero di cambi e minuti a piedi.

A* e Dijkstra condividono **lo stesso codice**: Dijkstra e' A* con euristica
identicamente nulla. Non e' un dettaglio implementativo ma una condizione del
confronto sperimentale: due implementazioni separate misurerebbero anche le
differenze fra le due implementazioni, e non solo l'effetto dell'euristica.
"""

from __future__ import annotations

import heapq
import logging
from dataclasses import dataclass, field
from time import perf_counter
from typing import Callable

import numpy as np

from src.graph.time_expanded import ABordo, ATerra, Grafo, Stato

log = logging.getLogger("ricerca")


class ErroreRicerca(Exception):
    """La ricerca non e' impostabile: fermate sconosciute, finestra incoerente."""


# =============================================================================
# Euristica
# =============================================================================


def euristica_geografica(
    grafo: Grafo, destinazione: int, velocita_massima_m_s: float
) -> Callable[[Stato], float]:
    """Stima ottimistica del tempo residuo: distanza in linea d'aria diviso la
    velocita' massima della rete.

    **Ammissibilita'.** Sia ``n`` uno stato la cui fermata dista ``d`` metri in
    linea d'aria dalla destinazione, e sia ``V`` la velocita' massima fra due
    fermate consecutive presente nell'orario. Qualunque itinerario che porti da
    ``n`` alla destinazione e' una successione di spostamenti fra fermate; la
    somma delle loro lunghezze non puo' essere inferiore a ``d``, perche' la
    linea d'aria e' il cammino piu' breve fra due punti del piano; e ognuno di
    essi impiega almeno la propria lunghezza divisa ``V``, perche' ``V`` e' per
    costruzione un limite superiore alla velocita' di ogni spostamento. Il tempo
    residuo reale e' percio' almeno ``d / V``, che e' il valore restituito. Le
    attese alle fermate e i tempi minimi di trasbordo possono solo aumentarlo,
    quindi non intaccano il limite. L'euristica non sovrastima mai il costo
    residuo, ed e' quindi ammissibile: A* restituisce l'ottimo.

    **Consistenza.** L'euristica e' anche consistente, perche' e' della forma
    ``d(x)/V`` con ``d`` distanza euclidea, che soddisfa la disuguaglianza
    triangolare: per ogni arco da ``x`` a ``y`` di costo ``c``, si ha
    ``h(x) <= c + h(y)``. Con un'euristica consistente, ogni stato viene estratto
    dalla coda con il suo costo definitivo e non serve riaprirlo.

    **Il prezzo di ``V``.** Il limite deve valere per l'orario cosi' com'e',
    difetti compresi. Se la tabella oraria dichiara un percorso di quattrocento
    metri in tre secondi, ``V`` deve tenerne conto, altrimenti l'euristica
    sovrastimerebbe il costo residuo su quel tratto e A* potrebbe scartare
    l'ottimo. E' misurato che questo accade in entrambe le citta' del progetto, e
    la conseguenza e' un'euristica molto piu' debole di quanto la fisica
    consentirebbe.
    """
    coordinate = grafo.coordinate
    obiettivo = coordinate[destinazione]
    velocita = max(float(velocita_massima_m_s), 1e-6)

    def h(stato: Stato) -> float:
        fermata = grafo.fermata_di(stato)
        scarto = coordinate[fermata] - obiettivo
        return float(np.hypot(scarto[0], scarto[1]) / velocita)

    return h


def euristica_nulla(_grafo: Grafo, _destinazione: int, _velocita: float) -> Callable[[Stato], float]:
    """L'euristica di Dijkstra. Ammissibile in modo banale, e del tutto inutile."""
    return lambda _stato: 0.0


# =============================================================================
# Ricerca mono-criterio
# =============================================================================


@dataclass
class EsitoRicerca:
    """Risultato di una singola interrogazione, con le sue misure."""

    trovato: bool
    orario_arrivo: int | None
    cambi: int | None
    stati_espansi: int
    stati_generati: int
    tempo_secondi: float
    cammino: list[Stato] = field(default_factory=list)

    @property
    def durata_minuti(self) -> float | None:
        return None if self.orario_arrivo is None else self.orario_arrivo / 60.0


def _chiave(grafo: Grafo, stato: Stato, con_cambi: bool) -> tuple:
    """Chiave con cui uno stato viene considerato gia' visitato.

    Per uno stato a terra la chiave **non contiene l'istante**, e la ragione e'
    una relazione di dominanza: trovarsi alla stessa fermata con lo stesso numero
    di cambi ma prima e' sempre almeno altrettanto buono, perche' ogni
    proseguimento disponibile a chi arriva tardi lo e' anche a chi arriva presto,
    e attendere non costa nulla. Tenere l'istante nella chiave moltiplicherebbe
    lo spazio degli stati per il numero di orari distinti di arrivo a una
    fermata, che sulla finestra di due ore sono centinaia: e' la differenza fra
    una ricerca che risponde in un decimo di secondo e una che espande milioni di
    stati.

    Per uno stato a bordo la chiave e' il passaggio, che gia' identifica corsa,
    fermata e istante insieme.

    ``con_cambi=False`` proietta via il numero di cambi. Serve unicamente a
    misurare quanto costi tenerlo nello stato: e' un parametro della misura, non
    una seconda implementazione della ricerca.
    """
    if isinstance(stato, ABordo):
        base = ("b", stato.evento)
    else:
        base = ("t", stato.fermata)
    return base + ((stato.cambi,) if con_cambi else ())


def cerca_primo_arrivo(
    grafo: Grafo,
    origine: str,
    destinazione: str,
    partenza: int,
    velocita_massima_m_s: float,
    con_euristica: bool = True,
    cambi_nello_stato: bool = True,
    cambi_massimi: int = 4,
) -> EsitoRicerca:
    """A* sul primo orario di arrivo. Con ``con_euristica=False`` e' Dijkstra.

    Il costo di uno stato e' l'**orario di arrivo**, non la durata: partire piu'
    tardi non e' peggio se si arriva prima, e minimizzare la durata porterebbe a
    preferire un viaggio breve che parte fra due ore a uno un po' piu' lungo che
    parte adesso.
    """
    if origine not in grafo.indice_fermata:
        raise ErroreRicerca(f"fermata di partenza sconosciuta: {origine}")
    if destinazione not in grafo.indice_fermata:
        raise ErroreRicerca(f"fermata di arrivo sconosciuta: {destinazione}")

    partenza_idx = grafo.indice_fermata[origine]
    arrivo_idx = grafo.indice_fermata[destinazione]
    costruisci_h = euristica_geografica if con_euristica else euristica_nulla
    h = costruisci_h(grafo, arrivo_idx, velocita_massima_m_s)

    inizio = perf_counter()
    iniziale = ATerra(partenza_idx, partenza, 0)
    # Il contatore e' un discriminante di parita': senza, a parita' di stima e di
    # costo heapq confronterebbe gli stati fra loro, che non sono ordinabili.
    # Serve anche a rendere deterministico l'ordine di estrazione, e quindi
    # riproducibile il conteggio dei nodi espansi.
    ordine = 0
    coda: list[tuple[float, int, int, Stato]] = [(partenza + h(iniziale), partenza, 0, iniziale)]
    migliore: dict[tuple, int] = {_chiave(grafo, iniziale, cambi_nello_stato): partenza}
    precedente: dict[tuple, Stato] = {}
    espansi = generati = 0

    while coda:
        _stima, costo, _ordine, stato = heapq.heappop(coda)
        chiave = _chiave(grafo, stato, cambi_nello_stato)
        if costo > migliore.get(chiave, costo):
            continue
        espansi += 1

        if grafo.fermata_di(stato) == arrivo_idx and isinstance(stato, ATerra):
            return EsitoRicerca(
                trovato=True,
                orario_arrivo=int(costo),
                cambi=stato.cambi,
                stati_espansi=espansi,
                stati_generati=generati,
                tempo_secondi=perf_counter() - inizio,
                cammino=_ricostruisci(precedente, grafo, stato, cambi_nello_stato),
            )

        for successivo, arrivo in grafo.successori(stato):
            generati += 1
            if arrivo > grafo.fine or successivo.cambi > cambi_massimi:
                continue
            chiave_succ = _chiave(grafo, successivo, cambi_nello_stato)
            if arrivo < migliore.get(chiave_succ, 1 << 62):
                migliore[chiave_succ] = arrivo
                precedente[chiave_succ] = stato
                ordine += 1
                heapq.heappush(coda, (arrivo + h(successivo), arrivo, ordine, successivo))

    return EsitoRicerca(
        trovato=False,
        orario_arrivo=None,
        cambi=None,
        stati_espansi=espansi,
        stati_generati=generati,
        tempo_secondi=perf_counter() - inizio,
    )


def _ricostruisci(
    precedente: dict[tuple, Stato], grafo: Grafo, finale: Stato, con_cambi: bool
) -> list[Stato]:
    cammino = [finale]
    corrente = finale
    for _ in range(10_000):  # limite di sicurezza contro un ciclo imprevisto
        chiave = _chiave(grafo, corrente, con_cambi)
        if chiave not in precedente:
            break
        corrente = precedente[chiave]
        cammino.append(corrente)
    return list(reversed(cammino))


# =============================================================================
# Ricerca multi-criterio
# =============================================================================


@dataclass(frozen=True)
class Etichetta:
    """Un compromesso: arrivare a un certo orario, con tanti cambi e tanto piedi."""

    orario_arrivo: int
    cambi: int
    secondi_a_piedi: int

    def domina(self, altra: "Etichetta") -> bool:
        """Vero se questa e' migliore o uguale su tutto e strettamente su qualcosa.

        E' la definizione di dominanza di Pareto. La disuguaglianza stretta su
        almeno un criterio e' necessaria: senza, due etichette identiche si
        dominerebbero a vicenda e la frontiera si svuoterebbe.
        """
        non_peggiore = (
            self.orario_arrivo <= altra.orario_arrivo
            and self.cambi <= altra.cambi
            and self.secondi_a_piedi <= altra.secondi_a_piedi
        )
        migliore_da_qualche_parte = (
            self.orario_arrivo < altra.orario_arrivo
            or self.cambi < altra.cambi
            or self.secondi_a_piedi < altra.secondi_a_piedi
        )
        return non_peggiore and migliore_da_qualche_parte


def _aggiorna_frontiera(frontiera: list[Etichetta], candidata: Etichetta) -> bool:
    """Inserisce una candidata se non e' dominata, togliendo cio' che essa domina."""
    for presente in frontiera:
        if presente.domina(candidata) or presente == candidata:
            return False
    frontiera[:] = [e for e in frontiera if not candidata.domina(e)]
    frontiera.append(candidata)
    return True


@dataclass
class EsitoPareto:
    frontiera: list[Etichetta]
    stati_espansi: int
    tempo_secondi: float


def cerca_frontiera_pareto(
    grafo: Grafo,
    origine: str,
    destinazione: str,
    partenza: int,
    cambi_massimi: int = 4,
) -> EsitoPareto:
    """Frontiera di Pareto su (orario di arrivo, cambi, secondi a piedi).

    Non esiste un itinerario ottimo unico, perche' i tre criteri non sono
    confrontabili fra loro senza decidere quanto valga un cambio in minuti. La
    ricerca restituisce quindi l'insieme delle soluzioni non dominate, e la
    scelta fra esse resta a chi viaggia.

    L'algoritmo e' a etichette: ogni stato porta l'insieme dei compromessi non
    dominati con cui vi si puo' arrivare, e un'etichetta nuova viene propagata
    solo se nessuna gia' presente la domina.
    """
    if origine not in grafo.indice_fermata or destinazione not in grafo.indice_fermata:
        raise ErroreRicerca("fermata sconosciuta")
    partenza_idx = grafo.indice_fermata[origine]
    arrivo_idx = grafo.indice_fermata[destinazione]

    inizio = perf_counter()
    iniziale = ATerra(partenza_idx, partenza, 0)
    etichette: dict[tuple, list[Etichetta]] = {}
    frontiera_finale: list[Etichetta] = []
    contatore = 0
    coda: list[tuple[int, int, int, int, Stato, Etichetta]] = [
        (partenza, 0, 0, 0, iniziale, Etichetta(partenza, 0, 0))
    ]
    espansi = 0

    while coda:
        _orario, _cambi, _piedi, _ordine, stato, etichetta = heapq.heappop(coda)
        chiave = _chiave(grafo, stato, con_cambi=False)
        if not _aggiorna_frontiera(etichette.setdefault(chiave, []), etichetta):
            continue
        espansi += 1

        if isinstance(stato, ATerra) and stato.fermata == arrivo_idx:
            _aggiorna_frontiera(frontiera_finale, etichetta)
            continue

        # Potatura: una soluzione gia' trovata che domina questo parziale rende
        # inutile proseguire, perche' proseguire puo' solo peggiorare.
        if any(e.domina(etichetta) for e in frontiera_finale):
            continue

        for successivo, arrivo in grafo.successori(stato):
            if arrivo > grafo.fine or successivo.cambi > cambi_massimi:
                continue
            piedi = etichetta.secondi_a_piedi
            if isinstance(stato, ATerra) and isinstance(successivo, ATerra):
                piedi += arrivo - stato.istante
            nuova = Etichetta(int(arrivo), successivo.cambi, piedi)
            contatore += 1
            heapq.heappush(coda, (nuova.orario_arrivo, nuova.cambi, nuova.secondi_a_piedi,
                                  contatore, successivo, nuova))

    return EsitoPareto(
        frontiera=sorted(frontiera_finale, key=lambda e: (e.orario_arrivo, e.cambi)),
        stati_espansi=espansi,
        tempo_secondi=perf_counter() - inizio,
    )
