"""Test del raccoglitore dei feed GTFS Real-Time.

I test coprono la logica pura (attese, percorsi, deduplica, validazione della
configurazione, analisi del payload) e, con un server HTTP locale, un giro
completo del ciclo di raccolta. La rete esterna non viene mai toccata: un test
che dipende dalla disponibilita' del feed di un'agenzia fallirebbe per motivi che
non hanno nulla a che vedere con il codice.
"""

from __future__ import annotations

import csv
import json
import threading
import urllib.error
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from google.transit import gtfs_realtime_pb2

from src.collector import poll_realtime as pr


# =============================================================================
# Aiutanti
# =============================================================================


def feed_finto(timestamp: int = 1_700_000_000, n_corse: int = 2, con_ritardo: bool = True) -> bytes:
    """Costruisce un GTFS Real-Time valido in memoria.

    Serve a collaudare l'analisi del payload senza dipendere da un feed vero, che
    cambierebbe a ogni esecuzione rendendo i test non riproducibili.
    """
    messaggio = gtfs_realtime_pb2.FeedMessage()
    messaggio.header.gtfs_realtime_version = "2.0"
    messaggio.header.timestamp = timestamp
    for indice in range(n_corse):
        entita = messaggio.entity.add()
        entita.id = f"e{indice}"
        entita.trip_update.trip.trip_id = f"T{indice}"
        entita.trip_update.trip.route_id = f"L{indice % 2}"
        for sequenza in range(3):
            tappa = entita.trip_update.stop_time_update.add()
            tappa.stop_id = f"S{sequenza}"
            tappa.stop_sequence = sequenza
            if con_ritardo:
                tappa.arrival.delay = 60 * (sequenza + 1)
                tappa.arrival.time = timestamp + 300 * sequenza
    return messaggio.SerializeToString()


def config_minima(radice: Path, url: str, url_secondario: str | None = None) -> dict:
    citta = {
        "nome": "prova",
        "attiva": True,
        "fuso_orario": "Europe/Rome",
        "url_gtfs_statico": None,
        "url_gtfs_statico_md5": None,
        "feed_rt": {"trip_updates": url, "vehicle_positions": url_secondario},
        "intestazioni_http": {},
    }
    return {
        "raccolta": {
            "intervallo_polling_secondi": 5,
            "timeout_richiesta_secondi": 2,
            "tentativi_max": 1,
            "snapshot_gtfs_statico": False,
            "cartella_rt": str(radice / "rt"),
            "cartella_gtfs": str(radice / "gtfs"),
            "cartella_log": str(radice / "logs"),
        },
        "citta": [citta],
    }


class _RispostaFinta:
    """Imita quel tanto di ``http.client.HTTPResponse`` che ``scarica`` utilizza."""

    def __init__(self, dati: bytes, stato: int = 200) -> None:
        self._dati = dati
        self.status = stato

    def read(self) -> bytes:
        return self._dati

    def __enter__(self) -> "_RispostaFinta":
        return self

    def __exit__(self, *_: object) -> bool:
        return False


# =============================================================================
# Segnaposto e validazione della configurazione
# =============================================================================


def test_riconosce_i_segnaposto_non_sostituiti() -> None:
    assert pr.e_segnaposto("INSERIRE_QUI_URL_TRIP_UPDATES_CITTA_A")
    assert pr.e_segnaposto("   INSERIRE_QUI_X")
    assert not pr.e_segnaposto("https://esempio.invalid/tu")
    assert not pr.e_segnaposto(None)
    assert not pr.e_segnaposto(42)


def test_configurazione_valida_viene_interpretata(tmp_path: Path) -> None:
    config = pr.interpreta_configurazione(
        config_minima(tmp_path, "https://esempio.invalid/tu"), tmp_path
    )
    assert len(config.citta) == 1
    citta = config.citta[0]
    assert citta.nome == "prova"
    # vehicle_positions e' None: non deve comparire affatto, cosi' il ciclo di
    # polling non deve controllare a ogni giro se l'indirizzo esiste.
    assert set(citta.feed_rt) == {"trip_updates"}


def test_configurazione_con_segnaposto_viene_rifiutata(tmp_path: Path) -> None:
    grezza = config_minima(tmp_path, "INSERIRE_QUI_URL_TRIP_UPDATES_CITTA_A")
    with pytest.raises(pr.ErroreConfigurazione) as errore:
        pr.interpreta_configurazione(grezza, tmp_path)
    # Il messaggio deve dire quale citta' e quale campo: e' l'errore che si
    # incontra al primo avvio, deve essere autoesplicativo.
    assert "prova" in str(errore.value)
    assert "trip_updates" in str(errore.value)


def test_citta_disattivata_non_richiede_il_feed_obbligatorio(tmp_path: Path) -> None:
    grezza = config_minima(tmp_path, "INSERIRE_QUI_URL")
    grezza["citta"][0]["attiva"] = False
    grezza["citta"].append(
        {
            "nome": "attiva",
            "fuso_orario": "Europe/Rome",
            "feed_rt": {"trip_updates": "https://esempio.invalid/tu"},
        }
    )
    config = pr.interpreta_configurazione(grezza, tmp_path)
    assert [c.attiva for c in config.citta] == [False, True]


def test_timeout_non_puo_superare_l_intervallo(tmp_path: Path) -> None:
    grezza = config_minima(tmp_path, "https://esempio.invalid/tu")
    grezza["raccolta"]["timeout_richiesta_secondi"] = 90
    grezza["raccolta"]["intervallo_polling_secondi"] = 60
    with pytest.raises(pr.ErroreConfigurazione, match="timeout_richiesta_secondi"):
        pr.interpreta_configurazione(grezza, tmp_path)


