"""Consolidamento notturno dei dump real-time.

Converte i dump ``.pb`` di un giorno gia' chiuso in un parquet di osservazioni,
poi archivia i grezzi in un ``.tar.gz``. Gira una volta al giorno sulla VM di
raccolta, alle quattro del mattino.

Tre scelte meritano di essere dichiarate.

**La data di servizio viene dal feed, non dalla cartella.** Il descrittore di
corsa del GTFS Real-Time porta ``start_date``, che e' la data di servizio a cui
la corsa appartiene. Non coincide sempre con la data della cartella: una corsa
delle 25:30 del giorno D circola all'una e mezza di notte del giorno D+1, quindi
viene osservata e archiviata in D+1 pur appartenendo al servizio di D. Usare la
cartella significherebbe attribuire tutte le corse notturne al giorno sbagliato e
confrontarle con l'orario programmato sbagliato.

**Il ``route_id`` e lo ``stop_id`` di Torino si recuperano dall'orario
statico.** GTT non include il ``route_id`` nei ``trip_update``, e soprattutto non
include mai lo ``stop_id``: identifica la fermata con il solo ``stop_sequence``.
E' stato verificato sui dati, e Roma si comporta all'opposto, fornendo sempre
entrambi. Per questo la chiave con cui si interroga l'orario programmato e'
``(trip_id, stop_sequence)`` e non ``(trip_id, stop_id, stop_sequence)``: la
prima funziona su entrambe le aziende, la seconda su una sola, e la specifica
GTFS garantisce che ``stop_sequence`` sia univoco dentro una corsa.

Lo ``stop_id`` mancante viene quindi riempito dall'orario statico, che e' la
fonte anagrafica autorevole. Quando il feed lo fornisce, si usa quello del feed e
si verifica che coincida con quello statico: una divergenza segnalerebbe che la
corsa in circolazione non e' quella che l'orario descrive, ed e' un'anomalia da
sapere. La stessa logica vale per il ``route_id``, che si potrebbe in teoria
ricavare dai ``vehicle_positions``, ma richiederebbe un accoppiamento temporale
fra due feed con timestamp diversi mentre ``trips.txt`` lo dice in modo esatto.

**La deduplica conserva l'evoluzione della previsione.** Vedere la voce 41 del
registro delle decisioni e la classe :class:`Politica`.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import tarfile
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator, Sequence
from zoneinfo import ZoneInfo

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from google.transit import gtfs_realtime_pb2

RADICE = Path(__file__).resolve().parent.parent.parent
if str(RADICE) not in sys.path:
    sys.path.insert(0, str(RADICE))

from src.gtfs.calendar import istante_di_servizio  # noqa: E402
from src.gtfs.indice_statico import carica_indice, versione_valida  # noqa: E402
from src.gtfs.loader import carica_archivio  # noqa: E402

log = logging.getLogger("consolida")

COLONNE = (
    "citta",
    "service_date",
    "trip_id",
    "route_id",
    "stop_id",
    "stop_sequence",
    "orario_programmato",
    "orario_osservato",
    "ritardo_secondi",
    "timestamp_feed",
    "timestamp_poll",
)

# Ogni quante righe si scarica un gruppo su disco. Serve a tenere la memoria
# limitata: una giornata di Roma produce decine di milioni di osservazioni, e
# costruirle tutte in memoria prima di scrivere non starebbe in RAM.
RIGHE_PER_GRUPPO = 2_000_000


class ErroreConsolidamento(Exception):
    """Il giorno non e' consolidabile, e proseguire produrrebbe dati sbagliati."""


# =============================================================================
# Politica di conservazione
# =============================================================================


@dataclass(frozen=True)
class Politica:
    """Quante righe conservare per ogni passaggio osservato.

    ``tutti`` e' la politica predefinita e conserva una riga a ogni CAMBIO del
    valore osservato. Non e' una deduplica per valore distinto in senso stretto:
    se una previsione torna a un valore gia' visto, quella ricomparsa viene
    conservata come evento a se'. La differenza e' voluta, perche' un'oscillazione
    e' informazione sulla stabilita' della stima, e perche' riconoscere i valori
    gia' visti richiederebbe di tenere in memoria l'intero insieme dei valori di
    ogni passaggio, che su Roma significa decine di milioni di voci.

    ``ultimo`` conserva solo l'ultima osservazione di ogni passaggio, cioe' la
    piu' vicina al transito reale. E' la politica piu' economica ed e' sufficiente
    se alla Fase 3 interessa solo il ritardo effettivo.

    ``fasce`` conserva l'ultima osservazione disponibile prima di ciascuna soglia
    di anticipo. Preserva l'informazione che motiva ``tutti`` - quanto era
    affidabile la previsione con un dato anticipo - a un costo fisso per
    passaggio invece che variabile.
    """

    nome: str
    soglie_anticipo: tuple[int, ...] = (3600, 1800, 900, 600, 300, 120, 0)

    @classmethod
    def dal_nome(cls, nome: str) -> "Politica":
        if nome not in ("tutti", "ultimo", "fasce"):
            raise ErroreConsolidamento(f"Politica sconosciuta: {nome!r}")
        return cls(nome=nome)


