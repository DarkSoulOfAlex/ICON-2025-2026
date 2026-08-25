"""Lettura e validazione di un archivio GTFS statico.

Il modulo si limita a leggere e a controllare: non deriva conoscenza, non calcola
trasbordi, non decide quali corse siano attive. Serve a garantire che tutto cio'
che sta a valle lavori su dati di cui sono gia' note forma e completezza.

Due scelte guidano l'implementazione.

La prima e' che la validazione fallisce **rumorosamente e per intero**: un
archivio a cui manca una colonna obbligatoria non viene caricato a meta', e il
messaggio dice quale file e quale colonna. Un GTFS incompleto caricato
silenziosamente produce, molte fasi piu' avanti, risultati sbagliati che non
somigliano a un errore.

La seconda riguarda la memoria. ``stop_times.txt`` di Roma ha 5,6 milioni di
righe: letto senza indicare colonne e tipi costerebbe qualche gigabyte di RAM per
poi usarne una frazione. Le colonne si dichiarano, i tipi anche, e gli orari
diventano interi al momento della lettura.
"""

from __future__ import annotations

import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

import pandas as pd

# Colonne che la specifica GTFS dichiara obbligatorie, limitatamente ai file che
# questo progetto utilizza. Non e' una validazione completa dello standard: e'
# il sottoinsieme senza il quale le fasi successive non possono lavorare.
COLONNE_OBBLIGATORIE: Mapping[str, tuple[str, ...]] = {
    "agency.txt": ("agency_name", "agency_url", "agency_timezone"),
    "stops.txt": ("stop_id",),
    "routes.txt": ("route_id", "route_type"),
    "trips.txt": ("route_id", "service_id", "trip_id"),
    "stop_times.txt": ("trip_id", "arrival_time", "departure_time", "stop_id", "stop_sequence"),
    "calendar.txt": (
        "service_id",
        "monday",
        "tuesday",
        "wednesday",
        "thursday",
        "friday",
        "saturday",
        "sunday",
        "start_date",
        "end_date",
    ),
    "calendar_dates.txt": ("service_id", "date", "exception_type"),
    "transfers.txt": ("from_stop_id", "to_stop_id", "transfer_type"),
}

FILE_OBBLIGATORI = ("agency.txt", "stops.txt", "routes.txt", "trips.txt", "stop_times.txt")

# Colonne facoltative che ci interessano davvero, con il valore da usare quando
# il file non le espone affatto. Dichiararle qui evita di disseminare il codice a
# valle di controlli "se la colonna esiste".
FACOLTATIVE_STOPS: Mapping[str, object] = {
    "stop_name": "",
    "stop_lat": float("nan"),
    "stop_lon": float("nan"),
    "location_type": 0,
    "parent_station": "",
    "wheelchair_boarding": 0,
}
FACOLTATIVE_TRIPS: Mapping[str, object] = {
    "direction_id": 0,
    "wheelchair_accessible": 0,
}

COLONNE_STOP_TIMES = ("trip_id", "stop_id", "stop_sequence", "arrival_time", "departure_time")

SECONDI_IN_UN_GIORNO = 86_400


class ErroreGTFS(Exception):
    """Archivio assente, incompleto o non conforme su un punto che ci serve."""


@dataclass(frozen=True)
class ArchivioGTFS:
    """Un archivio GTFS letto in memoria.

    ``stop_times`` e' opzionale perche' e' di gran lunga il file piu' pesante e
    non tutte le elaborazioni ne hanno bisogno: la base di conoscenza lo usa solo
    per sapere quali linee servono quali fermate.
    """

    percorso: Path
    fuso_orario: str
    stops: pd.DataFrame
    routes: pd.DataFrame
    trips: pd.DataFrame
    calendar: pd.DataFrame | None
    calendar_dates: pd.DataFrame | None
    transfers: pd.DataFrame | None
    stop_times: pd.DataFrame | None = None

    @property
    def ha_calendar(self) -> bool:
        return self.calendar is not None and not self.calendar.empty

    @property
    def ha_transfers(self) -> bool:
        return self.transfers is not None and not self.transfers.empty

    def descrivi(self) -> str:
        """Riga di riepilogo, usata nei log e nelle misure di complessita'."""
        pezzi = [
            f"{len(self.stops):,} fermate",
            f"{len(self.routes):,} linee",
            f"{len(self.trips):,} corse",
        ]
        if self.stop_times is not None:
            pezzi.append(f"{len(self.stop_times):,} passaggi")
        pezzi.append("calendar.txt " + ("presente" if self.ha_calendar else "ASSENTE"))
        pezzi.append("transfers.txt " + ("presente" if self.ha_transfers else "ASSENTE"))
        return "; ".join(pezzi)


