"""Grafo tempo-espanso di una rete di trasporto pubblico.

Un grafo tempo-espanso rappresenta non le fermate ma gli **eventi**: ogni
passaggio di una corsa a una fermata, con il suo orario. Muoversi nel grafo
significa muoversi nel tempo oltre che nello spazio, ed e' cio' che permette di
rispondere a "qual e' il primo momento in cui posso essere in B partendo da A alle
otto" invece che a "qual e' il percorso piu' corto fra A e B".

Due scelte determinano tutto il resto.

**La finestra temporale.** Il grafo non copre la giornata ma un intervallo
``[partenza, partenza + orizzonte]``. Roma ha 5,6 milioni di passaggi al giorno:
il grafo completo non e' un oggetto che si costruisce per rispondere a una query.
La finestra e' anche cio' che una query usa davvero, perche' nessuno accetta di
aspettare quattro ore alla fermata. Il prezzo va dichiarato: la ricerca trova
l'ottimo **dentro la finestra**, e un itinerario che richiedesse di attendere
oltre l'orizzonte non verrebbe trovato affatto.

**Lo stato e' (fermata, istante, cambi), con una precisazione necessaria.** La
terna da sola non basta a contare correttamente i cambi: stando fermi a una
fermata, "restare a bordo" e "salire di nuovo" sono indistinguibili se non si sa
su quale corsa ci si trovi. Un viaggiatore che attraversa dieci fermate a bordo
della stessa corsa risulterebbe con dieci cambi. Lo stato si sdoppia percio' in
due forme, che condividono la terna come parte osservabile:

* :class:`ATerra` - si e' a una fermata, a un certo istante, avendo fatto un certo
  numero di cambi. Da qui si puo' salire su una corsa, trasbordare o camminare.
* :class:`ABordo` - si e' su una corsa, appena arrivati a un suo passaggio. Da qui
  si puo' proseguire senza cambiare, oppure scendere.

L'identita' della corsa e' l'unica informazione aggiuntiva rispetto alla terna, ed
e' quella che rende il conteggio dei cambi corretto per costruzione invece che
per convenzione.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Iterator

import numpy as np
import pandas as pd

from src.gtfs.calendar import corse_attive, istante_di_servizio
from src.gtfs.loader import ArchivioGTFS, fermate_fisiche

log = logging.getLogger("grafo")

SENZA_SEGUITO = -1


class ErroreGrafo(Exception):
    """Il grafo non e' costruibile, o lo sarebbe su dati incoerenti."""


# =============================================================================
# Stati
# =============================================================================


@dataclass(frozen=True, slots=True)
class ATerra:
    """A una fermata, a un istante, dopo un certo numero di cambi."""

    fermata: int
    istante: int
    cambi: int


@dataclass(frozen=True, slots=True)
class ABordo:
    """A bordo di una corsa, appena arrivati al passaggio ``evento``."""

    evento: int
    cambi: int


Stato = ATerra | ABordo


# =============================================================================
# Il grafo
# =============================================================================


