"""Test dei moduli GTFS.

Coprono deliberatamente solo cio' che puo' rompersi **in silenzio**, cioe' senza
sollevare eccezioni e senza somigliare a un errore:

* il calendario, che interpretato male non fallisce ma restituisce zero corse
  oppure le corse del giorno sbagliato;
* gli orari oltre le 24:00, che troncati spostano le corse notturne di un giorno;
* il cambio dell'ora legale, che sposta tutto di un'ora per due giorni all'anno.

Non c'e' un test per ogni funzione del loader: la lettura di un CSV che fallisce
lo fa rumorosamente, e collaudarla sarebbe collaudare pandas.
"""

from __future__ import annotations

import zipfile
from datetime import date, timezone
from pathlib import Path

import pandas as pd
import pytest

from src.gtfs.calendar import (
    corse_attive,
    giorno_di_calendario,
    istante_di_servizio,
    oltre_la_mezzanotte,
    servizi_attivi,
)
from src.gtfs.loader import (
    ErroreGTFS,
    carica_archivio,
    fermate_fisiche,
    orari_in_secondi,
    orario_in_secondi,
)

# =============================================================================
# GTFS giocattolo
# =============================================================================

# Rete minima ma non banale: due linee che si incrociano, una stazione che
# raggruppa due banchine, una fermata non accessibile e una corsa notturna che
# scavalca la mezzanotte. Basta a esercitare ogni regola della base di
# conoscenza e a verificare i risultati a mano.
GIOCATTOLO: dict[str, str] = {
    "agency.txt": (
        "agency_id,agency_name,agency_url,agency_timezone\n"
        "AG,Azienda di Prova,https://esempio.invalid,Europe/Rome\n"
    ),
    "stops.txt": (
        "stop_id,stop_name,stop_lat,stop_lon,location_type,parent_station,wheelchair_boarding\n"
        "STAZ,Stazione Centrale,45.070000,7.680000,1,,1\n"
        "A1,Centrale banchina 1,45.070000,7.680000,0,STAZ,1\n"
        "A2,Centrale banchina 2,45.070100,7.680100,0,STAZ,1\n"
        "B,Piazza Vicina,45.070500,7.680600,0,,1\n"
        "C,Via Lontana,45.090000,7.720000,0,,2\n"
        "D,Capolinea Nord,45.100000,7.730000,0,,0\n"
    ),
    "routes.txt": (
        "route_id,route_short_name,route_long_name,route_type\n"
        "L1,1,Linea Uno,3\n"
        "L2,2,Linea Due,3\n"
        "LN,N,Linea Notturna,3\n"
    ),
    "trips.txt": (
        "route_id,service_id,trip_id,direction_id,wheelchair_accessible\n"
        "L1,FERIALE,T1,0,1\n"
        "L2,FERIALE,T2,0,2\n"
        "LN,NOTTURNO,TN,0,1\n"
        "L1,FESTIVO,T3,0,1\n"
    ),
    "stop_times.txt": (
        "trip_id,stop_id,stop_sequence,arrival_time,departure_time\n"
        "T1,A1,1,08:00:00,08:00:00\n"
        "T1,B,2,08:05:00,08:05:00\n"
        "T1,C,3,08:20:00,08:20:00\n"
        "T2,A2,1,08:10:00,08:10:00\n"
        "T2,D,2,08:40:00,08:40:00\n"
        "TN,A1,1,24:30:00,24:30:00\n"
        "TN,C,2,25:10:00,25:10:00\n"
        "T3,A1,1,09:00:00,09:00:00\n"
        "T3,B,2,09:06:00,09:06:00\n"
    ),
    "calendar.txt": (
        "service_id,monday,tuesday,wednesday,thursday,friday,saturday,sunday,"
        "start_date,end_date\n"
        "FERIALE,1,1,1,1,1,0,0,20260101,20261231\n"
        "NOTTURNO,1,1,1,1,1,1,1,20260101,20261231\n"
        "FESTIVO,0,0,0,0,0,1,1,20260101,20261231\n"
    ),
    "calendar_dates.txt": (
        "service_id,date,exception_type\n"
        # Un festivo infrasettimanale (2 giugno 2026, martedi'): si aggiunge il
        # servizio festivo e si toglie quello feriale nello stesso giorno.
        "FESTIVO,20260602,1\n"
        "FERIALE,20260602,2\n"
        # Un servizio aggiunto e poi tolto lo stesso giorno: la rimozione vince.
        "NOTTURNO,20260815,1\n"
        "NOTTURNO,20260815,2\n"
    ),
}