# =============================================================================
# Orari: il punto in cui il GTFS smette di somigliare a un orologio
# =============================================================================


def orario_in_secondi(testo: str | None) -> int | None:
    """Converte un orario GTFS in secondi dall'inizio del giorno di servizio.

    Il GTFS ammette e usa regolarmente valori **oltre le 24:00**: ``25:30:00`` e'
    un orario legittimo e significa l'una e mezza di notte del giorno successivo,
    ma appartenente al giorno di servizio precedente. Troncare o normalizzare a
    24 ore e' l'errore silenzioso classico su questo formato: non solleva
    eccezioni, sposta semplicemente le corse notturne sul giorno sbagliato, e in
    Fase 3 produce ritardi assurdi che sembrano un problema dei dati.

    Per questo la conversione **non riporta mai il valore sotto le 24 ore**: il
    numero restituito puo' superare 86400, ed e' compito di
    :func:`src.gtfs.calendar.istante_di_servizio` tradurlo in un istante reale.

    Un valore vuoto e' legittimo nel GTFS (fermate non a orario garantito) e
    restituisce ``None``.
    """
    if testo is None:
        return None
    testo = str(testo).strip()
    if not testo or testo.lower() in ("nan", "none"):
        return None
    pezzi = testo.split(":")
    if len(pezzi) != 3:
        raise ErroreGTFS(f"Orario GTFS malformato: {testo!r} (atteso H:MM:SS o HH:MM:SS).")
    try:
        ore, minuti, secondi = (int(p) for p in pezzi)
    except ValueError as errore:
        raise ErroreGTFS(f"Orario GTFS malformato: {testo!r}.") from errore
    if not (0 <= minuti < 60 and 0 <= secondi < 60) or ore < 0:
        raise ErroreGTFS(f"Orario GTFS fuori intervallo: {testo!r}.")
    return ore * 3600 + minuti * 60 + secondi


def orari_in_secondi(serie: pd.Series) -> pd.Series:
    """Versione vettorializzata di :func:`orario_in_secondi`.

    Esiste separatamente perche' applicare la versione scalare a 5,6 milioni di
    righe costerebbe minuti; la logica e le convenzioni sono le stesse, compreso
    il fatto che i valori oltre le 24 ore restano tali.
    """
    testo = serie.astype("string").str.strip()
    vuoti = testo.isna() | (testo == "")
    pezzi = testo.str.split(":", expand=True)
    if pezzi.shape[1] != 3:
        raise ErroreGTFS(
            "Colonna di orari non nel formato H:MM:SS: "
            f"trovati {pezzi.shape[1]} campi separati da ':'."
        )
    numeri = [pd.to_numeric(pezzi[i], errors="coerce") for i in range(3)]
    secondi = numeri[0] * 3600 + numeri[1] * 60 + numeri[2]

    # Un valore non vuoto che non si e' convertito e' un dato corrotto, non una
    # fermata senza orario: va segnalato invece di diventare silenziosamente NA.
    corrotti = (~vuoti) & secondi.isna()
    if bool(corrotti.any()):
        esempi = testo[corrotti].head(3).tolist()
        raise ErroreGTFS(f"{int(corrotti.sum())} orari malformati, ad esempio {esempi}.")
    return secondi.astype("Int32")


# =============================================================================
# Lettura dell'archivio
# =============================================================================