@dataclass
class Grafo:
    """Eventi e archi di una finestra temporale.

    Gli eventi stanno in vettori paralleli invece che in oggetti Python: un
    milione di piccoli oggetti costerebbe centinaia di MB e renderebbe il grafo
    inutilizzabile proprio sulla citta' piu' interessante. I vettori ``numpy``
    tengono lo stesso contenuto in pochi MB e si indicizzano altrettanto bene.
    """

    citta: str
    giorno: date
    inizio: int
    fine: int

    # Vettori paralleli, uno per evento.
    evento_fermata: np.ndarray
    evento_arrivo: np.ndarray
    evento_partenza: np.ndarray
    evento_corsa: np.ndarray
    evento_sequenza: np.ndarray
    evento_seguente: np.ndarray
    """Indice del passaggio successivo della stessa corsa, o -1."""

    # Per ogni fermata, gli eventi che vi partono, ordinati per orario.
    partenze_per_fermata: dict[int, np.ndarray]
    partenze_orari: dict[int, np.ndarray]

    # Trasbordi: fermata -> lista di (fermata di arrivo, tempo minimo, a piedi).
    trasbordi: dict[int, list[tuple[int, int, bool]]]

    # Corrispondenza fra indici e identificativi GTFS.
    fermate: tuple[str, ...]
    indice_fermata: dict[str, int]
    coordinate: np.ndarray
    """Matrice (n_fermate, 2) con le coordinate piane in metri."""

    corse: tuple[str, ...]
    linea_di_corsa: tuple[str, ...]

    @property
    def n_eventi(self) -> int:
        return int(self.evento_fermata.size)

    @property
    def n_fermate(self) -> int:
        return len(self.fermate)

    def n_archi(self) -> int:
        """Numero di archi del grafo tempo-espanso.

        Si contano tutti e quattro i tipi: permanenza a bordo, discesa, salita e
        trasbordo a terra. La salita e' la categoria piu' numerosa, perche' da
        ogni fermata si puo' salire su ogni corsa che vi passi dopo.
        """
        a_bordo = int((self.evento_seguente != SENZA_SEGUITO).sum())
        discese = self.n_eventi
        salite = sum(int(v.size) for v in self.partenze_per_fermata.values())
        trasbordi = sum(len(v) for v in self.trasbordi.values())
        return a_bordo + discese + salite + trasbordi

    def memoria_mb(self) -> float:
        """Memoria occupata dalle strutture del grafo, in MB."""
        vettori = sum(
            v.nbytes
            for v in (
                self.evento_fermata,
                self.evento_arrivo,
                self.evento_partenza,
                self.evento_corsa,
                self.evento_sequenza,
                self.evento_seguente,
                self.coordinate,
            )
        )
        indici = sum(v.nbytes for v in self.partenze_per_fermata.values())
        indici += sum(v.nbytes for v in self.partenze_orari.values())
        # Le liste di trasbordo sono strutture Python: si stima il loro costo
        # invece di ignorarlo, perche' su Roma sono decine di migliaia di voci.
        trasbordi = sum(len(v) for v in self.trasbordi.values()) * 72
        return (vettori + indici + trasbordi) / 1_048_576

    # -------------------------------------------------------------------------
    # Successori
    # -------------------------------------------------------------------------

    def successori(self, stato: Stato) -> Iterator[tuple[Stato, int]]:
        """Stati raggiungibili da uno stato, con l'istante in cui vi si arriva.

        L'istante restituito e' il costo nel senso della ricerca: si minimizza
        l'orario di arrivo, non una durata, perche' partire piu' tardi non e'
        peggio se si arriva prima.
        """
        if isinstance(stato, ABordo):
            yield from self._successori_a_bordo(stato)
        else:
            yield from self._successori_a_terra(stato)

    def _successori_a_bordo(self, stato: ABordo) -> Iterator[tuple[Stato, int]]:
        evento = stato.evento
        # Restare a bordo: nessun cambio, si arriva al passaggio successivo.
        seguente = int(self.evento_seguente[evento])
        if seguente != SENZA_SEGUITO:
            yield ABordo(seguente, stato.cambi), int(self.evento_arrivo[seguente])
        # Scendere: stessa fermata, stesso istante, nessun cambio. Il cambio si
        # conta alla salita, non alla discesa, altrimenti scendere a destinazione
        # costerebbe un cambio che il viaggiatore non percepisce.
        yield (
            ATerra(int(self.evento_fermata[evento]), int(self.evento_arrivo[evento]), stato.cambi),
            int(self.evento_arrivo[evento]),
        )

    def _successori_a_terra(self, stato: ATerra) -> Iterator[tuple[Stato, int]]:
        # Salire su una corsa che parte da qui, non prima di adesso.
        orari = self.partenze_orari.get(stato.fermata)
        if orari is not None and orari.size:
            primo = int(np.searchsorted(orari, stato.istante, side="left"))
            eventi = self.partenze_per_fermata[stato.fermata]
            for posizione in range(primo, eventi.size):
                evento = int(eventi[posizione])
                seguente = int(self.evento_seguente[evento])
                if seguente == SENZA_SEGUITO:
                    # Capolinea: salirci non porta da nessuna parte.
                    continue
                yield ABordo(seguente, stato.cambi + 1), int(self.evento_arrivo[seguente])

        # Trasbordare o camminare verso un'altra fermata.
        for destinazione, tempo, _a_piedi in self.trasbordi.get(stato.fermata, ()):
            arrivo = stato.istante + tempo
            if arrivo <= self.fine:
                yield ATerra(destinazione, arrivo, stato.cambi), arrivo

    # -------------------------------------------------------------------------
    # Interrogazioni di comodo
    # -------------------------------------------------------------------------

    def fermata_di(self, stato: Stato) -> int:
        return stato.fermata if isinstance(stato, ATerra) else int(self.evento_fermata[stato.evento])

    def istante_di(self, stato: Stato) -> int:
        return stato.istante if isinstance(stato, ATerra) else int(self.evento_arrivo[stato.evento])


# =============================================================================
# Costruzione
# =============================================================================


def _trasbordi_da_parquet(
    percorso: Path, indice_fermata: dict[str, int]
) -> dict[int, list[tuple[int, int, bool]]]:
    """Legge transfers_<citta>.parquet, prodotto dalla base di conoscenza."""
    if not percorso.is_file():
        raise ErroreGrafo(
            f"Manca {percorso}. Va prodotto prima con "
            "'python scripts/materializza_transfers.py'."
        )
    tabella = pd.read_parquet(percorso)
    trasbordi: dict[int, list[tuple[int, int, bool]]] = {}
    for riga in tabella.itertuples(index=False):
        partenza = indice_fermata.get(str(riga.from_stop_id))
        arrivo = indice_fermata.get(str(riga.to_stop_id))
        if partenza is None or arrivo is None:
            continue
        trasbordi.setdefault(partenza, []).append(
            (arrivo, int(riga.min_transfer_time), bool(riga.a_piedi))
        )
    return trasbordi


