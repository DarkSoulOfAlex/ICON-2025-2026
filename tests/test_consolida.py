"""Test del consolidamento notturno.

Coprono i tre modi in cui questo passaggio puo' sbagliare senza sollevare nulla:
attribuire una corsa notturna al giorno di servizio sbagliato, perdere lo
``stop_id`` che una delle due aziende non trasmette, e conservare le
osservazioni con una regola diversa da quella dichiarata.
"""

from __future__ import annotations

import zipfile
from datetime import date
from pathlib import Path

import pandas as pd
import pytest
from google.transit import gtfs_realtime_pb2

from src.consolida.notturno import ErroreConsolidamento, Politica, consolida_giorno, main
from tests.test_gtfs import GIOCATTOLO

GIORNO = date(2026, 8, 25)


def _prepara(radice: Path, dump: list[bytes], nomi: list[str]) -> None:
    """Costruisce l'albero che il consolidamento si aspetta di trovare."""
    gtfs = radice / "data" / "raw" / "gtfs" / "prova"
    gtfs.mkdir(parents=True)
    archivio = gtfs / f"{GIORNO.isoformat()}.zip"
    with zipfile.ZipFile(archivio, "w") as zip_gtfs:
        for nome, testo in GIOCATTOLO.items():
            zip_gtfs.writestr(nome, testo)
    (gtfs / "index.json").write_text(
        '{"citta": "prova", "giorni": {"%s": {"file": "%s", "md5": "x", "origine": "scaricato"}},'
        ' "versioni": {}}' % (GIORNO.isoformat(), archivio.name),
        encoding="utf-8",
    )
    cartella = radice / "data" / "raw" / "rt" / "prova" / GIORNO.isoformat() / "trip_updates"
    cartella.mkdir(parents=True)
    for nome, contenuto in zip(nomi, dump):
        (cartella / nome).write_bytes(contenuto)


def _dump(
    timestamp: int,
    passaggi: list[tuple[str, str, int, int]],
    start_date: str = "20260825",
) -> bytes:
    """Un dump con i passaggi indicati come (trip_id, stop_id, sequenza, orario)."""
    messaggio = gtfs_realtime_pb2.FeedMessage()
    messaggio.header.gtfs_realtime_version = "2.0"
    messaggio.header.timestamp = timestamp
    per_corsa: dict[str, object] = {}
    for trip_id, stop_id, sequenza, orario in passaggi:
        if trip_id not in per_corsa:
            entita = messaggio.entity.add()
            entita.id = trip_id
            entita.trip_update.trip.trip_id = trip_id
            entita.trip_update.trip.start_date = start_date
            per_corsa[trip_id] = entita.trip_update
        tappa = per_corsa[trip_id].stop_time_update.add()  # type: ignore[union-attr]
        if stop_id:
            tappa.stop_id = stop_id
        tappa.stop_sequence = sequenza
        tappa.arrival.time = orario
    return messaggio.SerializeToString()


def test_lo_stop_id_assente_viene_recuperato_dall_orario(tmp_path: Path) -> None:
    """E' il comportamento reale di Torino: trasmette solo lo stop_sequence.

    Senza questo recupero la colonna resterebbe vuota e il dataset sarebbe
    inutilizzabile in Fase 3, senza che nulla segnali l'errore.
    """
    _prepara(tmp_path, [_dump(1_000, [("T1", "", 2, 1_800_000_000)])], ["080000.pb"])
    consolida_giorno("prova", GIORNO, tmp_path, Politica.dal_nome("tutti"))

    tabella = pd.read_parquet(
        tmp_path / "data/processed/osservazioni/prova" / f"{GIORNO.isoformat()}.parquet"
    )
    assert len(tabella) == 1
    # Nel GTFS giocattolo la corsa T1 ha B come seconda fermata.
    assert tabella["stop_id"].iloc[0] == "B"
    assert tabella["route_id"].iloc[0] == "L1"
    assert tabella["orario_programmato"].notna().all()


def test_una_corsa_notturna_va_al_suo_giorno_di_servizio(tmp_path: Path) -> None:
    """La corsa TN parte alle 24:30 del 25: circola il 26 ma appartiene al 25."""
    _prepara(
        tmp_path,
        [_dump(1_000, [("TN", "", 1, 1_800_000_000)], start_date="20260825")],
        ["003000.pb"],
    )
    consolida_giorno("prova", GIORNO, tmp_path, Politica.dal_nome("tutti"))
    tabella = pd.read_parquet(
        tmp_path / "data/processed/osservazioni/prova" / f"{GIORNO.isoformat()}.parquet"
    )
    assert tabella["service_date"].unique().tolist() == ["2026-08-25"]