def scrivi_giocattolo(
    cartella: Path, senza: tuple[str, ...] = (), modifiche: dict[str, str] | None = None
) -> Path:
    """Crea uno zip GTFS giocattolo, eventualmente mutilato per i test negativi."""
    contenuto = dict(GIOCATTOLO)
    for nome in senza:
        contenuto.pop(nome, None)
    contenuto.update(modifiche or {})
    percorso = cartella / f"giocattolo_{len(contenuto)}_{abs(hash(tuple(sorted(contenuto))))}.zip"
    with zipfile.ZipFile(percorso, "w") as archivio:
        for nome, testo in contenuto.items():
            archivio.writestr(nome, testo)
    return percorso


@pytest.fixture
def giocattolo(tmp_path: Path) -> Path:
    return scrivi_giocattolo(tmp_path)


# =============================================================================
# Orari oltre le 24:00
# =============================================================================


def test_un_orario_oltre_le_24_non_viene_riportato_sotto() -> None:
    """Troncare a 24 ore sposterebbe le corse notturne sul giorno sbagliato."""
    assert orario_in_secondi("25:30:00") == 91_800
    assert orario_in_secondi("24:00:00") == 86_400
    assert orario_in_secondi("27:45:10") == 99_910


def test_gli_orari_normali_restano_normali() -> None:
    assert orario_in_secondi("00:00:00") == 0
    assert orario_in_secondi("08:05:00") == 29_100
    assert orario_in_secondi("8:05:00") == 29_100  # ora a una cifra: ammessa dal formato


@pytest.mark.parametrize("vuoto", ["", "   ", None])
def test_un_orario_assente_non_e_un_errore(vuoto: str | None) -> None:
    """Il GTFS ammette orari vuoti sulle fermate non a orario garantito."""
    assert orario_in_secondi(vuoto) is None


@pytest.mark.parametrize("guasto", ["08:00", "otto", "08:60:00", "08:00:99", "08-00-00"])
def test_un_orario_malformato_viene_segnalato(guasto: str) -> None:
    with pytest.raises(ErroreGTFS):
        orario_in_secondi(guasto)


def test_la_versione_vettorializzata_concorda_con_quella_scalare() -> None:
    """Sono due implementazioni della stessa regola: devono restare allineate."""
    valori = ["08:00:00", "24:00:00", "25:30:00", "", "0:00:30"]
    attesi = [orario_in_secondi(v) for v in valori]
    ottenuti = orari_in_secondi(pd.Series(valori))
    assert [None if pd.isna(x) else int(x) for x in ottenuti] == attesi


def test_un_orario_corrotto_in_mezzo_a_molti_non_passa_inosservato() -> None:
    """Diventare NA silenziosamente e' esattamente il fallimento da evitare."""
    with pytest.raises(ErroreGTFS, match="malformati"):
        orari_in_secondi(pd.Series(["08:00:00"] * 50 + ["rotto"] + ["09:00:00"] * 50))


@pytest.mark.parametrize(
    "secondi,atteso",
    [(0, False), (86_399, False), (86_400, True), (91_800, True)],
)
def test_riconosce_gli_orari_del_giorno_successivo(secondi: int, atteso: bool) -> None:
    assert oltre_la_mezzanotte(secondi) is atteso


def test_il_giorno_di_calendario_avanza_oltre_la_mezzanotte() -> None:
    servizio = date(2026, 3, 3)
    assert giorno_di_calendario(servizio, 29_100) == date(2026, 3, 3)
    assert giorno_di_calendario(servizio, 91_800) == date(2026, 3, 4)
    assert giorno_di_calendario(servizio, 180_000) == date(2026, 3, 5)


# =============================================================================
# Cambio dell'ora legale
# =============================================================================