def costruisci(
    archivio: ArchivioGTFS,
    citta: str,
    giorno: date,
    inizio: int,
    orizzonte_minuti: int = 120,
    percorso_trasbordi: Path | None = None,
) -> Grafo:
    """Costruisce il grafo della finestra ``[inizio, inizio + orizzonte]``.

    ``inizio`` e' un istante POSIX. Si includono tutti i passaggi la cui partenza
    cada nella finestra, piu' il passaggio successivo di ogni corsa: senza
    quest'ultimo un viaggio che parte dentro la finestra non avrebbe dove
    arrivare.
    """
    if archivio.stop_times is None:
        raise ErroreGrafo("l'archivio va caricato con con_stop_times=True")
    fine = inizio + orizzonte_minuti * 60

    fisiche = fermate_fisiche(archivio.stops)
    from src.kb.engine import proietta_in_metri  # importato qui per non forzare clingo

    proiettate = proietta_in_metri(fisiche)
    fermate = tuple(str(s) for s in proiettate["stop_id"])
    indice_fermata = {nome: i for i, nome in enumerate(fermate)}
    coordinate = np.column_stack(
        [proiettate["x_m"].to_numpy(dtype="int64"), proiettate["y_m"].to_numpy(dtype="int64")]
    )

    attive = corse_attive(archivio, giorno)
    if not attive:
        raise ErroreGrafo(f"nessuna corsa attiva il {giorno} per {citta}")

    passaggi = archivio.stop_times
    passaggi = passaggi[passaggi["trip_id"].astype("string").isin(attive)]
    passaggi = passaggi.dropna(subset=["departure_time", "arrival_time"])

    # Gli orari del GTFS sono secondi dall'inizio del giorno di servizio: vanno
    # portati a istanti assoluti prima di poterli confrontare con la finestra.
    mezzanotte = int(istante_di_servizio(giorno, 0, archivio.fuso_orario).timestamp())
    arrivo_assoluto = mezzanotte + passaggi["arrival_time"].to_numpy(dtype="int64")
    partenza_assoluta = mezzanotte + passaggi["departure_time"].to_numpy(dtype="int64")

    # Si tiene un margine a monte perche' una corsa entrata in finestra puo'
    # essere partita poco prima, e il suo passaggio precedente serve a saperlo.
    dentro = (partenza_assoluta >= inizio - 3600) & (arrivo_assoluto <= fine + 3600)
    passaggi = passaggi.loc[dentro].copy()
    passaggi["arrivo"] = arrivo_assoluto[dentro]
    passaggi["partenza"] = partenza_assoluta[dentro]
    passaggi = passaggi.sort_values(["trip_id", "stop_sequence"], kind="stable").reset_index(drop=True)

    conosciute = passaggi["stop_id"].astype("string").map(indice_fermata)
    passaggi = passaggi.loc[conosciute.notna()].copy()
    passaggi["fermata"] = conosciute[conosciute.notna()].to_numpy(dtype="int32")

    corse = tuple(passaggi["trip_id"].astype("string").unique())
    indice_corsa = {nome: i for i, nome in enumerate(corse)}
    passaggi["corsa"] = passaggi["trip_id"].astype("string").map(indice_corsa).to_numpy(dtype="int32")

    evento_fermata = passaggi["fermata"].to_numpy(dtype="int32")
    evento_arrivo = passaggi["arrivo"].to_numpy(dtype="int64")
    evento_partenza = passaggi["partenza"].to_numpy(dtype="int64")
    evento_corsa = passaggi["corsa"].to_numpy(dtype="int32")
    evento_sequenza = passaggi["stop_sequence"].to_numpy(dtype="int32")

    # Il passaggio successivo della stessa corsa e' quello immediatamente dopo
    # nell'ordinamento, purche' appartenga alla stessa corsa.
    evento_seguente = np.full(evento_corsa.size, SENZA_SEGUITO, dtype="int64")
    if evento_corsa.size > 1:
        stessa = evento_corsa[:-1] == evento_corsa[1:]
        indici = np.arange(evento_corsa.size - 1)
        evento_seguente[indici[stessa]] = indici[stessa] + 1

    # Indice delle partenze per fermata, dentro la finestra vera.
    in_finestra = (evento_partenza >= inizio) & (evento_partenza <= fine)
    partenze_per_fermata: dict[int, np.ndarray] = {}
    partenze_orari: dict[int, np.ndarray] = {}
    candidati = np.flatnonzero(in_finestra)
    ordinati = candidati[np.argsort(evento_partenza[candidati], kind="stable")]
    for fermata in np.unique(evento_fermata[ordinati]):
        selezione = ordinati[evento_fermata[ordinati] == fermata]
        partenze_per_fermata[int(fermata)] = selezione.astype("int64")
        partenze_orari[int(fermata)] = evento_partenza[selezione]

    if percorso_trasbordi is None:
        percorso_trasbordi = (
            Path(__file__).resolve().parents[2] / "data" / "processed" / f"transfers_{citta}.parquet"
        )
    trasbordi = _trasbordi_da_parquet(percorso_trasbordi, indice_fermata)

    linea_di_corsa = tuple(
        str(r)
        for r in archivio.trips.set_index("trip_id")["route_id"].reindex(list(corse)).fillna("")
    )

    return Grafo(
        citta=citta,
        giorno=giorno,
        inizio=inizio,
        fine=fine,
        evento_fermata=evento_fermata,
        evento_arrivo=evento_arrivo,
        evento_partenza=evento_partenza,
        evento_corsa=evento_corsa,
        evento_sequenza=evento_sequenza,
        evento_seguente=evento_seguente,
        partenze_per_fermata=partenze_per_fermata,
        partenze_orari=partenze_orari,
        trasbordi=trasbordi,
        fermate=fermate,
        indice_fermata=indice_fermata,
        coordinate=coordinate,
        corse=corse,
        linea_di_corsa=linea_di_corsa,
    )