def test_nomi_di_citta_duplicati_sono_un_errore(tmp_path: Path) -> None:
    grezza = config_minima(tmp_path, "https://esempio.invalid/tu")
    grezza["citta"].append(dict(grezza["citta"][0]))
    with pytest.raises(pr.ErroreConfigurazione, match="duplicati"):
        pr.interpreta_configurazione(grezza, tmp_path)


def test_nome_di_citta_con_caratteri_da_filesystem_e_un_errore(tmp_path: Path) -> None:
    grezza = config_minima(tmp_path, "https://esempio.invalid/tu")
    grezza["citta"][0]["nome"] = "san giovanni/rotondo"
    with pytest.raises(pr.ErroreConfigurazione, match="percorso di cartella"):
        pr.interpreta_configurazione(grezza, tmp_path)


def test_i_percorsi_relativi_sono_risolti_rispetto_alla_radice(tmp_path: Path) -> None:
    grezza = config_minima(tmp_path, "https://esempio.invalid/tu")
    grezza["raccolta"]["cartella_rt"] = "data/raw/rt"
    config = pr.interpreta_configurazione(grezza, tmp_path)
    assert config.raccolta.cartella_rt == tmp_path / "data/raw/rt"


def test_tutti_i_problemi_sono_segnalati_insieme(tmp_path: Path) -> None:
    """Chi compila config.yaml la prima volta deve vedere tutto in un colpo solo."""
    grezza = config_minima(tmp_path, "INSERIRE_QUI_URL")
    grezza["citta"].append(
        {"nome": "seconda", "fuso_orario": "Europe/Rome", "feed_rt": {"trip_updates": None}}
    )
    with pytest.raises(pr.ErroreConfigurazione) as errore:
        pr.interpreta_configurazione(grezza, tmp_path)
    assert str(errore.value).count("trip_updates") == 2


# =============================================================================
# Attesa fra i ritentativi
# =============================================================================


def test_il_backoff_cresce_e_si_ferma_al_massimo() -> None:
    # casuale=0.5 annulla il jitter: il valore atteso e' esattamente quello nominale.
    assert pr.ritardo_backoff(1, 2.0, 20.0, casuale=0.5) == pytest.approx(2.0)
    assert pr.ritardo_backoff(2, 2.0, 20.0, casuale=0.5) == pytest.approx(4.0)
    assert pr.ritardo_backoff(4, 2.0, 20.0, casuale=0.5) == pytest.approx(16.0)
    assert pr.ritardo_backoff(10, 2.0, 20.0, casuale=0.5) == pytest.approx(20.0)


def test_il_jitter_resta_nella_fascia_dichiarata() -> None:
    for casuale in (0.0, 0.25, 1.0):
        attesa = pr.ritardo_backoff(3, 2.0, 100.0, frazione_jitter=0.25, casuale=casuale)
        assert 8.0 * 0.75 <= attesa <= 8.0 * 1.25


def test_il_backoff_rifiuta_un_numero_di_tentativo_non_valido() -> None:
    with pytest.raises(ValueError):
        pr.ritardo_backoff(0, 2.0, 20.0)


# =============================================================================
# Deduplica
# =============================================================================


def test_un_feed_con_timestamp_nuovo_va_salvato() -> None:
    assert pr.deve_salvare(1_700_000_060, 1_700_000_000)


def test_un_feed_con_timestamp_invariato_e_un_duplicato() -> None:
    assert not pr.deve_salvare(1_700_000_000, 1_700_000_000)


def test_il_primo_feed_della_sessione_va_sempre_salvato() -> None:
    assert pr.deve_salvare(1_700_000_000, None)


@pytest.mark.parametrize("assente", [0, None])
def test_senza_timestamp_si_conserva_tutto(assente: int | None) -> None:
    """Meglio un duplicato in piu' che un'osservazione vera buttata via."""
    assert pr.deve_salvare(assente, 1_700_000_000)


# =============================================================================
# Percorsi su disco
# =============================================================================


def test_il_dump_finisce_nella_cartella_della_data_locale(tmp_path: Path) -> None:
    momento = datetime(2026, 3, 14, 7, 5, 9, tzinfo=ZoneInfo("Europe/Rome"))
    percorso = pr.percorso_dump(tmp_path, "bari", "trip_updates", momento, esiste=lambda _: False)
    assert percorso == tmp_path / "bari" / "2026-03-14" / "trip_updates" / "070509.pb"


def test_la_data_usata_e_quella_locale_non_quella_utc(tmp_path: Path) -> None:
    """Alle 23:30 UTC in Italia e' gia' il giorno dopo: la service_date e' locale."""
    momento_utc = datetime(2026, 7, 10, 23, 30, 0, tzinfo=timezone.utc)
    locale = momento_utc.astimezone(ZoneInfo("Europe/Rome"))
    percorso = pr.percorso_dump(tmp_path, "bari", "trip_updates", locale, esiste=lambda _: False)
    assert "2026-07-11" in str(percorso)


def test_l_ora_ripetuta_del_cambio_ora_non_sovrascrive(tmp_path: Path) -> None:
    """Alla fine dell'ora legale le 02:30 locali capitano due volte."""
    momento = datetime(2026, 10, 25, 2, 30, 0, tzinfo=ZoneInfo("Europe/Rome"))
    gia_presenti = {
        tmp_path / "bari" / "2026-10-25" / "trip_updates" / "023000.pb",
        tmp_path / "bari" / "2026-10-25" / "trip_updates" / "023000_1.pb",
    }
    percorso = pr.percorso_dump(
        tmp_path, "bari", "trip_updates", momento, esiste=lambda p: p in gia_presenti
    )
    assert percorso.name == "023000_2.pb"