def test_un_orario_diurno_resta_alla_stessa_ora_da_orologio() -> None:
    """E' la proprieta' che la definizione 'mezzogiorno meno dodici ore' garantisce.

    Il 25 ottobre 2026 finisce l'ora legale e la giornata dura 25 ore; il 29 marzo
    inizia e ne dura 23. In entrambi i casi una corsa delle 08:00 deve restare
    alle 08:00 da orologio, altrimenti tutti gli orari di quel giorno slittano di
    un'ora e in Fase 3 sembrerebbero ritardi.
    """
    for giorno in (date(2026, 10, 25), date(2026, 3, 29), date(2026, 7, 1)):
        istante = istante_di_servizio(giorno, 8 * 3600, "Europe/Rome")
        assert (istante.hour, istante.minute) == (8, 0), giorno
        assert istante.date() == giorno


def test_la_somma_e_una_durata_reale_non_un_salto_sull_orologio() -> None:
    """Fra due orari GTFS distanti 24 ore devono passare 24 ore reali.

    Il confronto passa da UTC per una ragione che vale la pena fissare qui,
    perche' e' la stessa trappola che il modulo evita. Sottraendo due datetime
    che portano **lo stesso oggetto** ``tzinfo``, Python ignora il fuso e
    sottrae i valori da orologio: fra le 01:00 del 25 ottobre e le 00:00 del 26
    ottobre risponderebbe 23 ore, perche' non applica il cambio d'ora che cade
    in mezzo. La differenza si misura solo dopo la conversione in UTC.
    """
    inizio = istante_di_servizio(date(2026, 10, 25), 0, "Europe/Rome")
    fine = istante_di_servizio(date(2026, 10, 25), 86_400, "Europe/Rome")

    reale = (fine.astimezone(timezone.utc) - inizio.astimezone(timezone.utc)).total_seconds()
    assert reale == 86_400

    # La sottrazione ingenua sbaglia di un'ora: se un giorno questa riga
    # cominciasse a valere 86400, vorrebbe dire che Python ha cambiato semantica
    # e che il resto del modulo va riconsiderato.
    assert (fine - inizio).total_seconds() == 82_800

    # Lo scarto dal meridiano cambia nel mezzo: e' la prova che stiamo
    # attraversando davvero il cambio d'ora e non un giorno qualunque.
    assert inizio.utcoffset() != fine.utcoffset()


def test_una_corsa_notturna_cade_nel_giorno_di_calendario_successivo() -> None:
    istante = istante_di_servizio(date(2026, 3, 3), 91_800, "Europe/Rome")
    assert istante.date() == date(2026, 3, 4)
    assert (istante.hour, istante.minute) == (1, 30)


# =============================================================================
# Calendario: le due regole e la loro interazione
# =============================================================================


def _calendario(percorso: Path) -> tuple[pd.DataFrame | None, pd.DataFrame | None]:
    archivio = carica_archivio(percorso)
    return archivio.calendar, archivio.calendar_dates


def test_la_regola_settimanale_seleziona_il_giorno_giusto(giocattolo: Path) -> None:
    calendar, dates = _calendario(giocattolo)
    # 2026-08-25 e' un martedi', 2026-08-30 una domenica.
    assert "FERIALE" in servizi_attivi(calendar, dates, date(2026, 8, 25))
    assert "FERIALE" not in servizi_attivi(calendar, dates, date(2026, 8, 30))
    assert "FESTIVO" in servizi_attivi(calendar, dates, date(2026, 8, 30))


def test_il_periodo_di_validita_e_inclusivo_agli_estremi(giocattolo: Path) -> None:
    calendar, dates = _calendario(giocattolo)
    assert "NOTTURNO" in servizi_attivi(calendar, dates, date(2026, 1, 1))
    assert "NOTTURNO" in servizi_attivi(calendar, dates, date(2026, 12, 31))
    assert "NOTTURNO" not in servizi_attivi(calendar, dates, date(2025, 12, 31))
    assert "NOTTURNO" not in servizi_attivi(calendar, dates, date(2027, 1, 1))