def test_le_ripetizioni_identiche_collassano_i_cambi_no(tmp_path: Path) -> None:
    """La regola conserva una riga a ogni CAMBIO del valore osservato."""
    passaggio = ("T1", "A1", 1, 1_800_000_000)
    cambiato = ("T1", "A1", 1, 1_800_000_120)
    _prepara(
        tmp_path,
        [
            _dump(1_000, [passaggio]),
            _dump(1_060, [passaggio]),   # identico: non produce una riga
            _dump(1_120, [cambiato]),    # cambiato: la produce
            _dump(1_180, [cambiato]),    # di nuovo identico
        ],
        ["080000.pb", "080100.pb", "080200.pb", "080300.pb"],
    )
    riepilogo = consolida_giorno("prova", GIORNO, tmp_path, Politica.dal_nome("tutti"))
    assert riepilogo.stu_totali == 4
    assert riepilogo.righe_scritte == 2

    tabella = pd.read_parquet(
        tmp_path / "data/processed/osservazioni/prova" / f"{GIORNO.isoformat()}.parquet"
    )
    # Di ogni valore si conserva la PRIMA comparsa, non l'ultima: e' cio' che
    # rende ricostruibile con quanto anticipo l'azienda aveva quella previsione.
    assert sorted(tabella["timestamp_feed"].tolist()) == [1_000, 1_120]


def test_la_politica_ultimo_conserva_una_riga_per_passaggio(tmp_path: Path) -> None:
    passaggio = ("T1", "A1", 1, 1_800_000_000)
    _prepara(
        tmp_path,
        [_dump(1_000, [passaggio]), _dump(1_060, [("T1", "A1", 1, 1_800_000_300)])],
        ["080000.pb", "080100.pb"],
    )
    riepilogo = consolida_giorno("prova", GIORNO, tmp_path, Politica.dal_nome("ultimo"))
    assert riepilogo.righe_scritte == 1
    tabella = pd.read_parquet(
        tmp_path / "data/processed/osservazioni/prova" / f"{GIORNO.isoformat()}.parquet"
    )
    assert tabella["orario_osservato"].iloc[0] == 1_800_000_300


def test_il_giorno_in_corso_non_viene_consolidato(tmp_path: Path, monkeypatch) -> None:
    """Il collector ci sta ancora scrivendo: archiviarlo perderebbe il resto."""
    monkeypatch.chdir(tmp_path)
    oggi = date.today().isoformat()
    assert main(["--data", oggi]) == 2


def test_senza_orario_statico_il_giorno_non_e_consolidabile(tmp_path: Path) -> None:
    """Meglio fermarsi che produrre ritardi calcolati sull'orario sbagliato."""
    _prepara(tmp_path, [_dump(1_000, [("T1", "A1", 1, 1_800_000_000)])], ["080000.pb"])
    (tmp_path / "data/raw/gtfs/prova/index.json").write_text(
        '{"citta": "prova", "giorni": {}, "versioni": {}}', encoding="utf-8"
    )
    with pytest.raises(ErroreConsolidamento, match="nessuna revisione"):
        consolida_giorno("prova", GIORNO, tmp_path, Politica.dal_nome("tutti"))


# =============================================================================
# Le tre correzioni: chiave di deduplica, archivio compresso, provenienza
# =============================================================================


def _dump_misto(timestamp: int, con_time: list[tuple[str, int, int]],
                con_delay: list[tuple[str, int, int]], start_date: str = "20260825") -> bytes:
    """Un dump in cui alcuni passaggi portano l'orario e altri il solo ritardo.

    E' il comportamento reale di Torino, che non manda mai i due campi insieme:
    serve a verificare che le colonne di provenienza distinguano le due origini.
    """
    messaggio = gtfs_realtime_pb2.FeedMessage()
    messaggio.header.gtfs_realtime_version = "2.0"
    messaggio.header.timestamp = timestamp
    per_corsa: dict[str, object] = {}

    def tappa_di(trip_id: str):
        if trip_id not in per_corsa:
            entita = messaggio.entity.add()
            entita.id = trip_id
            entita.trip_update.trip.trip_id = trip_id
            entita.trip_update.trip.start_date = start_date
            per_corsa[trip_id] = entita.trip_update
        return per_corsa[trip_id].stop_time_update.add()  # type: ignore[union-attr]

    for trip_id, sequenza, orario in con_time:
        tappa = tappa_di(trip_id)
        tappa.stop_sequence = sequenza
        tappa.arrival.time = orario
    for trip_id, sequenza, ritardo in con_delay:
        tappa = tappa_di(trip_id)
        tappa.stop_sequence = sequenza
        tappa.arrival.delay = ritardo
    return messaggio.SerializeToString()


def _righe(radice: Path) -> pd.DataFrame:
    return pd.read_parquet(
        radice / "data/processed/osservazioni/prova" / f"{GIORNO.isoformat()}.parquet"
    )