# =============================================================================
# Lettura dei dump
# =============================================================================


@dataclass
class Osservazione:
    trip_id: str
    route_id: str
    stop_id: str
    stop_sequence: int
    service_date: str
    orario_osservato: int | None
    ritardo_dichiarato: int | None
    timestamp_feed: int
    timestamp_poll: int


def _istante_dal_nome(percorso: Path, giorno: date, fuso: ZoneInfo) -> int:
    """Ricava l'istante del poll dal nome del file, che e' l'ora locale HHMMSS."""
    base = percorso.stem.split("_")[0]
    try:
        ore, minuti, secondi = int(base[:2]), int(base[2:4]), int(base[4:6])
    except (ValueError, IndexError):
        return 0
    locale = datetime(giorno.year, giorno.month, giorno.day, ore, minuti, secondi, tzinfo=fuso)
    return int(locale.timestamp())


def leggi_dump(percorso: Path, giorno: date, fuso: ZoneInfo) -> Iterator[Osservazione]:
    """Estrae le osservazioni da un singolo dump, senza interpretarle."""
    messaggio = gtfs_realtime_pb2.FeedMessage()
    try:
        messaggio.ParseFromString(percorso.read_bytes())
    except Exception:
        log.warning("dump illeggibile, saltato: %s", percorso.name)
        return

    timestamp_feed = int(messaggio.header.timestamp)
    timestamp_poll = _istante_dal_nome(percorso, giorno, fuso)
    predefinita = giorno.isoformat()

    for entita in messaggio.entity:
        if not entita.HasField("trip_update"):
            continue
        corsa = entita.trip_update.trip
        # start_date e' la data di SERVIZIO, che per le corse notturne non
        # coincide con quella della cartella.
        grezza = corsa.start_date.strip() if corsa.start_date else ""
        if len(grezza) == 8 and grezza.isdigit():
            service_date = f"{grezza[:4]}-{grezza[4:6]}-{grezza[6:]}"
        else:
            service_date = predefinita

        for tappa in entita.trip_update.stop_time_update:
            evento = None
            if tappa.HasField("arrival"):
                evento = tappa.arrival
            elif tappa.HasField("departure"):
                evento = tappa.departure
            if evento is None:
                continue
            yield Osservazione(
                trip_id=corsa.trip_id,
                route_id=corsa.route_id or "",
                stop_id=tappa.stop_id,
                stop_sequence=int(tappa.stop_sequence),
                service_date=service_date,
                orario_osservato=int(evento.time) if evento.HasField("time") else None,
                ritardo_dichiarato=int(evento.delay) if evento.HasField("delay") else None,
                timestamp_feed=timestamp_feed,
                timestamp_poll=timestamp_poll,
            )


# =============================================================================
# Orario programmato
# =============================================================================


def carica_orario(citta: str, service_date: str, cartella_gtfs: Path) -> tuple[dict, dict]:
    """Restituisce (orario programmato, corsa->linea) per una data di servizio.

    L'archivio giusto e' quello che ``index.json`` associa a quella data: e'
    esattamente il motivo per cui quell'indice viene mantenuto dal collector.
    """
    percorso_indice = cartella_gtfs / citta / "index.json"
    indice = carica_indice(percorso_indice, citta)
    voce = versione_valida(indice, service_date)
    if voce is None:
        raise ErroreConsolidamento(
            f"[{citta}] nessuna revisione dell'orario statico valida per {service_date}. "
            f"Controllare {percorso_indice}."
        )
    archivio_zip = cartella_gtfs / citta / voce["file"]
    if not archivio_zip.is_file():
        raise ErroreConsolidamento(f"[{citta}] archivio mancante: {archivio_zip}")

    log.info("[%s] %s -> orario %s", citta, service_date, voce["file"])
    archivio = carica_archivio(archivio_zip, con_stop_times=True)
    assert archivio.stop_times is not None

    orari = archivio.stop_times[["trip_id", "stop_id", "stop_sequence", "arrival_time"]]
    orari = orari.dropna(subset=["arrival_time"])
    # Chiave (corsa, posizione) e non (corsa, fermata, posizione): Torino non
    # trasmette lo stop_id, e la specifica garantisce che stop_sequence sia
    # univoco dentro una corsa. Il valore porta anche la fermata, che serve a
    # riempire il campo mancante.
    programmato = {
        (str(t), int(q)): (str(s), int(a))
        for t, s, q, a in orari.itertuples(index=False)
    }
    linea_di = {
        str(t): str(r) for t, r in archivio.trips[["trip_id", "route_id"]].itertuples(index=False)
    }
    return programmato, linea_di