def test_un_eccezione_additiva_aggiunge_un_servizio_fuori_regola(giocattolo: Path) -> None:
    """Il 2 giugno 2026 e' un martedi' trattato come festivo."""
    calendar, dates = _calendario(giocattolo)
    attivi = servizi_attivi(calendar, dates, date(2026, 6, 2))
    assert "FESTIVO" in attivi
    assert "FERIALE" not in attivi


def test_una_rimozione_batte_un_aggiunta_dello_stesso_giorno(giocattolo: Path) -> None:
    """Una rimozione deve poter cancellare anche un servizio appena aggiunto.

    E' il motivo per cui le tre operazioni hanno quest'ordine e non un altro.
    """
    calendar, dates = _calendario(giocattolo)
    assert "NOTTURNO" not in servizi_attivi(calendar, dates, date(2026, 8, 15))


def test_senza_calendar_txt_il_servizio_viene_tutto_dalle_eccezioni(tmp_path: Path) -> None:
    """E' il caso reale di Roma: conforme alla specifica, e senza questo test
    passerebbe inosservato che il modulo restituisce zero corse."""
    percorso = scrivi_giocattolo(tmp_path, senza=("calendar.txt",))
    calendar, dates = _calendario(percorso)
    assert calendar is None
    # Nessuna regola settimanale: nei giorni comuni non c'e' servizio...
    assert servizi_attivi(calendar, dates, date(2026, 8, 25)) == set()
    # ...ma nei giorni dichiarati come eccezione additiva si'.
    assert servizi_attivi(calendar, dates, date(2026, 6, 2)) == {"FESTIVO"}


def test_senza_nessuno_dei_due_file_l_archivio_e_rifiutato(tmp_path: Path) -> None:
    percorso = scrivi_giocattolo(tmp_path, senza=("calendar.txt", "calendar_dates.txt"))
    with pytest.raises(ErroreGTFS, match="calendar"):
        carica_archivio(percorso)


def test_le_corse_attive_seguono_i_servizi_attivi(giocattolo: Path) -> None:
    archivio = carica_archivio(giocattolo)
    martedi = corse_attive(archivio, date(2026, 8, 25))
    domenica = corse_attive(archivio, date(2026, 8, 30))
    assert martedi == {"T1", "T2", "TN"}
    assert domenica == {"T3", "TN"}


# =============================================================================
# Validazione dell'archivio
# =============================================================================


def test_una_colonna_obbligatoria_mancante_viene_nominata(tmp_path: Path) -> None:
    """Il messaggio deve dire quale file e quale colonna, non solo che c'e' un problema."""
    rotto = GIOCATTOLO["trips.txt"].replace("service_id,", "servizio,")
    percorso = scrivi_giocattolo(tmp_path, modifiche={"trips.txt": rotto})
    with pytest.raises(ErroreGTFS) as errore:
        carica_archivio(percorso)
    assert "trips.txt" in str(errore.value)
    assert "service_id" in str(errore.value)


def test_un_file_obbligatorio_mancante_viene_nominato(tmp_path: Path) -> None:
    percorso = scrivi_giocattolo(tmp_path, senza=("routes.txt",))
    with pytest.raises(ErroreGTFS, match="routes.txt"):
        carica_archivio(percorso)


def test_le_stazioni_non_sono_fermate(giocattolo: Path) -> None:
    """Contarle come fermate gonfierebbe la KB con entita' fra cui non c'e' trasbordo."""
    archivio = carica_archivio(giocattolo)
    assert len(archivio.stops) == 6
    fisiche = fermate_fisiche(archivio.stops)
    assert set(fisiche["stop_id"]) == {"A1", "A2", "B", "C", "D"}


def test_gli_orari_di_stop_times_arrivano_gia_in_secondi(giocattolo: Path) -> None:
    archivio = carica_archivio(giocattolo, con_stop_times=True)
    assert archivio.stop_times is not None
    notturna = archivio.stop_times[archivio.stop_times["trip_id"] == "TN"]
    assert sorted(int(x) for x in notturna["departure_time"]) == [86_400 + 1_800, 86_400 + 4_200]


def test_il_fuso_orario_viene_letto_da_agency(giocattolo: Path) -> None:
    assert carica_archivio(giocattolo).fuso_orario == "Europe/Rome"