def test_i_feed_diversi_finiscono_in_cartelle_diverse(tmp_path: Path) -> None:
    momento = datetime(2026, 3, 14, 7, 5, 9, tzinfo=ZoneInfo("Europe/Rome"))
    uno = pr.percorso_dump(tmp_path, "bari", "trip_updates", momento, esiste=lambda _: False)
    due = pr.percorso_dump(tmp_path, "bari", "vehicle_positions", momento, esiste=lambda _: False)
    assert uno.parent != due.parent


# =============================================================================
# Analisi del payload
# =============================================================================


def test_un_feed_valido_viene_riassunto_correttamente() -> None:
    riepilogo = pr.analizza_feed(feed_finto(timestamp=1_700_000_123, n_corse=4))
    assert riepilogo.versione == "2.0"
    assert riepilogo.timestamp_feed == 1_700_000_123
    assert riepilogo.n_entita == 4
    assert riepilogo.n_trip_update == 4
    assert riepilogo.n_stop_time_update == 12
    assert riepilogo.n_con_ritardo == 12
    assert riepilogo.n_con_orario_assoluto == 12
    assert riepilogo.relazioni_orario == {"SCHEDULED": 4}


def test_un_feed_senza_ritardi_viene_riconosciuto() -> None:
    riepilogo = pr.analizza_feed(feed_finto(con_ritardo=False))
    assert riepilogo.n_stop_time_update == 6
    assert riepilogo.n_con_ritardo == 0
    assert riepilogo.n_con_orario_assoluto == 0
    giudizio = "\n".join(pr.descrivi_feed(riepilogo, datetime.now(timezone.utc)))
    assert "NON utilizzabile" in giudizio


def test_una_pagina_html_non_viene_scambiata_per_un_feed() -> None:
    """E' il caso reale: il server risponde 200 con una pagina di errore."""
    with pytest.raises(pr.FeedNonValido, match="HTML"):
        pr.analizza_feed(b"<!DOCTYPE html><html><body>Service unavailable</body></html>")


def test_un_payload_vuoto_non_viene_scambiato_per_un_feed() -> None:
    with pytest.raises(pr.FeedNonValido, match="vuoto"):
        pr.analizza_feed(b"")


def test_un_protobuf_senza_versione_non_e_un_feed_gtfs_rt() -> None:
    """Il parsing da solo non basta: serve anche un controllo semantico.

    ``gtfs_realtime_version`` e' un campo *required* di proto2, ma protobuf
    verifica i campi obbligatori solo in scrittura: in lettura accetta senza
    protestare un messaggio che ne e' privo. I byte sono costruiti a mano proprio
    perche' l'API Python si rifiuterebbe di serializzarli, mentre un server
    malconfigurato puo' benissimo restituirli.
    """
    intestazione = b"\x18\x80\xa0\xb7\xca\x06"  # campo 3 (timestamp), varint
    grezzo = b"\x0a" + bytes([len(intestazione)]) + intestazione  # campo 1 (header)

    controllo = gtfs_realtime_pb2.FeedMessage()
    controllo.ParseFromString(grezzo)
    assert controllo.header.gtfs_realtime_version == ""  # protobuf non si oppone

    with pytest.raises(pr.FeedNonValido, match="gtfs_realtime_version"):
        pr.analizza_feed(grezzo)


def test_byte_corrotti_non_vengono_scambiati_per_un_feed() -> None:
    with pytest.raises(pr.FeedNonValido, match="protobuf illeggibile"):
        pr.analizza_feed(b"\x08\x96\x01\x1f\x7f")


def test_il_giudizio_e_positivo_su_un_feed_con_ritardi() -> None:
    giudizio = "\n".join(
        pr.descrivi_feed(pr.analizza_feed(feed_finto()), datetime.now(timezone.utc))
    )
    assert "GIUDIZIO: utilizzabile" in giudizio


# =============================================================================
# Scaricamento e ritentativi
# =============================================================================


def test_lo_scaricamento_riuscito_restituisce_i_byte() -> None:
    dati = feed_finto()
    risultato = pr.scarica(
        "https://esempio.invalid/tu", {}, 5, 3, 1.0, 4.0,
        dormi=lambda _: None, apri=lambda *a, **k: _RispostaFinta(dati),
    )
    assert risultato.ok
    assert risultato.dati == dati
    assert risultato.tentativi == 1


def test_un_errore_4xx_non_viene_ritentato() -> None:
    """Un 404 o un 401 non si risolvono riprovando: insistere e' solo dannoso."""
    chiamate = []

    def apri(*_a: object, **_k: object) -> object:
        chiamate.append(1)
        raise urllib.error.HTTPError("https://esempio.invalid/tu", 404, "Not Found", {}, None)

    risultato = pr.scarica(
        "https://esempio.invalid/tu", {}, 5, 3, 1.0, 4.0, dormi=lambda _: None, apri=apri
    )
    assert not risultato.ok
    assert len(chiamate) == 1
    assert risultato.stato_http == 404
    assert risultato.esito == pr.ESITO_ERRORE_HTTP


def test_un_errore_5xx_viene_ritentato_fino_al_limite() -> None:
    chiamate = []

    def apri(*_a: object, **_k: object) -> object:
        chiamate.append(1)
        raise urllib.error.HTTPError("https://esempio.invalid/tu", 503, "Unavailable", {}, None)

    attese: list[float] = []
    risultato = pr.scarica(
        "https://esempio.invalid/tu", {}, 5, 3, 1.0, 4.0, dormi=attese.append, apri=apri
    )
    assert len(chiamate) == 3
    assert risultato.tentativi == 3
    # Fra tre tentativi ci sono due attese, e devono essere crescenti.
    assert len(attese) == 2
    assert attese[1] > attese[0]