def velocita_massima(archivio: ArchivioGTFS, percentile: float | None = None) -> dict[str, float]:
    """Velocita' fra fermate consecutive, misurata sull'orario programmato.

    Serve all'euristica geografica della ricerca, che ha bisogno di un limite
    superiore alla velocita' con cui ci si puo' muovere nella rete.

    Si misura sull'orario **programmato** e non sul real-time di proposito: il
    primo e' un dato anagrafico pulito, il secondo puo' contenere salti di
    posizione che produrrebbero velocita' impossibili.

    Restituisce l'intera distribuzione e non il solo massimo, perche' guardare la
    coda e' l'unico modo per accorgersi delle coordinate sbagliate: una fermata
    con latitudine e longitudine invertite genera un arco di centinaia di
    chilometri percorso in due minuti, e il massimo da solo non lo direbbe.
    """
    if archivio.stop_times is None:
        raise ErroreGrafo("serve l'archivio con con_stop_times=True")

    fisiche = fermate_fisiche(archivio.stops)
    from src.kb.engine import proietta_in_metri

    proiettate = proietta_in_metri(fisiche).set_index("stop_id")
    coordinate = proiettate[["x_m", "y_m"]]

    passaggi = archivio.stop_times.dropna(subset=["arrival_time", "departure_time"])
    passaggi = passaggi.sort_values(["trip_id", "stop_sequence"], kind="stable")
    unito = passaggi.join(coordinate, on="stop_id", how="inner")

    stessa_corsa = unito["trip_id"].to_numpy()[:-1] == unito["trip_id"].to_numpy()[1:]
    dx = unito["x_m"].to_numpy()[1:] - unito["x_m"].to_numpy()[:-1]
    dy = unito["y_m"].to_numpy()[1:] - unito["y_m"].to_numpy()[:-1]
    distanza = np.sqrt(dx.astype(float) ** 2 + dy.astype(float) ** 2)
    durata = (
        unito["arrival_time"].to_numpy(dtype="float64")[1:]
        - unito["departure_time"].to_numpy(dtype="float64")[:-1]
    )

    valide = stessa_corsa & (durata > 0) & (distanza > 0)
    velocita = distanza[valide] / durata[valide]
    if velocita.size == 0:
        raise ErroreGrafo("nessun arco utilizzabile per misurare la velocita'")

    # I nomi sono espliciti e non generati: int(0.999 * 100) vale 99, e una
    # generazione automatica farebbe sovrascrivere il p99 dal p99,9 senza che
    # nulla lo segnali.
    return {
        "archi": float(velocita.size),
        "massimo_m_s": float(velocita.max()),
        "massimo_km_h": float(velocita.max() * 3.6),
        "p50": float(np.quantile(velocita, 0.50)),
        "p90": float(np.quantile(velocita, 0.90)),
        "p99": float(np.quantile(velocita, 0.99)),
        "p999": float(np.quantile(velocita, 0.999)),
        "p99_km_h": float(np.quantile(velocita, 0.99) * 3.6),
        "p999_km_h": float(np.quantile(velocita, 0.999) * 3.6),
        "oltre_150_km_h": float((velocita * 3.6 > 150).sum()),
    }