def _apri(percorso: Path) -> tuple[zipfile.ZipFile | None, Mapping[str, str]]:
    """Restituisce l'archivio aperto e la mappa nome-logico -> percorso interno.

    Accetta sia uno zip sia una cartella gia' estratta, e tollera che i file
    stiano in una sottocartella dell'archivio: alcune agenzie li impacchettano
    dentro una directory, e rifiutarli per questo sarebbe pedanteria.
    """
    if percorso.is_dir():
        return None, {p.name: str(p) for p in percorso.rglob("*.txt")}
    if not percorso.is_file():
        raise ErroreGTFS(f"Archivio GTFS non trovato: {percorso}")
    try:
        archivio = zipfile.ZipFile(percorso)
    except zipfile.BadZipFile as errore:
        raise ErroreGTFS(f"{percorso} non e' un archivio zip leggibile.") from errore
    return archivio, {Path(n).name: n for n in archivio.namelist() if n.endswith(".txt")}


def _leggi(
    archivio: zipfile.ZipFile | None,
    mappa: Mapping[str, str],
    nome: str,
    colonne: Sequence[str] | None = None,
    tipi: Mapping[str, str] | None = None,
) -> pd.DataFrame | None:
    if nome not in mappa:
        return None
    parametri = {
        "dtype": dict(tipi or {}),
        "encoding": "utf-8-sig",
        # Il GTFS non ha un valore convenzionale per "assente": una stringa
        # vuota e' una stringa vuota, e trasformarla in NA farebbe sparire
        # identificativi legittimi.
        "keep_default_na": False,
        "na_values": [],
        # Senza questo pandas deduce i tipi a blocchi e, su file grandi con
        # colonne facoltative spesso vuote, avverte di tipi misti. Leggere in un
        # colpo solo costa un po' di memoria in piu' ma rende il tipo di ogni
        # colonna deterministico, che e' cio' che serve per fidarsi dei confronti.
        "low_memory": False,
    }
    if colonne is not None:
        parametri["usecols"] = lambda c: c in set(colonne)  # type: ignore[assignment]
    if archivio is None:
        return pd.read_csv(mappa[nome], **parametri)  # type: ignore[arg-type]
    with archivio.open(mappa[nome]) as flusso:
        return pd.read_csv(flusso, **parametri)  # type: ignore[arg-type]


def _verifica_colonne(nome: str, tabella: pd.DataFrame, problemi: list[str]) -> None:
    attese = COLONNE_OBBLIGATORIE.get(nome, ())
    mancanti = [c for c in attese if c not in tabella.columns]
    if mancanti:
        problemi.append(
            f"{nome}: mancano le colonne obbligatorie {', '.join(mancanti)}. "
            f"Presenti: {', '.join(map(str, tabella.columns))}."
        )


def _completa(tabella: pd.DataFrame, predefinite: Mapping[str, object]) -> pd.DataFrame:
    """Aggiunge le colonne facoltative assenti con il loro valore predefinito."""
    for colonna, predefinito in predefinite.items():
        if colonna not in tabella.columns:
            tabella[colonna] = predefinito
    return tabella