def test_un_errore_di_rete_viene_ritentato_e_non_solleva() -> None:
    def apri(*_a: object, **_k: object) -> object:
        raise urllib.error.URLError("nome non risolto")

    risultato = pr.scarica(
        "https://esempio.invalid/tu", {}, 5, 2, 1.0, 4.0, dormi=lambda _: None, apri=apri
    )
    assert not risultato.ok
    assert risultato.esito == pr.ESITO_ERRORE_RETE
    assert "nome non risolto" in risultato.dettaglio


def test_un_eccezione_inattesa_non_esce_dalla_funzione() -> None:
    """Il ciclo deve girare per settimane: nulla puo' propagarsi fino a lui."""

    def apri(*_a: object, **_k: object) -> object:
        raise TimeoutError("il socket non ha risposto")

    risultato = pr.scarica(
        "https://esempio.invalid/tu", {}, 5, 1, 1.0, 4.0, dormi=lambda _: None, apri=apri
    )
    assert not risultato.ok
    assert "TimeoutError" in risultato.dettaglio


# =============================================================================
# Manifest
# =============================================================================


def test_il_manifest_scrive_l_intestazione_una_volta_sola(tmp_path: Path) -> None:
    percorso = tmp_path / "giorno" / "_manifest.csv"
    pr.scrivi_riga_manifest(percorso, {"istante_utc": "A", "esito": pr.ESITO_SALVATO})
    pr.scrivi_riga_manifest(percorso, {"istante_utc": "B", "esito": pr.ESITO_DUPLICATO})

    with percorso.open(encoding="utf-8", newline="") as flusso:
        righe = list(csv.DictReader(flusso))
    assert [r["istante_utc"] for r in righe] == ["A", "B"]
    assert righe[0]["esito"] == pr.ESITO_SALVATO
    # Le colonne mancanti diventano stringhe vuote, non spariscono: il formato
    # del manifest deve restare stabile perche' la Fase 3 lo rilegge.
    assert set(righe[0]) == set(pr.COLONNE_MANIFEST)


# =============================================================================
# Copertura
# =============================================================================


def test_un_duplicato_conta_come_interrogazione_riuscita() -> None:
    """Il feed ha risposto: e' solo piu' lento della nostra cadenza."""
    contatori = pr.Contatori(salvati=6, duplicati=3, errori_rete=1)
    assert contatori.interrogazioni == 10
    assert contatori.copertura == pytest.approx(0.9)


def test_la_copertura_di_zero_interrogazioni_non_divide_per_zero() -> None:
    assert pr.Contatori().copertura == 0.0


# =============================================================================
# Archiviazione dell'orario statico
# =============================================================================


def _zip_finto(contenuto: bytes) -> bytes:
    """Byte che iniziano con la firma di un archivio zip, come il controllo richiede."""
    return b"PK\x03\x04" + contenuto


def _config_orario(
    tmp_path: Path, con_md5: bool = True
) -> tuple[pr.ConfigCitta, pr.ConfigRaccolta]:
    citta = pr.ConfigCitta(
        nome="prova",
        attiva=True,
        fuso_orario="Europe/Rome",
        url_gtfs_statico="https://esempio.invalid/gtfs.zip",
        url_gtfs_statico_md5="https://esempio.invalid/gtfs.zip.md5" if con_md5 else None,
        feed_rt={},
        intestazioni_http={},
    )
    raccolta = pr.ConfigRaccolta(
        intervallo_polling_secondi=60,
        timeout_richiesta_secondi=20,
        timeout_gtfs_statico_secondi=60,
        tentativi_max=1,
        backoff_base_secondi=1.0,
        backoff_max_secondi=2.0,
        snapshot_gtfs_statico=True,
        soglia_interruzione_secondi=300.0,
        cartella_rt=tmp_path / "rt",
        cartella_gtfs=tmp_path / "gtfs",
        cartella_log=tmp_path / "logs",
        user_agent="test",
    )
    return citta, raccolta


def _finto_server(archivio: bytes, md5_dichiarato: str | None, registro: list[str]):
    """Sostituto di ``scarica`` che risponde in base all'indirizzo richiesto.

    Il registro delle chiamate serve a verificare la proprieta' piu' importante
    dell'archiviazione: nei giorni senza modifiche l'archivio NON deve essere
    scaricato affatto.
    """

    def finto(url: str, *_a: object, **_k: object) -> pr.RisultatoDownload:
        registro.append(url)
        if url.endswith(".md5"):
            if md5_dichiarato is None:
                return pr.RisultatoDownload(False, None, 404, 1, pr.ESITO_ERRORE_HTTP, "HTTP 404")
            corpo = f"{md5_dichiarato}  rsm/gtfs.zip\n".encode("ascii")
            return pr.RisultatoDownload(True, corpo, 200, 1, pr.ESITO_SALVATO, "")
        return pr.RisultatoDownload(True, archivio, 200, 1, pr.ESITO_SALVATO, "")

    return finto


def test_interpreta_il_formato_md5_reale_di_roma() -> None:
    """Il formato e' quello verificato scaricandolo davvero da Roma Mobilita'."""
    grezzo = b"e328ed0e82a9294dc6a20b7117200375  rsm/rome_static_gtfs.zip\n"
    assert pr.interpreta_md5(grezzo) == "e328ed0e82a9294dc6a20b7117200375"