# =============================================================================
# Consolidamento di un giorno
# =============================================================================


def _schema() -> pa.Schema:
    return pa.schema(
        [
            ("citta", pa.string()),
            ("service_date", pa.string()),
            ("trip_id", pa.string()),
            ("route_id", pa.string()),
            ("stop_id", pa.string()),
            ("stop_sequence", pa.int32()),
            ("orario_programmato", pa.int64()),
            ("orario_osservato", pa.int64()),
            ("ritardo_secondi", pa.int32()),
            ("timestamp_feed", pa.int64()),
            ("timestamp_poll", pa.int64()),
        ]
    )


@dataclass
class Riepilogo:
    citta: str
    giorno: str
    dump_letti: int
    stu_totali: int
    righe_scritte: int
    passaggi_distinti: int
    mb_grezzi: float
    mb_parquet: float

    @property
    def compressione(self) -> float:
        return 0.0 if self.mb_grezzi == 0 else self.mb_parquet / self.mb_grezzi


def consolida_giorno(
    citta: str,
    giorno: date,
    radice: Path = RADICE,
    politica: Politica | None = None,
    fuso: str = "Europe/Rome",
) -> Riepilogo:
    """Converte i dump di un giorno in parquet. Non tocca i grezzi."""
    politica = politica or Politica.dal_nome("tutti")
    zona = ZoneInfo(fuso)
    cartella = radice / "data" / "raw" / "rt" / citta / giorno.isoformat() / "trip_updates"
    if not cartella.is_dir():
        raise ErroreConsolidamento(f"[{citta}] nessun dump per {giorno}: {cartella} non esiste.")

    dump = sorted(cartella.glob("*.pb"))
    if not dump:
        raise ErroreConsolidamento(f"[{citta}] nessun file .pb in {cartella}.")

    destinazione = radice / "data" / "processed" / "osservazioni" / citta / f"{giorno.isoformat()}.parquet"
    destinazione.parent.mkdir(parents=True, exist_ok=True)

    cartella_gtfs = radice / "data" / "raw" / "gtfs"
    orari: dict[str, tuple[dict, dict]] = {}

    # Stato della deduplica: per ogni passaggio, l'ultimo valore osservato. Basta
    # questo, e non l'insieme di tutti i valori, perche' la politica registra i
    # CAMBI: la memoria resta proporzionale ai passaggi, non alle osservazioni.
    ultimo_valore: dict[tuple[str, int], int | None] = {}
    ultima_riga: dict[tuple[str, int], list] = {}
    # Contatore in una lista per poterlo aggiornare dentro il ciclo senza nonlocal.
    divergenze = [0]

    scrittore = pq.ParquetWriter(destinazione, _schema(), compression="zstd")
    accumulate: list[list] = []
    stu_totali = 0
    righe_scritte = 0

    def scarica_gruppo() -> None:
        nonlocal accumulate, righe_scritte
        if not accumulate:
            return
        tabella = pa.Table.from_arrays(
            [pa.array(colonna) for colonna in zip(*accumulate)], schema=_schema()
        )
        scrittore.write_table(tabella)
        righe_scritte += len(accumulate)
        accumulate = []

    try:
        for percorso in dump:
            for osservazione in leggi_dump(percorso, giorno, zona):
                stu_totali += 1
                if osservazione.service_date not in orari:
                    orari[osservazione.service_date] = carica_orario(
                        citta, osservazione.service_date, cartella_gtfs
                    )
                programmato, linea_di = orari[osservazione.service_date]

                chiave = (osservazione.trip_id, osservazione.stop_sequence)
                voce = programmato.get(chiave)
                fermata_statica, secondi = voce if voce is not None else ("", None)

                # Lo stop_id del feed ha la precedenza quando c'e'; altrimenti
                # vale quello dell'orario. Se ci sono entrambi e non coincidono,
                # la corsa in circolazione non e' quella descritta dall'orario.
                if osservazione.stop_id and fermata_statica and osservazione.stop_id != fermata_statica:
                    divergenze[0] += 1
                fermata = osservazione.stop_id or fermata_statica

                orario_programmato = (
                    int(
                        istante_di_servizio(
                            date.fromisoformat(osservazione.service_date), secondi, zona
                        ).timestamp()
                    )
                    if secondi is not None
                    else None
                )

                osservato = osservazione.orario_osservato
                ritardo = osservazione.ritardo_dichiarato
                if osservato is None and ritardo is not None and orario_programmato is not None:
                    osservato = orario_programmato + ritardo
                if ritardo is None and osservato is not None and orario_programmato is not None:
                    ritardo = osservato - orario_programmato
                if osservato is None:
                    continue

                # Il route_id manca nei trip_update di Torino: si recupera
                # dall'orario statico, che e' la fonte anagrafica autorevole.
                linea = osservazione.route_id or linea_di.get(osservazione.trip_id, "")

                riga = [
                    citta,
                    osservazione.service_date,
                    osservazione.trip_id,
                    linea,
                    fermata,
                    osservazione.stop_sequence,
                    orario_programmato,
                    osservato,
                    ritardo,
                    osservazione.timestamp_feed,
                    osservazione.timestamp_poll,
                ]

                if politica.nome == "ultimo":
                    ultima_riga[chiave] = riga
                    continue
                if ultimo_valore.get(chiave) == osservato:
                    continue
                ultimo_valore[chiave] = osservato
                accumulate.append(riga)
                if len(accumulate) >= RIGHE_PER_GRUPPO:
                    scarica_gruppo()

        if politica.nome == "ultimo":
            accumulate = list(ultima_riga.values())
        scarica_gruppo()
    finally:
        scrittore.close()

    if divergenze[0]:
        log.warning(
            "[%s] %d osservazioni con stop_id del feed diverso da quello dell'orario: "
            "la corsa in circolazione potrebbe non essere quella descritta.",
            citta, divergenze[0],
        )

    mb_grezzi = sum(p.stat().st_size for p in dump) / 1_048_576
    mb_parquet = destinazione.stat().st_size / 1_048_576
    passaggi = len(ultimo_valore) or len(ultima_riga)

    return Riepilogo(
        citta=citta,
        giorno=giorno.isoformat(),
        dump_letti=len(dump),
        stu_totali=stu_totali,
        righe_scritte=righe_scritte,
        passaggi_distinti=passaggi,
        mb_grezzi=mb_grezzi,
        mb_parquet=mb_parquet,
    )


