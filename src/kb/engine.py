"""Esecuzione della base di conoscenza sui fatti derivati dal GTFS.

Il modulo fa tre cose: traduce un archivio GTFS nei fatti attesi da
``rules.lp``, esegue clingo separando il tempo di grounding da quello di
solving, e materializza il risultato in ``data/processed/transfers.parquet``.

Due scelte meritano di essere dichiarate subito.

**Le fermate diventano numeri interi.** Gli identificativi GTFS sono stringhe
arbitrarie (``"0#4744-16"``, ``"79283"``) e usarle come termini ASP rallenta il
grounding senza portare alcun vantaggio: la corrispondenza e' biunivoca e viene
conservata in memoria, quindi il risultato si ritraduce esattamente. E' un
cambio di rappresentazione, non di conoscenza.

**Le coordinate diventano metri.** ``rules.lp`` confronta distanze, e farlo in
gradi richiederebbe di conoscere la latitudine dentro la regola. La proiezione
equirettangolare locale, centrata sul baricentro delle fermate della citta',
converte gradi in metri con un errore trascurabile sulla scala di una citta' (a
250 m di distanza, ben sotto il metro). Anche questo e' un cambio di unita': la
regola che decide *quali* coppie siano trasbordi resta interamente in ASP.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from time import perf_counter
from typing import Any, Iterable, Mapping, Sequence

import clingo
import pandas as pd

from src.gtfs.loader import ArchivioGTFS, fermate_fisiche

PERCORSO_REGOLE = Path(__file__).with_name("rules.lp")

# Metri per grado di latitudine. Costante a meno di variazioni di terzo ordine,
# irrilevanti sulla scala di una citta'.
METRI_PER_GRADO = 111_320.0


class ErroreKB(Exception):
    """La base di conoscenza non ha prodotto un modello utilizzabile."""


# =============================================================================
# Dai dati GTFS ai fatti
# =============================================================================


@dataclass(frozen=True)
class Fatti:
    """I fatti ASP di una istanza, piu' cio' che serve a ritradurne il risultato."""

    testo: str
    fermate: tuple[str, ...]
    indice_di: Mapping[str, int]
    conteggi: Mapping[str, int]
    lato_cella: int

    @property
    def n_fermate(self) -> int:
        return len(self.fermate)

    @property
    def n_fatti(self) -> int:
        return sum(self.conteggi.values())


def proietta_in_metri(stops: pd.DataFrame) -> pd.DataFrame:
    """Aggiunge le coordinate piane in metri interi, centrate sul baricentro.

    Il centro e' il baricentro geometrico delle fermate della citta', calcolato
    dai dati e non scelto a mano: e' riproducibile e non introduce un punto di
    vista arbitrario sulla rete.
    """
    proiettate = stops.copy()
    lat0 = float(proiettate["stop_lat"].mean())
    lon0 = float(proiettate["stop_lon"].mean())
    metri_per_grado_lon = METRI_PER_GRADO * math.cos(math.radians(lat0))
    proiettate["x_m"] = ((proiettate["stop_lon"] - lon0) * metri_per_grado_lon).round().astype("int64")
    proiettate["y_m"] = ((proiettate["stop_lat"] - lat0) * METRI_PER_GRADO).round().astype("int64")
    return proiettate


def fermata_centrale(stops: pd.DataFrame) -> str:
    """La fermata piu' vicina al baricentro geometrico di tutte le fermate.

    E' il centro usato per il campionamento per prossimita' della curva di
    complessita'. Deriva dai dati, quindi e' riproducibile e dichiarabile nel
    documento: non e' "il centro citta'" scelto a occhio.
    """
    proiettate = proietta_in_metri(stops)
    distanza2 = proiettate["x_m"] ** 2 + proiettate["y_m"] ** 2
    return str(proiettate.loc[distanza2.idxmin(), "stop_id"])


def sottoinsieme_per_prossimita(stops: pd.DataFrame, quante: int, centro: str | None = None) -> pd.DataFrame:
    """Le ``quante`` fermate piu' vicine a un centro, per la curva di complessita'.

    Perche' per prossimita' e non a caso: cinquanta fermate estratte a sorte fra
    le ottomila di Roma finirebbero sparse su tutta la citta', a chilometri l'una
    dall'altra, e non genererebbero quasi nessun trasbordo a piedi. La curva
    misurerebbe il costo di un problema che non somiglia a quello vero. Il
    campionamento per prossimita' conserva invece la densita' reale della rete.

    Il prezzo va dichiarato: i risultati valgono per una porzione connessa e
    densa di rete, non per un campione sparso di pari cardinalita'.
    """
    if centro is None:
        centro = fermata_centrale(stops)
    proiettate = proietta_in_metri(stops)
    riga_centro = proiettate[proiettate["stop_id"] == centro]
    if riga_centro.empty:
        raise ErroreKB(f"Fermata centro '{centro}' non presente fra le fermate fornite.")
    x0 = int(riga_centro["x_m"].iloc[0])
    y0 = int(riga_centro["y_m"].iloc[0])
    distanza2 = (proiettate["x_m"] - x0) ** 2 + (proiettate["y_m"] - y0) ** 2
    ordinate = proiettate.assign(_d2=distanza2).sort_values(["_d2", "stop_id"])
    return ordinate.head(quante).drop(columns="_d2").reset_index(drop=True)


def genera_fatti(
    archivio: ArchivioGTFS,
    stops: pd.DataFrame | None = None,
    soglia_piedi: int = 250,
    ascensori_fuori_servizio: Sequence[str] = (),
) -> Fatti:
    """Traduce l'archivio (o un suo sottoinsieme di fermate) nei fatti di rules.lp.

    Il lato della cella dell'indice spaziale e' posto **uguale** alla soglia di
    cammino. E' la condizione che rende l'indice semanticamente neutro: due
    fermate a meno di ``soglia_piedi`` metri non possono finire in celle non
    adiacenti, quindi nessun trasbordo puo' sfuggire al confronto. Un lato
    minore della soglia romperebbe questa garanzia, ed e' il motivo per cui non
    e' un parametro indipendente.
    """
    fermate = fermate_fisiche(archivio.stops) if stops is None else stops
    fermate = proietta_in_metri(fermate) if "x_m" not in fermate.columns else fermate
    lato = int(soglia_piedi)

    elenco = [str(s) for s in fermate["stop_id"]]
    insieme_fermate = set(elenco)

    # Le stazioni non sono fermate ma compaiono nei fatti, perche' l'eredita'
    # dell'accessibilita' le attraversa. Ricevono un indice nello stesso spazio.
    stazioni = {
        str(s)
        for s in fermate["parent_station"]
        if str(s) and str(s) != "nan" and str(s) not in insieme_fermate
    }
    ordinati = elenco + sorted(stazioni)
    indice_di = {identificativo: i for i, identificativo in enumerate(ordinati)}

    righe: list[str] = []
    conteggi: dict[str, int] = {}

    def aggiungi(nome: str, quante: int) -> None:
        conteggi[nome] = conteggi.get(nome, 0) + quante

    for riga in fermate.itertuples(index=False):
        f = indice_di[str(riga.stop_id)]
        righe.append(f"fermata({f}).")
        righe.append(f"coord({f},{int(riga.x_m)},{int(riga.y_m)}).")
        righe.append(f"cella({f},{int(riga.x_m) // lato},{int(riga.y_m) // lato}).")
        padre = str(riga.parent_station)
        if padre and padre != "nan" and padre in indice_di:
            righe.append(f"in_stazione({f},{indice_di[padre]}).")
            aggiungi("in_stazione", 1)
        righe.append(f"accesso_sedia({f},{int(riga.wheelchair_boarding)}).")
    aggiungi("fermata", len(fermate))
    aggiungi("coord", len(fermate))
    aggiungi("cella", len(fermate))
    aggiungi("accesso_sedia", len(fermate))

    # Accessibilita' dichiarata delle stazioni: serve alla regola di eredita'.
    stazioni_note = archivio.stops[archivio.stops["stop_id"].astype("string").isin(stazioni)]
    for riga in stazioni_note.itertuples(index=False):
        righe.append(f"accesso_sedia({indice_di[str(riga.stop_id)]},{int(riga.wheelchair_boarding)}).")
    aggiungi("accesso_sedia_stazione", len(stazioni_note))

    # serve/2: quali linee fermano dove. Richiede stop_times, che e' il file
    # pesante; se non e' stato caricato la relazione resta vuota e la regola di
    # utilita' del trasbordo semplicemente non deriva nulla.
    if archivio.stop_times is not None:
        coppie = _coppie_linea_fermata(archivio, insieme_fermate)
        linee = sorted({r for r, _ in coppie})
        indice_linea = {linea: i for i, linea in enumerate(linee)}
        for linea, fermata in coppie:
            righe.append(f"serve({indice_linea[linea]},{indice_di[fermata]}).")
        aggiungi("serve", len(coppie))

    # transfers.txt, se l'azienda lo pubblica. Nessuna delle due citta' del
    # progetto lo fa: la regola di livello 1 resta senza fatti, ed e' il motivo
    # per cui l'intera relazione di trasbordo va derivata.
    if archivio.transfers is not None and not archivio.transfers.empty:
        quanti = 0
        for riga in archivio.transfers.itertuples(index=False):
            partenza, arrivo = str(riga.from_stop_id), str(riga.to_stop_id)
            if partenza not in indice_di or arrivo not in indice_di:
                continue
            tempo = getattr(riga, "min_transfer_time", "")
            if tempo == "" or pd.isna(tempo):
                continue
            righe.append(f"dichiarato({indice_di[partenza]},{indice_di[arrivo]},{int(tempo)}).")
            quanti += 1
        aggiungi("dichiarato", quanti)

    for identificativo in ascensori_fuori_servizio:
        if str(identificativo) in indice_di:
            righe.append(f"ascensore_fuori_servizio({indice_di[str(identificativo)]}).")
    aggiungi("ascensore_fuori_servizio", len(ascensori_fuori_servizio))

    return Fatti(
        testo="\n".join(righe),
        fermate=tuple(ordinati),
        indice_di=indice_di,
        conteggi=conteggi,
        lato_cella=lato,
    )


def _coppie_linea_fermata(archivio: ArchivioGTFS, fermate: set[str]) -> list[tuple[str, str]]:
    """Coppie distinte (linea, fermata) ricavate da stop_times e trips."""
    assert archivio.stop_times is not None
    passaggi = archivio.stop_times[["trip_id", "stop_id"]]
    corse = archivio.trips[["trip_id", "route_id"]]
    unione = passaggi.merge(corse, on="trip_id", how="inner")
    unione = unione[unione["stop_id"].astype("string").isin(fermate)]
    distinte = unione[["route_id", "stop_id"]].drop_duplicates()
    return [(str(r), str(f)) for r, f in distinte.itertuples(index=False)]


# =============================================================================
# Esecuzione
# =============================================================================


@dataclass(frozen=True)
class RisultatoKB:
    """Esito di una esecuzione, con le misure che servono alla curva di complessita'."""

    soddisfacibile: bool
    tempo_grounding: float
    tempo_solving: float
    atomi: int
    regole: int
    trasbordi: pd.DataFrame = field(default_factory=pd.DataFrame)
    n_fermate: int = 0
    n_fatti: int = 0
    # Popolata solo su richiesta: la chiusura transitiva ha dimensione
    # quadratica e materializzarla per ogni esecuzione costerebbe piu' del
    # calcolo stesso.
    raggiungibili: frozenset[tuple[str, str]] = frozenset()

    @property
    def tempo_totale(self) -> float:
        return self.tempo_grounding + self.tempo_solving