def test_interpreta_anche_un_md5_nudo() -> None:
    assert pr.interpreta_md5(b"E328ED0E82A9294DC6A20B7117200375\n") == (
        "e328ed0e82a9294dc6a20b7117200375"
    )


@pytest.mark.parametrize(
    "grezzo",
    [
        b"",
        b"<html>404 not found</html>",
        b"non-esadecimale-ma-lungo-32-caratt",
        b"abc123",
        "e328ed0e82a9294dc6a20b7117200375è".encode("utf-8"),
    ],
)
def test_un_md5_non_riconoscibile_non_viene_accettato(grezzo: bytes) -> None:
    """Una pagina di errore servita con stato 200 non deve passare per un'impronta."""
    assert pr.interpreta_md5(grezzo) is None


def test_la_prima_revisione_viene_archiviata_col_nome_del_giorno(tmp_path: Path, monkeypatch) -> None:
    citta, raccolta = _config_orario(tmp_path)
    archivio = _zip_finto(b"v1")
    monkeypatch.setattr(pr, "scarica", _finto_server(archivio, pr._md5(archivio), []))

    esito = pr.forse_archivia_orario(citta, raccolta, "2026-08-25")

    assert esito is not None and esito.origine == "scaricato"
    assert (tmp_path / "gtfs" / "prova" / "2026-08-25.zip").read_bytes() == archivio
    indice = json.loads((tmp_path / "gtfs" / "prova" / "index.json").read_text(encoding="utf-8"))
    assert indice["giorni"]["2026-08-25"]["file"] == "2026-08-25.zip"
    assert indice["giorni"]["2026-08-25"]["md5"] == pr._md5(archivio)


def test_nello_stesso_giorno_non_si_ricontrolla(tmp_path: Path, monkeypatch) -> None:
    """Senza questo, un riavvio orario riscaricherebbe decine di MB ogni volta."""
    citta, raccolta = _config_orario(tmp_path)
    archivio = _zip_finto(b"v1")
    registro: list[str] = []
    monkeypatch.setattr(pr, "scarica", _finto_server(archivio, pr._md5(archivio), registro))

    pr.forse_archivia_orario(citta, raccolta, "2026-08-25")
    quante = len(registro)
    assert pr.forse_archivia_orario(citta, raccolta, "2026-08-25") is None
    assert len(registro) == quante


def test_se_il_md5_e_invariato_l_archivio_non_viene_scaricato(tmp_path: Path, monkeypatch) -> None:
    """E' la ragione d'essere del .md5: cinquanta byte invece di decine di MB."""
    citta, raccolta = _config_orario(tmp_path)
    archivio = _zip_finto(b"v1")
    registro: list[str] = []
    monkeypatch.setattr(pr, "scarica", _finto_server(archivio, pr._md5(archivio), registro))

    pr.forse_archivia_orario(citta, raccolta, "2026-08-25")
    registro.clear()
    esito = pr.forse_archivia_orario(citta, raccolta, "2026-08-26")

    assert esito is not None and esito.origine == "invariato"
    assert registro == ["https://esempio.invalid/gtfs.zip.md5"], "lo zip non doveva essere scaricato"
    # Il giorno senza modifiche ha comunque un marcatore che punta alla versione
    # precedente: e' cio' che rende interpretabili i dump di quel giorno.
    indice = json.loads((tmp_path / "gtfs" / "prova" / "index.json").read_text(encoding="utf-8"))
    assert indice["giorni"]["2026-08-26"]["file"] == "2026-08-25.zip"
    assert len(list((tmp_path / "gtfs" / "prova").glob("*.zip"))) == 1


def test_un_md5_diverso_produce_un_nuovo_archivio(tmp_path: Path, monkeypatch) -> None:
    """E' il caso che tiene interpretabili i dump gia' raccolti."""
    citta, raccolta = _config_orario(tmp_path)
    primo = _zip_finto(b"v1")
    monkeypatch.setattr(pr, "scarica", _finto_server(primo, pr._md5(primo), []))
    pr.forse_archivia_orario(citta, raccolta, "2026-08-25")

    secondo = _zip_finto(b"v2-orario-cambiato")
    monkeypatch.setattr(pr, "scarica", _finto_server(secondo, pr._md5(secondo), []))
    esito = pr.forse_archivia_orario(citta, raccolta, "2026-08-26")

    assert esito is not None and esito.origine == "scaricato"
    assert sorted(p.name for p in (tmp_path / "gtfs" / "prova").glob("*.zip")) == [
        "2026-08-25.zip",
        "2026-08-26.zip",
    ]
    indice = json.loads((tmp_path / "gtfs" / "prova" / "index.json").read_text(encoding="utf-8"))
    assert indice["giorni"]["2026-08-25"]["file"] == "2026-08-25.zip"
    assert indice["giorni"]["2026-08-26"]["file"] == "2026-08-26.zip"


def test_senza_md5_si_ripiega_sullo_scaricamento(tmp_path: Path, monkeypatch) -> None:
    """Torino non pubblica il .md5: il confronto deve funzionare lo stesso."""
    citta, raccolta = _config_orario(tmp_path, con_md5=False)
    archivio = _zip_finto(b"v1")
    registro: list[str] = []
    monkeypatch.setattr(pr, "scarica", _finto_server(archivio, None, registro))

    pr.forse_archivia_orario(citta, raccolta, "2026-08-25")
    registro.clear()
    esito = pr.forse_archivia_orario(citta, raccolta, "2026-08-26")

    assert esito is not None and esito.origine == "invariato"
    assert registro == ["https://esempio.invalid/gtfs.zip"], "senza .md5 si scarica l'archivio"
    assert len(list((tmp_path / "gtfs" / "prova").glob("*.zip"))) == 1