def verifica(destinazione: Path, atteso: int) -> None:
    """Rilegge il parquet e ne controlla coerenza e completezza.

    Si esegue prima di comprimere i grezzi: comprimere sulla base di un parquet
    che non e' stato riletto significherebbe scoprire un problema quando i dump
    sciolti non ci sono piu'.
    """
    tabella = pq.read_table(destinazione)
    if tabella.num_rows != atteso:
        raise ErroreConsolidamento(
            f"{destinazione.name}: attese {atteso:,} righe, rilette {tabella.num_rows:,}."
        )
    if list(tabella.schema.names) != list(COLONNE):
        raise ErroreConsolidamento(f"{destinazione.name}: colonne inattese {tabella.schema.names}.")
    for colonna in ("trip_id", "stop_id", "orario_osservato", "timestamp_feed"):
        if tabella.column(colonna).null_count:
            raise ErroreConsolidamento(
                f"{destinazione.name}: {tabella.column(colonna).null_count:,} valori nulli in "
                f"'{colonna}', che non puo' esserlo."
            )


def archivia_grezzi(citta: str, giorno: date, radice: Path = RADICE) -> Path | None:
    """Comprime i dump del giorno in un unico .tar.gz e rimuove i file sciolti.

    I grezzi NON vengono cancellati: restano dentro l'archivio, che e' la prova
    di provenienza dei dati e va conservata per tutta la campagna. Sparisce solo
    la forma sciolta, che occupa molto piu' spazio.
    """
    cartella = radice / "data" / "raw" / "rt" / citta / giorno.isoformat()
    sottocartelle = [p for p in (cartella / "trip_updates", cartella / "vehicle_positions") if p.is_dir()]
    if not sottocartelle:
        return None

    destinazione = cartella / "grezzi.tar.gz"
    attesi = sum(len(list(p.glob("*.pb"))) for p in sottocartelle)
    with tarfile.open(destinazione, "w:gz") as archivio:
        for sottocartella in sottocartelle:
            archivio.add(sottocartella, arcname=sottocartella.name)

    # Si conta cosa e' finito dentro prima di togliere qualcosa da fuori.
    with tarfile.open(destinazione, "r:gz") as archivio:
        dentro = sum(1 for m in archivio.getmembers() if m.name.endswith(".pb"))
    if dentro != attesi:
        destinazione.unlink(missing_ok=True)
        raise ErroreConsolidamento(
            f"[{citta}] l'archivio conterrebbe {dentro} dump invece di {attesi}: non rimuovo nulla."
        )

    for sottocartella in sottocartelle:
        for file in sottocartella.glob("*.pb"):
            file.unlink()
        sottocartella.rmdir()
    return destinazione