def carica_archivio(
    percorso: Path | str,
    con_stop_times: bool = False,
    fuso_orario_predefinito: str = "Europe/Rome",
) -> ArchivioGTFS:
    """Legge un archivio GTFS e ne valida i punti da cui dipendono le fasi successive.

    ``con_stop_times`` e' disattivo per default perche' su Roma quel file da solo
    vale 5,6 milioni di righe: chi non ne ha bisogno non deve pagarlo.
    """
    percorso = Path(percorso)
    archivio, mappa = _apri(percorso)
    problemi: list[str] = []

    mancanti = [f for f in FILE_OBBLIGATORI if f not in mappa]
    if mancanti:
        raise ErroreGTFS(
            f"{percorso}: mancano file obbligatori del GTFS: {', '.join(mancanti)}.\n"
            f"File presenti: {', '.join(sorted(mappa)) or 'nessuno'}"
        )

    testo = {"stop_id": "string", "trip_id": "string", "route_id": "string"}
    stops = _leggi(archivio, mappa, "stops.txt", tipi={"stop_id": "string", "parent_station": "string"})
    routes = _leggi(archivio, mappa, "routes.txt", tipi={"route_id": "string"})
    trips = _leggi(archivio, mappa, "trips.txt", tipi=testo | {"service_id": "string"})
    calendar = _leggi(archivio, mappa, "calendar.txt", tipi={"service_id": "string"})
    calendar_dates = _leggi(archivio, mappa, "calendar_dates.txt", tipi={"service_id": "string"})
    transfers = _leggi(
        archivio,
        mappa,
        "transfers.txt",
        tipi={"from_stop_id": "string", "to_stop_id": "string"},
    )
    agency = _leggi(archivio, mappa, "agency.txt")

    for nome, tabella in (
        ("stops.txt", stops),
        ("routes.txt", routes),
        ("trips.txt", trips),
        ("calendar.txt", calendar),
        ("calendar_dates.txt", calendar_dates),
        ("transfers.txt", transfers),
        ("agency.txt", agency),
    ):
        if tabella is not None:
            _verifica_colonne(nome, tabella, problemi)

    # La specifica GTFS ammette che manchi calendar.txt oppure calendar_dates.txt,
    # ma non entrambi: senza nessuno dei due nessuna corsa sarebbe mai attiva e
    # l'archivio sarebbe inservibile. Roma pubblica solo calendar_dates.txt, che
    # e' legittimo; e' il caso che rende necessario questo controllo invece di
    # dare per scontata la presenza di calendar.txt.
    if calendar is None and calendar_dates is None:
        problemi.append(
            "manca sia calendar.txt sia calendar_dates.txt: nessuna corsa "
            "risulterebbe mai attiva."
        )

    if problemi:
        raise ErroreGTFS(f"Archivio GTFS non utilizzabile ({percorso}):\n  - " + "\n  - ".join(problemi))

    assert stops is not None and routes is not None and trips is not None
    stops = _completa(stops, FACOLTATIVE_STOPS)
    trips = _completa(trips, FACOLTATIVE_TRIPS)

    stops["stop_lat"] = pd.to_numeric(stops["stop_lat"], errors="coerce")
    stops["stop_lon"] = pd.to_numeric(stops["stop_lon"], errors="coerce")
    stops["location_type"] = pd.to_numeric(stops["location_type"], errors="coerce").fillna(0).astype("int8")
    stops["wheelchair_boarding"] = (
        pd.to_numeric(stops["wheelchair_boarding"], errors="coerce").fillna(0).astype("int8")
    )
    trips["wheelchair_accessible"] = (
        pd.to_numeric(trips["wheelchair_accessible"], errors="coerce").fillna(0).astype("int8")
    )

    tabella_orari: pd.DataFrame | None = None
    if con_stop_times:
        tabella_orari = _leggi(
            archivio,
            mappa,
            "stop_times.txt",
            colonne=COLONNE_STOP_TIMES,
            tipi={"trip_id": "string", "stop_id": "string"},
        )
        assert tabella_orari is not None
        _verifica_colonne("stop_times.txt", tabella_orari, problemi)
        if problemi:
            raise ErroreGTFS("stop_times.txt non utilizzabile:\n  - " + "\n  - ".join(problemi))
        tabella_orari["arrival_time"] = orari_in_secondi(tabella_orari["arrival_time"])
        tabella_orari["departure_time"] = orari_in_secondi(tabella_orari["departure_time"])
        tabella_orari["stop_sequence"] = pd.to_numeric(
            tabella_orari["stop_sequence"], errors="coerce"
        ).astype("int32")

    fuso = fuso_orario_predefinito
    if agency is not None and "agency_timezone" in agency.columns and not agency.empty:
        dichiarato = str(agency["agency_timezone"].iloc[0]).strip()
        if dichiarato:
            fuso = dichiarato

    if archivio is not None:
        archivio.close()

    return ArchivioGTFS(
        percorso=percorso,
        fuso_orario=fuso,
        stops=stops,
        routes=routes,
        trips=trips,
        calendar=calendar,
        calendar_dates=calendar_dates,
        transfers=transfers,
        stop_times=tabella_orari,
    )


def fermate_fisiche(stops: pd.DataFrame) -> pd.DataFrame:
    """Solo le fermate a cui un passeggero puo' effettivamente salire.

    ``stops.txt`` mescola fermate vere (``location_type`` 0), stazioni che le
    raggruppano (1), ingressi (2) e nodi generici (3, 4). Trattarle tutte come
    fermate gonfierebbe la base di conoscenza con entita' fra cui non esiste
    alcun trasbordo, e falserebbe la curva di complessita' contando come
    "fermate" oggetti che non lo sono.
    """
    fisiche = stops[stops["location_type"] == 0].copy()
    return fisiche[fisiche["stop_lat"].notna() & fisiche["stop_lon"].notna()]