def test_un_md5_irraggiungibile_non_blocca_l_archiviazione(tmp_path: Path, monkeypatch) -> None:
    citta, raccolta = _config_orario(tmp_path)
    archivio = _zip_finto(b"v1")
    monkeypatch.setattr(pr, "scarica", _finto_server(archivio, None, []))

    esito = pr.forse_archivia_orario(citta, raccolta, "2026-08-25")
    assert esito is not None and esito.origine == "scaricato"


def test_una_revisione_gia_nota_non_viene_duplicata(tmp_path: Path, monkeypatch) -> None:
    """Se l'agenzia torna a una versione precedente, si riusa l'archivio esistente."""
    citta, raccolta = _config_orario(tmp_path, con_md5=False)
    primo = _zip_finto(b"v1")
    secondo = _zip_finto(b"v2")

    monkeypatch.setattr(pr, "scarica", _finto_server(primo, None, []))
    pr.forse_archivia_orario(citta, raccolta, "2026-08-25")
    monkeypatch.setattr(pr, "scarica", _finto_server(secondo, None, []))
    pr.forse_archivia_orario(citta, raccolta, "2026-08-26")
    monkeypatch.setattr(pr, "scarica", _finto_server(primo, None, []))
    pr.forse_archivia_orario(citta, raccolta, "2026-08-27")

    archivi = sorted(p.name for p in (tmp_path / "gtfs" / "prova").glob("*.zip"))
    assert archivi == ["2026-08-25.zip", "2026-08-26.zip"]
    indice = json.loads((tmp_path / "gtfs" / "prova" / "index.json").read_text(encoding="utf-8"))
    assert indice["giorni"]["2026-08-27"]["file"] == "2026-08-25.zip"


def test_un_archivio_che_non_e_uno_zip_viene_rifiutato(tmp_path: Path, monkeypatch) -> None:
    citta, raccolta = _config_orario(tmp_path, con_md5=False)
    monkeypatch.setattr(pr, "scarica", _finto_server(b"<html>login</html>", None, []))

    esito = pr.forse_archivia_orario(citta, raccolta, "2026-08-25")
    assert esito is not None and esito.origine == "fallito"
    assert not list((tmp_path / "gtfs" / "prova").glob("*.zip"))


def test_uno_scaricamento_fallito_verra_ritentato_al_giro_dopo(tmp_path: Path, monkeypatch) -> None:
    """L'indice non va aggiornato in caso di errore, o si perderebbe il giorno."""
    citta, raccolta = _config_orario(tmp_path, con_md5=False)
    monkeypatch.setattr(
        pr,
        "scarica",
        lambda *a, **k: pr.RisultatoDownload(False, None, 503, 1, pr.ESITO_ERRORE_HTTP, "HTTP 503"),
    )
    esito = pr.forse_archivia_orario(citta, raccolta, "2026-08-25")

    assert esito is not None and esito.origine == "fallito"
    percorso_indice = tmp_path / "gtfs" / "prova" / "index.json"
    assert not percorso_indice.exists() or "2026-08-25" not in json.loads(
        percorso_indice.read_text(encoding="utf-8")
    )["giorni"]


# =============================================================================
# index.json letto dal lato della Fase 3
# =============================================================================


def test_la_versione_valida_e_quella_del_giorno_stesso() -> None:
    indice = {"giorni": {"2026-08-25": {"file": "a.zip"}, "2026-08-26": {"file": "b.zip"}}}
    assert pr.versione_valida(indice, "2026-08-26")["file"] == "b.zip"


def test_senza_voce_esplicita_vale_l_ultima_precedente() -> None:
    """Se il collector era fermo, l'orario in vigore resta quello dell'ultima revisione."""
    indice = {"giorni": {"2026-08-20": {"file": "a.zip"}, "2026-08-26": {"file": "b.zip"}}}
    assert pr.versione_valida(indice, "2026-08-23")["file"] == "a.zip"


def test_prima_della_prima_revisione_non_c_e_nulla() -> None:
    indice = {"giorni": {"2026-08-20": {"file": "a.zip"}}}
    assert pr.versione_valida(indice, "2026-08-19") is None


# =============================================================================
# Registro delle interruzioni
# =============================================================================


def _istante(ora: int, minuto: int = 0) -> datetime:
    return datetime(2026, 8, 25, ora, minuto, tzinfo=timezone.utc)


def test_una_finestra_breve_non_e_un_interruzione() -> None:
    """Un tick perso e recuperato subito non e' un buco nei dati, e' rumore."""
    assert not pr.e_interruzione(_istante(8, 0), _istante(8, 2), 300)


def test_una_finestra_oltre_la_soglia_e_un_interruzione() -> None:
    assert pr.e_interruzione(_istante(8, 0), _istante(8, 30), 300)


def test_il_gap_viene_scritto_in_jsonl_rileggibile(tmp_path: Path) -> None:
    percorso = tmp_path / "gaps.jsonl"
    pr.scrivi_gap(percorso, "roma", _istante(2, 0), _istante(8, 0), pr.CAUSA_PROCESSO_FERMO, "prova")
    pr.scrivi_gap(percorso, "roma", _istante(9, 0), _istante(9, 30), pr.CAUSA_ERRORI_RETE)

    righe = [json.loads(r) for r in percorso.read_text(encoding="utf-8").splitlines()]
    assert len(righe) == 2
    assert righe[0]["durata_secondi"] == 6 * 3600
    assert righe[0]["causa"] == pr.CAUSA_PROCESSO_FERMO
    assert righe[1]["citta"] == "roma"


