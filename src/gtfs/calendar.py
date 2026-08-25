"""Calendario di servizio GTFS: quali corse circolano in una data data.

Il modulo esiste perche' due cose, in questo formato, sembrano ovvie e non lo
sono.

La prima e' che il calendario ha **due regimi**, e le due citta' del progetto ne
usano uno ciascuno. Torino pubblica ``calendar.txt``, che dichiara una regola
settimanale con un periodo di validita', piu' ``calendar_dates.txt`` per le
eccezioni. Roma **non pubblica affatto** ``calendar.txt``: ogni singolo giorno di
servizio e' elencato come eccezione additiva in ``calendar_dates.txt``. Entrambi
sono conformi alla specifica. Un modulo scritto sull'assunzione che
``calendar.txt`` esista funzionerebbe su Torino e restituirebbe zero corse su
Roma, senza sollevare nulla.

La seconda e' che il **giorno di servizio non coincide con il giorno di
calendario**. Una corsa che parte alle 25:30 del giorno di servizio del 3 marzo
circola all'una e mezza di notte del 4 marzo, ma appartiene al servizio del 3.
Questa distinzione e' la ragione per cui gli orari restano in secondi non
normalizzati fino all'ultimo momento utile.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone, tzinfo
from zoneinfo import ZoneInfo

import pandas as pd

from src.gtfs.loader import SECONDI_IN_UN_GIORNO, ArchivioGTFS, ErroreGTFS

# Nomi delle colonne di calendar.txt, nell'ordine di datetime.date.weekday().
GIORNI_SETTIMANA = (
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
)

ECCEZIONE_AGGIUNTA = 1
ECCEZIONE_RIMOSSA = 2


def _come_data(valore: object) -> date:
    """Interpreta una data GTFS, che nel formato e' un intero ``AAAAMMGG``."""
    if isinstance(valore, date) and not isinstance(valore, datetime):
        return valore
    if isinstance(valore, datetime):
        return valore.date()
    testo = str(valore).strip()
    if len(testo) != 8 or not testo.isdigit():
        raise ErroreGTFS(f"Data GTFS malformata: {valore!r} (atteso AAAAMMGG).")
    return date(int(testo[:4]), int(testo[4:6]), int(testo[6:]))


def servizi_attivi(
    calendar: pd.DataFrame | None,
    calendar_dates: pd.DataFrame | None,
    giorno: date,
) -> set[str]:
    """Insieme dei ``service_id`` attivi in una data data di servizio.

    L'ordine delle tre operazioni non e' arbitrario ed e' quello imposto dalla
    specifica: si parte dalla regola settimanale, si aggiungono le eccezioni di
    tipo 1, si tolgono quelle di tipo 2. La rimozione viene per ultima perche'
    un'eccezione di tipo 2 deve poter cancellare anche un servizio aggiunto da
    un'eccezione di tipo 1, non solo uno previsto dalla regola settimanale.

    Quando ``calendar`` e' assente l'insieme di partenza e' vuoto e tutto il
    servizio arriva dalle eccezioni additive: e' il caso di Roma, ed e' conforme.
    """
    attivi: set[str] = set()

    if calendar is not None and not calendar.empty:
        colonna_giorno = GIORNI_SETTIMANA[giorno.weekday()]
        if colonna_giorno not in calendar.columns:
            raise ErroreGTFS(f"calendar.txt: manca la colonna '{colonna_giorno}'.")
        for riga in calendar.itertuples(index=False):
            if int(getattr(riga, colonna_giorno)) != 1:
                continue
            if not (_come_data(riga.start_date) <= giorno <= _come_data(riga.end_date)):
                continue
            attivi.add(str(riga.service_id))

    if calendar_dates is not None and not calendar_dates.empty:
        delle_date = calendar_dates[
            calendar_dates["date"].map(_come_data) == giorno
        ]
        aggiunti = {
            str(r.service_id)
            for r in delle_date.itertuples(index=False)
            if int(r.exception_type) == ECCEZIONE_AGGIUNTA
        }
        rimossi = {
            str(r.service_id)
            for r in delle_date.itertuples(index=False)
            if int(r.exception_type) == ECCEZIONE_RIMOSSA
        }
        attivi |= aggiunti
        attivi -= rimossi

    return attivi


def corse_attive(archivio: ArchivioGTFS, giorno: date) -> set[str]:
    """Insieme dei ``trip_id`` che circolano in una data data di servizio."""
    servizi = servizi_attivi(archivio.calendar, archivio.calendar_dates, giorno)
    if not servizi:
        return set()
    selezione = archivio.trips["service_id"].astype("string").isin(servizi)
    return set(archivio.trips.loc[selezione, "trip_id"].astype("string").tolist())


# =============================================================================
# Dal giorno di servizio all'istante reale
# =============================================================================


def istante_di_servizio(giorno: date, secondi: int, fuso: tzinfo | str) -> datetime:
    """Istante assoluto corrispondente a un orario GTFS di un giorno di servizio.

    Il calcolo non e' "mezzanotte locale piu' N secondi", ed e' la specifica
    stessa a dirlo: gli orari GTFS sono misurati **da mezzogiorno meno dodici
    ore** del giorno di servizio. Nei giorni normali le due definizioni
    coincidono; nei due giorni all'anno in cui cambia l'ora legale no, e la
    differenza e' esattamente un'ora su tutte le corse della giornata.

    L'aritmetica passa per UTC di proposito. In Python, sommare un ``timedelta``
    a un datetime con fuso orario fa aritmetica sull'orologio da parete e
    conserva il fuso di partenza: attraversando il cambio d'ora produrrebbe un
    istante con lo scarto sbagliato. Convertire, sommare e riconvertire e' l'unico
    modo per ottenere una durata reale.

    Il parametro ``secondi`` puo' superare 86400: e' il caso normale delle corse
    notturne, e il risultato cade legittimamente nel giorno di calendario
    successivo.
    """
    zona = ZoneInfo(fuso) if isinstance(fuso, str) else fuso
    mezzogiorno = datetime.combine(giorno, time(12, 0), tzinfo=zona)
    mezzanotte_di_servizio = mezzogiorno.astimezone(timezone.utc) - timedelta(hours=12)
    return (mezzanotte_di_servizio + timedelta(seconds=int(secondi))).astimezone(zona)


def giorno_di_calendario(giorno: date, secondi: int) -> date:
    """Giorno di calendario in cui cade un orario del giorno di servizio.

    Serve a rendere esplicito, e collaudabile, lo scarto fra i due concetti: per
    ogni multiplo di 24 ore contenuto nell'orario si avanza di un giorno.
    """
    return giorno + timedelta(days=int(secondi) // SECONDI_IN_UN_GIORNO)


def oltre_la_mezzanotte(secondi: int | None) -> bool:
    """Vero se l'orario appartiene al giorno di calendario successivo."""
    return secondi is not None and int(secondi) >= SECONDI_IN_UN_GIORNO


def riepiloga_calendario(archivio: ArchivioGTFS, giorno: date) -> dict[str, int]:
    """Numeri di controllo su una giornata, per accorgersi di un calendario vuoto.

    Un archivio interpretato male non lancia eccezioni: restituisce zero corse.
    Questo riepilogo esiste per rendere quel silenzio visibile.
    """
    servizi = servizi_attivi(archivio.calendar, archivio.calendar_dates, giorno)
    corse = corse_attive(archivio, giorno)
    return {
        "servizi_attivi": len(servizi),
        "corse_attive": len(corse),
        "servizi_totali": int(archivio.trips["service_id"].nunique()),
        "corse_totali": len(archivio.trips),
    }