def test_due_giorni_di_servizio_nella_stessa_cartella_non_si_sovrascrivono(
    tmp_path: Path,
) -> None:
    """La chiave di deduplica deve contenere la data di servizio.

    Attorno alla mezzanotte una cartella contiene due giorni di servizio, perche'
    le corse notturne del giorno prima sono ancora in circolazione. Senza la data
    nella chiave i due passaggi condividono lo stesso posto e il secondo viene
    scartato come valore invariato. Misurato sui dati veri, il difetto valeva
    quasi 194.000 righe su Roma in una sola giornata.
    """
    _prepara(
        tmp_path,
        [
            _dump(1_000, [("T1", "A", 1, 1_800_000_000)], start_date="20260825"),
            _dump(2_000, [("T1", "A", 1, 1_800_086_400)], start_date="20260826"),
        ],
        ["000500.pb", "001000.pb"],
    )
    consolida_giorno("prova", GIORNO, tmp_path, Politica.dal_nome("tutti"))

    tabella = _righe(tmp_path)
    assert len(tabella) == 2, "il passaggio del secondo giorno di servizio e' stato perso"
    assert sorted(tabella["service_date"]) == ["2026-08-25", "2026-08-26"]


def test_lo_stesso_passaggio_ripetuto_resta_una_riga_sola(tmp_path: Path) -> None:
    """Controllo speculare: la deduplica deve continuare a funzionare.

    Senza questo, una chiave che non deduplica piu' nulla passerebbe il test
    precedente e nessuno se ne accorgerebbe.
    """
    _prepara(
        tmp_path,
        [
            _dump(1_000, [("T1", "A", 1, 1_800_000_000)]),
            _dump(2_000, [("T1", "A", 1, 1_800_000_000)]),
        ],
        ["080000.pb", "080500.pb"],
    )
    consolida_giorno("prova", GIORNO, tmp_path, Politica.dal_nome("tutti"))
    assert len(_righe(tmp_path)) == 1


def test_i_dump_si_leggono_anche_dall_archivio_compresso(tmp_path: Path) -> None:
    """Rigenerare un giorno passato e' possibile solo leggendo da ``grezzi.tar.gz``.

    Il consolidamento notturno comprime i dump e rimuove la forma sciolta, quindi
    la cartella non esiste piu'. Il risultato deve essere identico a quello che si
    otterrebbe dai file sciolti: se differisse, i parquet rigenerati non sarebbero
    confrontabili con quelli prodotti la notte stessa.
    """
    import tarfile

    dump = [
        _dump(1_000, [("T1", "A", 1, 1_800_000_000)]),
        _dump(2_000, [("T1", "A", 1, 1_800_000_120)]),
    ]
    _prepara(tmp_path, dump, ["080000.pb", "080500.pb"])
    consolida_giorno("prova", GIORNO, tmp_path, Politica.dal_nome("tutti"))
    dalla_cartella = _righe(tmp_path)

    giorno_rt = tmp_path / "data/raw/rt/prova" / GIORNO.isoformat()
    with tarfile.open(giorno_rt / "grezzi.tar.gz", "w:gz") as archivio:
        archivio.add(giorno_rt / "trip_updates", arcname="trip_updates")
    for file in (giorno_rt / "trip_updates").glob("*.pb"):
        file.unlink()
    (giorno_rt / "trip_updates").rmdir()

    consolida_giorno("prova", GIORNO, tmp_path, Politica.dal_nome("tutti"))
    dall_archivio = _righe(tmp_path)

    pd.testing.assert_frame_equal(dalla_cartella, dall_archivio)


def test_le_colonne_di_provenienza_distinguono_le_due_origini(tmp_path: Path) -> None:
    """Il parquet deve dire da dove vengono orario e ritardo di ogni riga.

    Su Torino il feed non manda mai i due campi insieme: due terzi delle righe
    hanno il ritardo dichiarato dall'azienda e un terzo una nostra ricostruzione,
    e le due popolazioni differiscono di quarantacinque secondi alla mediana.
    Senza queste colonne il modello della Fase 3 imparerebbe da una miscela di
    due grandezze diverse senza poterle separare.
    """
    _prepara(
        tmp_path,
        [_dump_misto(1_000, con_time=[("T1", 1, 1_800_000_000)],
                     con_delay=[("T1", 2, 90)])],
        ["080000.pb"],
    )
    consolida_giorno("prova", GIORNO, tmp_path, Politica.dal_nome("tutti"))

    tabella = _righe(tmp_path).set_index("stop_sequence")
    assert tabella.loc[1, "origine_orario"] == "trasmesso"
    assert tabella.loc[1, "origine_ritardo"] == "ricalcolato"
    assert tabella.loc[2, "origine_orario"] == "sintetizzato"
    assert tabella.loc[2, "origine_ritardo"] == "dichiarato"
    # Il ritardo dichiarato va usato tale e quale, non ricalcolato.
    assert tabella.loc[2, "ritardo_secondi"] == 90