def test_il_battito_sopravvive_al_riavvio(tmp_path: Path) -> None:
    percorso = tmp_path / "_battito.json"
    pr.scrivi_battito(percorso, _istante(8, 0))
    assert pr.leggi_battito(percorso) == _istante(8, 0)


@pytest.mark.parametrize("contenuto", ["", "{}", "non json", '{"ultimo_successo": "boh"}'])
def test_un_battito_illeggibile_non_fa_esplodere_nulla(tmp_path: Path, contenuto: str) -> None:
    percorso = tmp_path / "_battito.json"
    percorso.write_text(contenuto, encoding="utf-8")
    assert pr.leggi_battito(percorso) is None


def test_un_giro_riuscito_aggiorna_il_battito(tmp_path: Path) -> None:
    citta, raccolta = _config_orario(tmp_path)
    stato = pr.StatoCitta(ultimo_successo=_istante(8, 0))
    pr._aggiorna_interruzioni(citta, raccolta, stato, [pr.ESITO_SALVATO], _istante(8, 1))

    assert stato.ultimo_successo == _istante(8, 1)
    assert pr.leggi_battito(tmp_path / "rt" / "prova" / pr.NOME_BATTITO) == _istante(8, 1)


def test_un_duplicato_conta_come_giro_riuscito(tmp_path: Path) -> None:
    """Il feed ha risposto: non e' un'interruzione della raccolta."""
    citta, raccolta = _config_orario(tmp_path)
    stato = pr.StatoCitta(ultimo_successo=_istante(8, 0))
    pr._aggiorna_interruzioni(citta, raccolta, stato, [pr.ESITO_DUPLICATO], _istante(8, 1))
    assert stato.ultimo_successo == _istante(8, 1)


def test_gli_errori_prolungati_aprono_e_chiudono_una_interruzione(tmp_path: Path) -> None:
    citta, raccolta = _config_orario(tmp_path)
    stato = pr.StatoCitta(ultimo_successo=_istante(8, 0))

    # Un solo giro fallito subito dopo un successo non apre nulla.
    pr._aggiorna_interruzioni(citta, raccolta, stato, [pr.ESITO_ERRORE_RETE], _istante(8, 1))
    assert stato.interruzione_aperta is None

    # Superata la soglia, la finestra si apre e parte dall'ULTIMO SUCCESSO, non
    # dal momento in cui ce ne siamo accorti.
    pr._aggiorna_interruzioni(citta, raccolta, stato, [pr.ESITO_ERRORE_RETE], _istante(8, 20))
    assert stato.interruzione_aperta == _istante(8, 0)

    percorso = tmp_path / "rt" / "prova" / pr.NOME_GAPS
    assert not percorso.exists(), "la finestra si scrive solo quando si chiude"

    pr._aggiorna_interruzioni(citta, raccolta, stato, [pr.ESITO_SALVATO], _istante(8, 30))
    assert stato.interruzione_aperta is None
    riga = json.loads(percorso.read_text(encoding="utf-8").splitlines()[0])
    assert riga["inizio"] == _istante(8, 0).isoformat(timespec="seconds")
    assert riga["fine"] == _istante(8, 30).isoformat(timespec="seconds")
    assert riga["causa"] == pr.CAUSA_ERRORI_RETE


def test_un_riavvio_dopo_una_pausa_registra_l_interruzione(tmp_path: Path, server_locale: str) -> None:
    """La finestra fra l'arresto e il riavvio ha entrambi gli estremi solo qui."""
    grezza = config_minima(tmp_path, f"{server_locale}/tu")
    config = pr.interpreta_configurazione(grezza, tmp_path)

    battito = datetime.now(timezone.utc) - timedelta(hours=6)
    pr.scrivi_battito(tmp_path / "rt" / "prova" / pr.NOME_BATTITO, battito)

    assert pr.esegui(config, cicli_max=1, dormi=lambda _: None) == 0

    righe = [
        json.loads(r)
        for r in (tmp_path / "rt" / "prova" / pr.NOME_GAPS).read_text(encoding="utf-8").splitlines()
    ]
    assert len(righe) == 1
    assert righe[0]["causa"] == pr.CAUSA_PROCESSO_FERMO
    assert righe[0]["durata_secondi"] == pytest.approx(6 * 3600, abs=120)


def test_la_prima_esecuzione_non_inventa_interruzioni(tmp_path: Path, server_locale: str) -> None:
    config = pr.interpreta_configurazione(config_minima(tmp_path, f"{server_locale}/tu"), tmp_path)
    assert pr.esegui(config, cicli_max=1, dormi=lambda _: None) == 0
    assert not (tmp_path / "rt" / "prova" / pr.NOME_GAPS).exists()


# =============================================================================
# Indirizzi non cifrati
# =============================================================================


def test_un_indirizzo_http_e_ammesso_ma_segnalato(tmp_path: Path) -> None:
    """Rifiutarlo significherebbe rinunciare a un'agenzia che pubblica solo in chiaro."""
    grezza = config_minima(tmp_path, "http://esempio.invalid/tu")
    config = pr.interpreta_configurazione(grezza, tmp_path)
    assert config.citta[0].indirizzi_in_chiaro == ("http://esempio.invalid/tu",)


def test_un_indirizzo_https_non_risulta_in_chiaro(tmp_path: Path) -> None:
    config = pr.interpreta_configurazione(
        config_minima(tmp_path, "https://esempio.invalid/tu"), tmp_path
    )
    assert config.citta[0].indirizzi_in_chiaro == ()