# =============================================================================
# Avvio
# =============================================================================


def citta_disponibili(radice: Path = RADICE) -> list[str]:
    cartella = radice / "data" / "raw" / "rt"
    return sorted(p.name for p in cartella.iterdir() if p.is_dir()) if cartella.is_dir() else []


def main(argv: Sequence[str] | None = None) -> int:
    analizzatore = argparse.ArgumentParser(description=__doc__)
    analizzatore.add_argument("--citta", default="", help="elenco separato da virgole (default: tutte)")
    analizzatore.add_argument("--data", default="", help="AAAA-MM-GG (default: ieri)")
    analizzatore.add_argument("--rifai", action="store_true", help="rigenera un parquet gia' esistente")
    analizzatore.add_argument(
        "--politica", default="tutti", choices=("tutti", "ultimo", "fasce"),
        help="quante righe conservare per passaggio",
    )
    analizzatore.add_argument(
        "--senza-archivio", action="store_true", help="non comprimere i grezzi",
    )
    argomenti = analizzatore.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)-7s %(message)s", datefmt="%H:%M:%S"
    )

    zona = ZoneInfo("Europe/Rome")
    oggi = datetime.now(timezone.utc).astimezone(zona).date()
    giorno = date.fromisoformat(argomenti.data) if argomenti.data else oggi - timedelta(days=1)

    # Non si tocca mai il giorno in corso: il collector ci sta ancora scrivendo,
    # e un archivio creato adesso perderebbe tutto cio' che arriva dopo.
    if giorno >= oggi:
        log.error("Il giorno %s non e' ancora chiuso: si consolidano solo i giorni passati.", giorno)
        return 2

    elenco = [c.strip() for c in argomenti.citta.split(",") if c.strip()] or citta_disponibili()
    if not elenco:
        log.error("Nessuna citta' con dati raccolti.")
        return 2

    politica = Politica.dal_nome(argomenti.politica)
    problemi = 0
    for citta in elenco:
        destinazione = (
            RADICE / "data" / "processed" / "osservazioni" / citta / f"{giorno.isoformat()}.parquet"
        )
        if destinazione.exists() and not argomenti.rifai:
            log.info("[%s] %s gia' consolidato, salto (usare --rifai per rigenerarlo)", citta, giorno)
            continue
        try:
            riepilogo = consolida_giorno(citta, giorno, RADICE, politica)
            verifica(destinazione, riepilogo.righe_scritte)
            log.info(
                "[%s] %s: %d dump, %s stop_time_update -> %s righe (%s passaggi distinti)",
                citta, giorno, riepilogo.dump_letti,
                f"{riepilogo.stu_totali:,}", f"{riepilogo.righe_scritte:,}",
                f"{riepilogo.passaggi_distinti:,}",
            )
            log.info(
                "[%s] grezzi %.1f MB -> parquet %.1f MB (%.1f%%)",
                citta, riepilogo.mb_grezzi, riepilogo.mb_parquet, riepilogo.compressione * 100,
            )
            if not argomenti.senza_archivio:
                archivio = archivia_grezzi(citta, giorno, RADICE)
                if archivio is not None:
                    log.info("[%s] grezzi archiviati in %s (%.1f MB)", citta, archivio.name,
                             archivio.stat().st_size / 1_048_576)
        except ErroreConsolidamento as errore:
            log.error("%s", errore)
            problemi += 1
        except Exception:
            log.exception("[%s] errore imprevisto nel consolidamento di %s", citta, giorno)
            problemi += 1

    return 1 if problemi else 0


if __name__ == "__main__":
    raise SystemExit(main())