def esegui(
    fatti: Fatti,
    soglia_piedi: int = 250,
    con_vincoli: bool = True,
    con_indice: bool = True,
    con_chiusura: bool = True,
    mostra_raggiungibile: bool = False,
    percorso_regole: Path = PERCORSO_REGOLE,
) -> RisultatoKB:
    """Esegue rules.lp sui fatti dati, misurando grounding e solving separatamente.

    ``con_indice`` e ``con_chiusura`` sono gli interruttori usati dalla misura di
    complessita'. Il primo fa confrontare tutte le coppie di fermate invece delle
    sole celle adiacenti: serve a verificare che l'insieme dei trasbordi derivati
    sia **identico** con e senza indice, cioe' che l'indice non alteri la
    semantica. Il secondo disattiva la chiusura transitiva: la differenza fra le
    due esecuzioni attribuisce alla ricorsione la sua quota di atomi, invece di
    dedurla.

    Sono passati a clingo come costanti e non applicati riscrivendo il testo del
    programma, perche' una sostituzione testuale si rompe in silenzio appena
    qualcuno riformatta una regola.
    """
    argomenti = [
        "--warn=none",
        f"-c soglia_piedi={int(soglia_piedi)}",
        f"-c con_vincoli={1 if con_vincoli else 0}",
        f"-c con_indice={1 if con_indice else 0}",
        f"-c con_chiusura={1 if con_chiusura else 0}",
    ]
    controllo = clingo.Control(argomenti)
    controllo.add("base", [], fatti.testo)

    testo_regole = percorso_regole.read_text(encoding="utf-8")
    if mostra_raggiungibile:
        testo_regole += "\n#show raggiungibile/2.\n"
    controllo.add("base", [], testo_regole)

    inizio = perf_counter()
    controllo.ground([("base", [])])
    tempo_grounding = perf_counter() - inizio

    inizio = perf_counter()
    simboli: list[clingo.Symbol] = []
    soddisfacibile = False
    with controllo.solve(yield_=True) as risoluzione:  # type: ignore[union-attr]
        for modello in risoluzione:
            soddisfacibile = True
            simboli = list(modello.symbols(shown=True))
            break
    tempo_solving = perf_counter() - inizio

    statistiche = controllo.statistics
    atomi = int(_scava(statistiche, ("problem", "lp", "atoms"), 0))
    regole = int(_scava(statistiche, ("problem", "lp", "rules"), 0))

    return RisultatoKB(
        soddisfacibile=soddisfacibile,
        tempo_grounding=tempo_grounding,
        tempo_solving=tempo_solving,
        atomi=atomi,
        regole=regole,
        trasbordi=_tabella(simboli, fatti) if soddisfacibile else pd.DataFrame(),
        n_fermate=fatti.n_fermate,
        n_fatti=fatti.n_fatti,
        raggiungibili=_raggiungibili(simboli, fatti) if mostra_raggiungibile else frozenset(),
    )