def test_credenziali_su_http_sono_rifiutate(tmp_path: Path) -> None:
    """Viaggerebbero in chiaro: meglio un rifiuto all'avvio che una chiave regalata."""
    grezza = config_minima(tmp_path, "http://esempio.invalid/tu")
    grezza["citta"][0]["intestazioni_http"] = {"Authorization": "Bearer segreto"}
    with pytest.raises(pr.ErroreConfigurazione, match="chiaro"):
        pr.interpreta_configurazione(grezza, tmp_path)


def test_credenziali_su_https_sono_ammesse(tmp_path: Path) -> None:
    grezza = config_minima(tmp_path, "https://esempio.invalid/tu")
    grezza["citta"][0]["intestazioni_http"] = {"Authorization": "Bearer segreto"}
    config = pr.interpreta_configurazione(grezza, tmp_path)
    assert config.citta[0].intestazioni_http == {"Authorization": "Bearer segreto"}


def test_il_md5_senza_archivio_statico_e_un_errore(tmp_path: Path) -> None:
    grezza = config_minima(tmp_path, "https://esempio.invalid/tu")
    grezza["citta"][0]["url_gtfs_statico_md5"] = "https://esempio.invalid/gtfs.zip.md5"
    with pytest.raises(pr.ErroreConfigurazione, match="url_gtfs_statico"):
        pr.interpreta_configurazione(grezza, tmp_path)


# =============================================================================
# Giro completo contro un server HTTP locale
# =============================================================================


class _Gestore(BaseHTTPRequestHandler):
    """Serve un feed il cui timestamp avanza solo ogni due richieste.

    Riproduce il comportamento reale di un'agenzia che rigenera il feed meno
    spesso di quanto noi lo interroghiamo, cosi' il test verifica davvero la
    deduplica invece di darla per buona.
    """

    richieste = 0

    def do_GET(self) -> None:  # noqa: N802 - nome imposto da BaseHTTPRequestHandler
        _Gestore.richieste += 1
        if self.path == "/rotto":
            corpo = b"<html>errore</html>"
        else:
            corpo = feed_finto(timestamp=1_700_000_000 + 60 * ((_Gestore.richieste - 1) // 2))
        self.send_response(200)
        self.send_header("Content-Type", "application/x-protobuf")
        self.send_header("Content-Length", str(len(corpo)))
        self.end_headers()
        self.wfile.write(corpo)

    def log_message(self, *_: object) -> None:
        """Silenzia il log del server, che sporcherebbe l'output di pytest."""


@pytest.fixture
def server_locale():
    _Gestore.richieste = 0
    server = HTTPServer(("127.0.0.1", 0), _Gestore)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()


def test_un_giro_completo_salva_dump_e_manifest(tmp_path: Path, server_locale: str) -> None:
    config = pr.interpreta_configurazione(
        config_minima(tmp_path, f"{server_locale}/tu"), tmp_path
    )
    assert pr.esegui(config, cicli_max=4, dormi=lambda _: None) == 0

    dump = sorted((tmp_path / "rt" / "prova").rglob("*.pb"))
    # Quattro giri, ma il feed cambia timestamp ogni due: due dump e due duplicati.
    assert len(dump) == 2

    manifest = next((tmp_path / "rt" / "prova").rglob("_manifest.csv"))
    with manifest.open(encoding="utf-8", newline="") as flusso:
        righe = list(csv.DictReader(flusso))
    esiti = [r["esito"] for r in righe]
    assert len(righe) == 4
    assert esiti.count(pr.ESITO_SALVATO) == 2
    assert esiti.count(pr.ESITO_DUPLICATO) == 2
    # Anche i duplicati riportano il timestamp del feed: serve a ricostruire a
    # posteriori con che cadenza l'agenzia aggiornava davvero i dati.
    assert all(r["timestamp_feed"] for r in righe)


def test_un_payload_non_valido_finisce_negli_scarti(tmp_path: Path, server_locale: str) -> None:
    config = pr.interpreta_configurazione(
        config_minima(tmp_path, f"{server_locale}/rotto"), tmp_path
    )
    assert pr.esegui(config, cicli_max=1, dormi=lambda _: None) == 0

    scarti = list((tmp_path / "rt" / "prova").rglob("_scarti/**/*.bin"))
    assert len(scarti) == 1
    assert not list((tmp_path / "rt" / "prova").rglob("*.pb"))

    manifest = next((tmp_path / "rt" / "prova").rglob("_manifest.csv"))
    with manifest.open(encoding="utf-8", newline="") as flusso:
        righe = list(csv.DictReader(flusso))
    assert righe[0]["esito"] == pr.ESITO_NON_VALIDO


def test_un_feed_irraggiungibile_non_ferma_la_raccolta(tmp_path: Path) -> None:
    """Il caso piu' importante: la rete cade e il processo deve sopravvivere."""
    # La porta 1 su localhost rifiuta la connessione in modo immediato e affidabile.
    config = pr.interpreta_configurazione(
        config_minima(tmp_path, "http://127.0.0.1:1/tu"), tmp_path
    )
    assert pr.esegui(config, cicli_max=2, dormi=lambda _: None) == 0

    manifest = next((tmp_path / "rt" / "prova").rglob("_manifest.csv"))
    with manifest.open(encoding="utf-8", newline="") as flusso:
        righe = list(csv.DictReader(flusso))
    assert len(righe) == 2
    assert all(r["esito"] == pr.ESITO_ERRORE_RETE for r in righe)


def test_una_citta_inesistente_e_un_errore_di_avvio(tmp_path: Path) -> None:
    config = pr.interpreta_configurazione(
        config_minima(tmp_path, "https://esempio.invalid/tu"), tmp_path
    )
    assert pr.esegui(config, solo_citta=["inesistente"], cicli_max=1) == 2