def _raggiungibili(simboli: Sequence[clingo.Symbol], fatti: Fatti) -> frozenset[tuple[str, str]]:
    """Coppie della chiusura transitiva, ritradotte negli identificativi GTFS."""
    nome_di = fatti.fermate
    return frozenset(
        (nome_di[s.arguments[0].number], nome_di[s.arguments[1].number])
        for s in simboli
        if s.name == "raggiungibile" and len(s.arguments) == 2
    )


def _scava(statistiche: Any, percorso: Iterable[str], predefinito: float) -> float:
    corrente: Any = statistiche
    for chiave in percorso:
        try:
            corrente = corrente[chiave]
        except (KeyError, TypeError):
            return predefinito
    try:
        return float(corrente)
    except (TypeError, ValueError):
        return predefinito


def _tabella(simboli: Sequence[clingo.Symbol], fatti: Fatti) -> pd.DataFrame:
    """Ritraduce il modello in una tabella con gli identificativi GTFS originali."""
    nome_di = fatti.fermate
    tempi: dict[tuple[int, int], int] = {}
    a_piedi: set[tuple[int, int]] = set()
    accessibili: set[tuple[int, int]] = set()
    utili: set[tuple[int, int]] = set()

    for simbolo in simboli:
        argomenti = simbolo.arguments
        if simbolo.name == "trasbordo_ammissibile" and len(argomenti) == 3:
            tempi[(argomenti[0].number, argomenti[1].number)] = argomenti[2].number
        elif simbolo.name == "trasbordo_a_piedi" and len(argomenti) == 2:
            a_piedi.add((argomenti[0].number, argomenti[1].number))
        elif simbolo.name == "accessibile" and len(argomenti) == 2:
            accessibili.add((argomenti[0].number, argomenti[1].number))
        elif simbolo.name == "trasbordo_utile" and len(argomenti) == 2:
            utili.add((argomenti[0].number, argomenti[1].number))

    righe = [
        {
            "from_stop_id": nome_di[partenza],
            "to_stop_id": nome_di[arrivo],
            "min_transfer_time": tempo,
            "a_piedi": (partenza, arrivo) in a_piedi,
            "accessibile": (partenza, arrivo) in accessibili,
            "utile": (partenza, arrivo) in utili,
        }
        for (partenza, arrivo), tempo in sorted(tempi.items())
    ]
    return pd.DataFrame(
        righe,
        columns=["from_stop_id", "to_stop_id", "min_transfer_time", "a_piedi", "accessibile", "utile"],
    )


def materializza(
    archivio: ArchivioGTFS,
    destinazione: Path,
    soglia_piedi: int = 250,
) -> RisultatoKB:
    """Esegue la KB sull'intero archivio e scrive transfers.parquet."""
    fatti = genera_fatti(archivio, soglia_piedi=soglia_piedi)
    risultato = esegui(fatti, soglia_piedi=soglia_piedi)
    if not risultato.soddisfacibile:
        raise ErroreKB(
            "La base di conoscenza e' insoddisfacibile: un vincolo di integrita' ha "
            "rifiutato il modello. Rieseguire con con_vincoli=False per individuarlo."
        )
    destinazione.parent.mkdir(parents=True, exist_ok=True)
    risultato.trasbordi.to_parquet(destinazione, index=False)
    return risultato
