"""Diagnosi del consolidamento sui giorni pieni, in sola lettura.

Nasce da un'anomalia trovata nei parquet: mediana del ritardo negativa su
entrambe le citta', deviazione standard di quasi due ore su Roma, e valori
esattamente a -86.400 s. Le prime verifiche su una giornata **parziale** - 47
dump per 50 minuti - hanno escluso le spiegazioni meccaniche e smentito
l'ipotesi che la negativita' venisse dall'ottimismo delle previsioni lontane. Ma
in una finestra di cinquanta minuti l'ora programmata e l'anticipo della
previsione sono la stessa variabile travestita, quindi quelle conclusioni non
sono trasferibili: servono giornate intere.

Lo script non modifica nulla. Legge i parquet consolidati e un campione dei dump
grezzi, e stampa sei quadri:

1. **Il rollover.** Quante righe cadono vicino a +/- 24 ore, da quali corse
   vengono, se quelle corse abbiano davvero orari statici oltre le 24 ore e in
   quale ora del giorno il feed le abbia emesse. Distingue il salto di giorno da
   una previsione stantia di una corsa ferma, che ha una firma diversa: valori
   grandi ma non prossimi a 86.400, concentrati su poche corse.
2. **Il collo della deduplica.** Quante coppie (corsa, fermata) compaiono con
   piu' di una data di servizio dentro la stessa cartella. La chiave di deduplica
   non contiene la data di servizio, quindi ogni collisione e' una riga soppressa
   in silenzio, e succede solo attorno alla mezzanotte.
3. **Il ritardo per ora del giorno**, sull'intera giornata. Se la mediana fosse
   negativa a **tutte** le ore, comprese la notte e le ore di morbida, sarebbe un
   indizio a favore del margine inserito negli orari; se lo fosse solo di giorno,
   la spiegazione e' un'altra.
4. **L'anticipo con cui le previsioni sono emesse**, confrontato fra le due
   citta'. Sulla giornata parziale erano 15,9 minuti di mediana su Roma e 2,1 su
   Torino: se regge, e' una differenza strutturale fra i due produttori.
5. **Il ritardo per anticipo della previsione, dentro ciascuna fascia oraria.**
   E' il quadro che conta: aggregando le fasce, anticipo e ora programmata
   restano confusi, ed e' l'errore che ha fatto sembrare vera l'ipotesi
   dell'ottimismo. Separarli richiede giornate intere, ed e' il motivo per cui
   questo script esiste.
6. **Il filtro al momento del passaggio**, con quante righe sopravvivono e come
   cambia la mediana per fascia oraria.

Ogni tabella dichiara la numerosita' di ogni riga: le percentuali su basi
sottili non vanno lette come stime.

    python scripts/diagnosi_consolidamento.py --giorno 2026-08-28
"""

from __future__ import annotations

import argparse
import sys
import tarfile
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from typing import Iterable, Iterator, Sequence
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

RADICE = Path(__file__).resolve().parents[1]
if str(RADICE) not in sys.path:
    sys.path.insert(0, str(RADICE))

from google.transit import gtfs_realtime_pb2 as pb  # noqa: E402

from src.consolida.notturno import carica_orario  # noqa: E402
from src.gtfs.calendar import istante_di_servizio  # noqa: E402
from src.gtfs.loader import carica_archivio  # noqa: E402

CITTA = ("roma", "torino")
FUSO = ZoneInfo("Europe/Rome")
GIORNO = 86_400
SOGLIA_CONFRONTO_MODI = 3_000
"""Righe minime per modo, su fermate condivise, perche' il confronto sia un risultato.

Sotto questa soglia una mediana e' un'indicazione e non una stima, e riportarla
in tabella la farebbe sembrare piu' solida di quanto sia. Meglio una domanda
aperta dichiarata che una tabella su base troppo sottile.
"""

TIPI_LINEA = {
    0: "tram", 1: "metro", 2: "treno", 3: "bus", 4: "traghetto",
    5: "funicolare", 6: "funivia", 7: "cremagliera", 11: "filobus", 12: "monorotaia",
}

FASCE_ANTICIPO = (
    (-10**9, 0, "gia' passato"),
    (0, 300, "0-5 min"),
    (300, 900, "5-15 min"),
    (900, 1800, "15-30 min"),
    (1800, 3600, "30-60 min"),
    (3600, 10**9, "oltre 60 min"),
)


def _mediana(valori: Sequence[float]) -> str:
    return f"{np.median(valori):.0f}" if len(valori) else "-"


# =============================================================================
# 1-3. Quadri ricavabili dal parquet consolidato
# =============================================================================


def analizza_parquet(percorso: Path, citta: str, cartella_gtfs: Path) -> pd.DataFrame | None:
    if not percorso.is_file():
        print(f"  [{citta}] parquet assente: {percorso}")
        return None

    d = pd.read_parquet(
        percorso,
        columns=["service_date", "trip_id", "route_id", "stop_id", "stop_sequence",
                 "orario_programmato", "orario_osservato", "ritardo_secondi",
                 "timestamp_feed"],
    )
    r = d["ritardo_secondi"]
    print(f"\n  [{citta}] {percorso.name}: {len(d):,} righe, "
          f"date di servizio {sorted(d.service_date.unique())}")
    print(f"    mediana {r.median():>8.0f}  media {r.mean():>8.0f}  std {r.std():>9.0f}")
    print(f"    min     {r.min():>8.0f}  q1    {r.quantile(.25):>8.0f}  "
          f"q3 {r.quantile(.75):>8.0f}  max {r.max():.0f}")

    # ---- 1. Rollover
    print(f"\n    --- 1. Salto di giorno contro previsione stantia ---")
    vicino = d[((r + GIORNO).abs() <= 600) | ((r - GIORNO).abs() <= 600)]
    grandi = d[r.abs() > 3600]
    print(f"    |ritardo| > 1 h                : {len(grandi):>9,} ({len(grandi)/len(d):.3%}) "
          f"su {grandi.trip_id.nunique():,} corse")
    print(f"    entro 10 min da +/- 24 h       : {len(vicino):>9,} ({len(vicino)/len(d):.3%}) "
          f"su {vicino.trip_id.nunique():,} corse")
    if len(grandi):
        conc = grandi.trip_id.value_counts()
        print(f"    concentrazione: le prime 10 corse fanno "
              f"{conc.head(10).sum()/len(grandi):.1%} delle righe grandi")
    if len(vicino):
        # Le corse coinvolte hanno davvero orari statici oltre le 24 ore?
        notturne = corse_oltre_24h(citta, sorted(vicino.service_date.unique()), cartella_gtfs)
        quota = vicino.trip_id.isin(notturne).mean()
        print(f"    quota di quelle corse con orario statico oltre le 24 h: {quota:.1%}")
        print(f"    (vicino a 1 = salto di giorno; vicino a 0 = altra causa)")
        ore = pd.to_datetime(vicino.timestamp_feed, unit="s", utc=True).dt.tz_convert(FUSO).dt.hour
        print(f"    ore in cui il feed le ha emesse: {dict(sorted(Counter(ore).items()))}")
        print("    primi cinque casi:")
        for _, x in vicino.head(5).iterrows():
            print(f"      servizio {x.service_date} corsa {x.trip_id} seq {x.stop_sequence:>3} "
                  f"prog {_istante(x.orario_programmato)} oss {_istante(x.orario_osservato)} "
                  f"ritardo {x.ritardo_secondi:,}")

    # ---- 3. Ritardo per ora del giorno, giornata intera
    print(f"\n    --- 3. Ritardo per ora PROGRAMMATA, giornata intera ---")
    ore = pd.to_datetime(d.orario_programmato, unit="s", utc=True).dt.tz_convert(FUSO).dt.hour
    tab = d.assign(ora=ore).groupby("ora")["ritardo_secondi"].agg(["size", "median", "mean", "std"])
    print(f"    {'ora':>4} {'righe':>10} {'mediana':>9} {'media':>9} {'std':>9}")
    for ora, x in tab.iterrows():
        print(f"    {ora:>4} {int(x['size']):>10,} {x['median']:>9.0f} "
              f"{x['mean']:>9.0f} {x['std']:>9.0f}")
    negative = (tab["median"] < 0).sum()
    print(f"    ore con mediana negativa: {negative} su {len(tab)}")
    print(f"    (tutte negative = indizio di margine negli orari; solo di giorno = altra causa)")

    quadro_senza_orario(d, citta, cartella_gtfs)
    quadro_corse_spostate(d, citta, sorted(d.service_date.unique()), cartella_gtfs)
    quadro_collisioni(d)
    quadro_per_tipo(d, ore, citta, sorted(d.service_date.unique()), cartella_gtfs)
    return d


def tipi_di_linea(citta: str, date_servizio: Iterable[str], cartella_gtfs: Path) -> dict[str, int]:
    """Corrispondenza linea -> tipo di veicolo, dall'orario statico."""
    from src.gtfs.indice_statico import carica_indice, versione_valida

    for sd in date_servizio:
        try:
            indice = carica_indice(cartella_gtfs / citta / "index.json", citta)
            voce = versione_valida(indice, sd)
            if voce is None:
                continue
            archivio = carica_archivio(cartella_gtfs / citta / voce["file"])
            return {
                str(r): int(t)
                for r, t in archivio.routes[["route_id", "route_type"]].itertuples(index=False)
            }
        except Exception as errore:
            print(f"    (tipi di linea non caricabili per {sd}: {errore})")
    return {}


def corse_oltre_24h(citta: str, date_servizio: Iterable[str], cartella_gtfs: Path) -> set[str]:
    """Corse il cui orario statico supera le 24 ore, per le date indicate.

    Serve a distinguere il salto di giorno dalle altre cause di ritardo enorme:
    se le corse coinvolte hanno davvero un orario oltre la mezzanotte, il salto
    e' la spiegazione; se non ce l'hanno, l'anomalia viene da altrove.
    """
    corse: set[str] = set()
    for sd in date_servizio:
        try:
            programmato, _ = carica_orario(citta, sd, cartella_gtfs)
        except Exception as errore:  # l'archivio puo' mancare per quella data
            print(f"    (orario non caricabile per {sd}: {errore})")
            continue
        for (trip, _seq), (_stop, secondi) in programmato.items():
            if secondi >= GIORNO:
                corse.add(trip)
    return corse


def _istante(valore) -> str:
    """Formatta un istante POSIX, tollerando i nulli.

    I nulli esistono davvero: quando la giunzione con l'orario statico non trova
    la corsa, ``orario_programmato`` resta nullo e la riga finisce comunque nel
    parquet, perche' il ritardo dichiarato dal feed non ha bisogno dell'orario
    programmato per essere registrato. Formattarli senza controllo faceva
    interrompere la diagnosi.
    """
    if pd.isna(valore):
        return "     -    "
    return f"{pd.Timestamp(int(valore), unit='s', tz='UTC').tz_convert(FUSO):%m-%d %H:%M}"


def quadro_senza_orario(d: pd.DataFrame, citta: str, cartella_gtfs: Path) -> None:
    """Righe la cui giunzione con l'orario statico non ha trovato corrispondenza.

    Sono un problema perche' passano comunque: se il feed porta il ritardo
    dichiarato, il ramo che richiede l'orario programmato non scatta e la riga
    entra nel parquet con un ritardo valido ma senza il proprio riferimento
    temporale. Per la Fase 3 sono righe su cui non si puo' calcolare nulla che
    dipenda dall'orario, e vanno contate prima di decidere se tenerle.
    """
    print()
    print("    --- 1-bis. Righe senza orario programmato ---")
    manca = d.orario_programmato.isna()
    print(f"    righe con orario_programmato nullo: {manca.sum():,} ({manca.mean():.3%}) "
          f"su {d[manca].trip_id.nunique():,} corse")
    if not manca.any():
        print("    nessuna: la giunzione trova sempre corrispondenza")
        return
    sotto = d[manca]
    print(f"    di cui con ritardo comunque valorizzato: {sotto.ritardo_secondi.notna().sum():,} "
          f"({sotto.ritardo_secondi.notna().mean():.1%})")
    print(f"    mediana del loro ritardo: {sotto.ritardo_secondi.median()}")

    # La corsa manca del tutto dall'orario, o manca solo quella fermata?
    for sd in sorted(sotto.service_date.unique()):
        parte = sotto[sotto.service_date == sd]
        try:
            programmato, _ = carica_orario(citta, sd, cartella_gtfs)
        except Exception as errore:
            print(f"    ({sd}: orario non caricabile, {errore})")
            continue
        corse_note = {t for t, _ in programmato}
        corse = set(parte.trip_id.unique())
        assenti = corse - corse_note
        print(f"    {sd}: {len(corse):,} corse coinvolte, di cui {len(assenti):,} "
              f"({len(assenti)/len(corse):.0%}) assenti dall'orario statico")
        print(f"      -> assenti = corse aggiunte in tempo reale o archivio che non le copre")
        print(f"      -> presenti = la corsa c'e' ma non quella stop_sequence")


def quadro_corse_spostate(d: pd.DataFrame, citta: str, date_servizio: Sequence[str],
                          cartella_gtfs: Path) -> None:
    """Il terzo fenomeno: ritardi enormi che non sono salti di giorno.

    Ha una firma propria, distinta sia dal rollover sia dalle righe senza orario.
    Si misura per distinguere una previsione stantia - il feed che continua a
    trasmettere una corsa ferma - da una corsa realmente spostata nel tempo, che
    ha lo stesso ritardo su tutte le proprie fermate e un orario osservato
    prossimo all'istante di emissione.
    """
    print()
    print("    --- 1-ter. Ritardi enormi che NON sono salti di giorno ---")
    r = d.ritardo_secondi
    lontane = ((r + GIORNO).abs() <= 600) | ((r - GIORNO).abs() <= 600)
    grandi = d[(r.abs() > 3600) & ~lontane]
    if grandi.empty:
        print("    nessuna")
        quadro_blocchi(d, grandi, citta, date_servizio, cartella_gtfs)
        return
    print(f"    righe: {len(grandi):,} ({len(grandi)/len(d):.3%}) su "
          f"{grandi.trip_id.nunique():,} corse")
    conc = grandi.trip_id.value_counts()
    print(f"    concentrazione: le prime 10 corse fanno {conc.head(10).sum()/len(grandi):.1%}")
    coinvolte = set(grandi.trip_id)
    tutte = d[d.trip_id.isin(coinvolte)]
    print(f"    su quelle corse, quota di righe grandi: {len(grandi)/len(tutte):.1%}")
    print(f"    (vicino a 1 = la corsa e' spostata per intero; bassa = poche fermate anomale)")

    # Ritardo costante lungo la corsa? Uno spostamento uniforme ha varianza bassa.
    per_corsa = grandi.groupby("trip_id").ritardo_secondi.agg(["std", "mean", "size"])
    print(f"    dispersione del ritardo DENTRO la corsa: mediana della std "
          f"{per_corsa['std'].median():.0f} s, contro un ritardo medio di "
          f"{per_corsa['mean'].median():.0f} s")
    print(f"    (std piccola rispetto alla media = corsa spostata in blocco)")

    # Previsione stantia o rapporto corrente? Se l'osservato segue l'istante di
    # emissione, il feed sta dicendo "sta passando ora", non ripetendo una stima.
    valide = grandi.dropna(subset=["orario_osservato", "timestamp_feed"])
    if len(valide):
        scarto = (valide.orario_osservato - valide.timestamp_feed) / 60.0
        print(f"    osservato meno istante di emissione: mediana {scarto.median():.0f} min, "
              f"q1 {scarto.quantile(.25):.0f}, q3 {scarto.quantile(.75):.0f}")
        print(f"    (vicino a zero = rapporto corrente; molto negativo = previsione stantia)")
    ore = pd.to_datetime(grandi.timestamp_feed, unit="s", utc=True).dt.tz_convert(FUSO).dt.hour
    print(f"    ore di emissione: {dict(sorted(Counter(ore).items()))}")

    quadro_blocchi(d, grandi, citta, date_servizio, cartella_gtfs)


def quadro_blocchi(d: pd.DataFrame, grandi: pd.DataFrame, citta: str,
                   date_servizio: Sequence[str], cartella_gtfs: Path) -> None:
    """Il veicolo si porta dietro il ritardo sulla corsa successiva del suo turno?

    E' il solo modo che questi dati offrono per distinguere le due letture del
    fenomeno. Se una corsa e' davvero partita con un'ora e mezza di ritardo, il
    veicolo quel ritardo lo trascina anche sulla corsa seguente dello stesso
    turno, perche' e' lo stesso mezzo che deve tornare indietro. Se invece si
    tratta di un'etichetta sbagliata - un veicolo che percorre una corsa
    riportando l'identificativo di una precedente - le corse successive del turno
    risultano normali, perche' il ritardo non e' mai esistito.

    Il turno e' il ``block_id`` del GTFS. Dove non e' valorizzato la domanda resta
    indecidibile, e va detto invece di sostituirlo con un'euristica.
    """
    print()
    print("    --- 1-quater. Il ritardo si trasmette alla corsa successiva del turno? ---")
    if grandi.empty:
        print("    nessuna corsa spostata da esaminare")
        return

    blocco_di: dict[str, str] = {}
    partenza_di: dict[str, int] = {}
    for sd in date_servizio:
        try:
            from src.gtfs.indice_statico import carica_indice, versione_valida

            indice = carica_indice(cartella_gtfs / citta / "index.json", citta)
            voce = versione_valida(indice, sd)
            if voce is None:
                continue
            archivio = carica_archivio(cartella_gtfs / citta / voce["file"], con_stop_times=True)
        except Exception as errore:
            print(f"    ({sd}: archivio non caricabile, {errore})")
            continue
        trips = archivio.trips
        if "block_id" not in trips.columns:
            print("    trips.txt non ha la colonna block_id: domanda indecidibile")
            return
        # Il campo puo' esserci ed essere vuoto: su Roma sono 179.177 stringhe
        # vuote, che un controllo sui soli nulli non intercetta. Senza questo
        # filtro tutte le corse finirebbero in un unico turno fittizio e il test
        # restituirebbe un numero plausibile e privo di significato, che e' il
        # modo peggiore in cui una misura puo' sbagliare.
        etichetta = trips["block_id"].astype("string").fillna("").str.strip()
        validi = trips[etichetta != ""]
        if validi.empty:
            print(f"    block_id presente ma **mai valorizzato** su {citta}: "
                  f"{len(trips):,} corse, tutte con turno vuoto.")
            print(f"    La domanda e' indecidibile su questa citta', e non viene forzata.")
            return
        blocco_di = {str(t): str(b) for t, b in
                     validi[["trip_id", "block_id"]].itertuples(index=False)}
        partenza_di = (archivio.stop_times.dropna(subset=["arrival_time"])
                       .groupby("trip_id").arrival_time.min().astype("int64").to_dict())
        break

    if not blocco_di:
        print("    nessun turno disponibile: domanda indecidibile")
        return

    # Corse successive, nello stesso turno, di quelle spostate.
    per_blocco: dict[str, list[str]] = defaultdict(list)
    for trip, blocco in blocco_di.items():
        per_blocco[blocco].append(trip)
    for blocco in per_blocco:
        per_blocco[blocco].sort(key=lambda t: partenza_di.get(str(t), 0))

    spostate = set(grandi.trip_id.unique())
    successive: set[str] = set()
    con_turno = 0
    for trip in spostate:
        blocco = blocco_di.get(str(trip))
        if blocco is None:
            continue
        con_turno += 1
        fratelli = per_blocco[blocco]
        try:
            posizione = fratelli.index(str(trip))
        except ValueError:
            continue
        successive.update(fratelli[posizione + 1: posizione + 3])
    successive -= spostate

    print(f"    corse spostate: {len(spostate):,}, di cui con turno noto: {con_turno:,}")
    if not successive:
        print("    nessuna corsa successiva nel turno: domanda indecidibile")
        return
    osservate = d[d.trip_id.isin(successive)]
    print(f"    corse successive nel turno: {len(successive):,}, "
          f"di cui osservate nel feed: {osservate.trip_id.nunique():,} "
          f"({len(osservate):,} righe)")
    if osservate.empty:
        print("    nessuna di esse compare nel feed: domanda indecidibile")
        return
    print(f"    ritardo delle corse successive : mediana "
          f"{osservate.ritardo_secondi.median():>8.0f} s")
    print(f"    ritardo di tutte le corse      : mediana "
          f"{d.ritardo_secondi.median():>8.0f} s")
    print(f"    quota delle successive con |ritardo| > 1 h: "
          f"{(osservate.ritardo_secondi.abs() > 3600).mean():.1%}")
    print(f"    (quota alta = il veicolo trascina il ritardo, quindi corsa davvero")
    print(f"     in ritardo; quota bassa = etichetta sbagliata sulla sola corsa)")


def quadro_collisioni(d: pd.DataFrame) -> None:
    """Collisioni della chiave di deduplica, misurate sull'intero file.

    Contarle su un campione di dump non le trova: il fenomeno e' notturno, e sei
    finestre distribuite sulla giornata hanno bassa probabilita' di cadere a
    cavallo della mezzanotte. Sul parquet si misura per intero.
    """
    print()
    print("    --- 2. Collisioni della chiave di deduplica (sul file intero) ---")
    per_coppia = d.groupby(["trip_id", "stop_sequence"]).service_date.nunique()
    collisioni = int((per_coppia > 1).sum())
    print(f"    coppie (corsa, fermata) distinte: {len(per_coppia):,}")
    print(f"    con piu' di una data di servizio : {collisioni:,} ({collisioni/len(per_coppia):.3%})")
    if collisioni:
        print(f"    ogni collisione e' almeno una riga soppressa: la chiave di")
        print(f"    deduplica non contiene la data di servizio")
        date_coinvolte = d[d.set_index(["trip_id", "stop_sequence"]).index.isin(
            per_coppia[per_coppia > 1].index)].service_date.value_counts()
        print(f"    date coinvolte: {dict(date_coinvolte)}")


def quadro_per_tipo(d: pd.DataFrame, ore: pd.Series, citta: str,
                    date_servizio: Sequence[str], cartella_gtfs: Path) -> None:
    """Ritardo per ora e per tipo di veicolo, con il controllo di legittimita'.

    Serve a mettere alla prova la spiegazione del margine negli orari: una linea
    in sede propria non incontra la congestione che il margine dovrebbe
    assorbire. Il confronto fra modi e' pero' legittimo solo se i modi servono
    gli stessi luoghi: se il tram copre corridoi che il bus non tocca, si
    confrontano reti diverse e non modi diversi. Per questo si riporta anche il
    confronto ristretto alle **fermate servite da entrambi**, che e' l'unico in
    cui la differenza puo' essere attribuita al modo.
    """
    print()
    print("    --- 3-bis. Ritardo per tipo di linea ---")
    mappa = tipi_di_linea(citta, date_servizio, cartella_gtfs)
    if not mappa:
        print("    tipi di linea non disponibili")
        return

    tipi_statici = Counter(mappa.values())
    d = d.assign(ora=ore, tipo=d.route_id.map(mappa))
    tipi_feed = Counter(d.tipo.dropna().astype(int))
    print(f"    tipi nell'orario statico : "
          + ", ".join(f"{TIPI_LINEA.get(k, k)}={v}" for k, v in sorted(tipi_statici.items())))
    print(f"    tipi presenti nel FEED   : "
          + ", ".join(f"{TIPI_LINEA.get(k, k)}={v:,}" for k, v in sorted(tipi_feed.items())))
    mancanti = set(tipi_statici) - set(tipi_feed)
    if mancanti:
        print(f"    ASSENTI dal feed: "
              + ", ".join(TIPI_LINEA.get(k, str(k)) for k in sorted(mancanti))
              + " -> il confronto fra modi non e' possibile su questa citta'")

    noti = d[d.tipo.notna()]
    if noti.empty or noti.tipo.nunique() < 2:
        print("    meno di due tipi presenti: confronto non eseguibile")
        return
    presenti = sorted(noti.tipo.unique())
    etichette = [TIPI_LINEA.get(int(x), f"tipo {int(x)}") for x in presenti]

    print(f"    {'ora':>5} " + " ".join(f"{e:>16}" for e in etichette))
    for ora in sorted(noti.ora.unique()):
        blocco = noti[noti.ora == ora]
        celle = []
        for tipo in presenti:
            s = blocco[blocco.tipo == tipo]
            celle.append(f"{_mediana(s.ritardo_secondi.values):>8}({len(s):>6,})"
                         if len(s) else f"{'-':>16}")
        print(f"    {ora:>5} " + " ".join(celle))
    print(f"    {'tutte':>5} " + " ".join(
        f"{_mediana(noti[noti.tipo == tipo].ritardo_secondi.values):>8}"
        f"({len(noti[noti.tipo == tipo]):>6,})" for tipo in presenti))

    # ---- Il confronto e' legittimo? Fermate servite da piu' di un modo.
    print()
    print("    Controllo di legittimita': i modi servono gli stessi luoghi?")
    per_fermata = noti.groupby("stop_id").tipo.nunique()
    condivise = set(per_fermata[per_fermata > 1].index)
    print(f"    fermate servite da un solo modo: {int((per_fermata == 1).sum()):,}")
    print(f"    fermate servite da piu' modi   : {len(condivise):,}")
    for tipo in presenti:
        s = noti[noti.tipo == tipo]
        quota = s.stop_id.isin(condivise).mean() if len(s) else 0.0
        print(f"      {TIPI_LINEA.get(int(tipo), tipo):>12}: {quota:.1%} delle righe "
              f"su fermate condivise")
    if not condivise:
        print("    nessuna fermata condivisa: si confrontano reti diverse, non modi.")
        return
    ristretto = noti[noti.stop_id.isin(condivise)]
    minimo = min(len(ristretto[ristretto.tipo == tipo]) for tipo in presenti)
    if minimo < SOGLIA_CONFRONTO_MODI:
        print(f"    Il modo meno rappresentato ha {minimo:,} righe su fermate condivise,")
        print(f"    sotto la soglia di {SOGLIA_CONFRONTO_MODI:,}: il confronto ristretto NON")
        print(f"    viene riportato come risultato. La domanda resta aperta: con questi dati")
        print(f"    non e' decidibile se la differenza fra modi sia differenza fra modi o")
        print(f"    fra corridoi.")
        return
    print(f"    Ristretto alle sole fermate condivise ({len(ristretto):,} righe):")
    print(f"    {'':>5} " + " ".join(f"{e:>16}" for e in etichette))
    print(f"    {'':>5} " + " ".join(
        f"{_mediana(ristretto[ristretto.tipo == tipo].ritardo_secondi.values):>8}"
        f"({len(ristretto[ristretto.tipo == tipo]):>6,})" for tipo in presenti))
    print(f"    Se qui la differenza fra modi sparisce, era differenza fra corridoi.")


# =============================================================================
# Sorgente dei dump: cartella sciolta oppure archivio compresso
# =============================================================================


class SorgenteDump:
    """I dump di una giornata, letti dalla cartella o dall'archivio compresso.

    Il consolidamento notturno comprime i ``.pb`` del giorno in ``grezzi.tar.gz``
    e rimuove la forma sciolta, quindi una diagnosi su un giorno passato non
    trova piu' la cartella. Poiche' il motivo per cui questa diagnosi e' uno
    script e non un comando incollato a mano e' proprio la ripetibilita' su
    qualunque giorno, la lettura dall'archivio non e' un'aggiunta di comodo: senza
    di essa lo script funzionerebbe solo sul giorno corrente.

    Non si estrae nulla su disco. La VM ha spazio contato e un giorno di dump
    sciolti pesa piu' di un gigabyte.
    """

    def __init__(self, cartella_giorno: Path) -> None:
        self.cartella = cartella_giorno / "trip_updates"
        self.archivio = cartella_giorno / "grezzi.tar.gz"
        self._da_tar = not self.cartella.is_dir() and self.archivio.is_file()
        self._nomi: list[str] = []

    @property
    def origine(self) -> str:
        if self.cartella.is_dir():
            return f"cartella {self.cartella.name}"
        if self._da_tar:
            return f"archivio {self.archivio.name}"
        return "assente"

    def disponibile(self) -> bool:
        return self.cartella.is_dir() or self._da_tar

    def nomi(self) -> list[str]:
        """Nomi dei dump di trip_updates, ordinati per orario."""
        if self._nomi:
            return self._nomi
        if self.cartella.is_dir():
            self._nomi = sorted(p.name for p in self.cartella.glob("*.pb"))
        elif self._da_tar:
            # Una passata sull'archivio per l'elenco. tarfile.add ordina i membri
            # di una cartella, quindi l'ordine dentro l'archivio e' gia' quello
            # per orario, ma si riordina comunque per non dipendere da questo.
            with tarfile.open(self.archivio, "r:gz") as tar:
                self._nomi = sorted(
                    Path(m.name).name
                    for m in tar
                    if m.isfile() and m.name.endswith(".pb") and "trip_updates" in m.name
                )
        return self._nomi

    def leggi(self, voluti: Iterable[str]) -> Iterator[tuple[str, bytes]]:
        """Contenuto dei dump richiesti, in ordine di nome.

        Dall'archivio si legge con una sola passata sequenziale: su un ``.tar.gz``
        l'accesso casuale costringerebbe a decomprimere dall'inizio a ogni
        membro, e su un giorno intero sarebbe quadratico.
        """
        insieme = set(voluti)
        if self.cartella.is_dir():
            for nome in sorted(insieme):
                percorso = self.cartella / nome
                if percorso.is_file():
                    yield nome, percorso.read_bytes()
            return
        if not self._da_tar:
            return
        trovati: dict[str, bytes] = {}
        with tarfile.open(self.archivio, "r|gz") as tar:
            for membro in tar:
                if not membro.isfile() or not membro.name.endswith(".pb"):
                    continue
                nome = Path(membro.name).name
                if nome not in insieme or "trip_updates" not in membro.name:
                    continue
                estratto = tar.extractfile(membro)
                if estratto is not None:
                    trovati[nome] = estratto.read()
        for nome in sorted(trovati):
            yield nome, trovati[nome]


def finestre_di_nomi(nomi: Sequence[str], quante: int, per_finestra: int) -> list[list[str]]:
    """Blocchi di dump CONSECUTIVI distribuiti sulla giornata.

    Consecutivi e non sparsi perche' il filtro al momento del passaggio ha
    bisogno di vedere una fermata comparire e sparire: con dump scelti a caso la
    sparizione non sarebbe osservabile. Distribuiti sulla giornata perche' una
    finestra sola confonde l'ora programmata con l'anticipo della previsione, che
    e' l'errore che questo script esiste per evitare.
    """
    if len(nomi) < per_finestra:
        return [list(nomi)] if nomi else []
    passo = max(1, (len(nomi) - per_finestra) // max(1, quante - 1))
    finestre = []
    for k in range(quante):
        inizio = min(k * passo, len(nomi) - per_finestra)
        finestre.append(list(nomi[inizio:inizio + per_finestra]))
    return finestre


def leggi_finestra(dumps: Sequence[tuple[str, bytes]], orari: dict) -> tuple[pd.DataFrame, dict, int, int]:
    """Estrae le osservazioni di un blocco di dump, senza deduplicarle."""
    righe = []
    corse_per_dump: list[set[str]] = []
    ultimo_indice: dict[tuple[str, int], int] = {}
    saltate = 0
    coppie_per_data: dict[tuple[str, int], set[str]] = defaultdict(set)

    for i, (_nome, contenuto) in enumerate(dumps):
        messaggio = pb.FeedMessage()
        try:
            messaggio.ParseFromString(contenuto)
        except Exception:
            corse_per_dump.append(set())
            continue
        ts = int(messaggio.header.timestamp)
        presenti: set[str] = set()
        for entita in messaggio.entity:
            if not entita.HasField("trip_update"):
                continue
            tu = entita.trip_update
            trip = tu.trip.trip_id
            presenti.add(trip)
            grezza = tu.trip.start_date.strip() if tu.trip.start_date else ""
            sd = (
                f"{grezza[:4]}-{grezza[4:6]}-{grezza[6:]}"
                if len(grezza) == 8 and grezza.isdigit()
                else ""
            )
            for tappa in tu.stop_time_update:
                if tappa.HasField("schedule_relationship") and tappa.schedule_relationship == 2:
                    saltate += 1
                    continue
                evento = (
                    tappa.arrival
                    if tappa.HasField("arrival")
                    else (tappa.departure if tappa.HasField("departure") else None)
                )
                if evento is None:
                    continue
                seq = int(tappa.stop_sequence)
                if sd:
                    coppie_per_data[(trip, seq)].add(sd)
                prog = orari.get(sd, {}).get((trip, seq))
                if prog is None:
                    continue
                if evento.HasField("delay"):
                    rit = int(evento.delay)
                elif evento.HasField("time"):
                    rit = int(evento.time) - prog
                else:
                    continue
                righe.append((trip, seq, ts, prog, rit, prog + rit, i))
                ultimo_indice[(trip, seq)] = i
        corse_per_dump.append(presenti)

    d = pd.DataFrame(righe, columns=["trip", "seq", "ts", "prog", "rit", "previsto", "dump"])
    collisioni = sum(1 for v in coppie_per_data.values() if len(v) > 1)
    return d, {"ultimo": ultimo_indice, "corse": corse_per_dump}, saltate, collisioni


def analizza_dump(citta: str, giorno: date, quante: int, per_finestra: int,
                  cartella_rt: Path, cartella_gtfs: Path) -> None:
    sorgente = SorgenteDump(cartella_rt / citta / giorno.isoformat())
    if not sorgente.disponibile():
        print(f"  [{citta}] nessun dump: ne' cartella ne' archivio in "
              f"{cartella_rt / citta / giorno.isoformat()}")
        return
    nomi = sorgente.nomi()
    if not nomi:
        print(f"  [{citta}] {sorgente.origine}: nessun dump di trip_updates")
        return
    finestre = finestre_di_nomi(nomi, quante, per_finestra)
    print(f"\n  [{citta}] {sorgente.origine}: {len(nomi):,} dump disponibili, "
          f"{len(finestre)} finestre da {per_finestra}")

    # Orari statici, per data di servizio, caricati una volta sola. Anche il
    # giorno precedente: le corse notturne ancora in circolazione dopo la
    # mezzanotte portano la data di servizio del giorno prima.
    precedente = date.fromordinal(giorno.toordinal() - 1)
    orari: dict[str, dict] = {}
    for sd in (giorno.isoformat(), precedente.isoformat()):
        try:
            programmato, _ = carica_orario(citta, sd, cartella_gtfs)
            orari[sd] = {
                k: int(istante_di_servizio(date.fromisoformat(sd), v[1], FUSO).timestamp())
                for k, v in programmato.items()
            }
        except Exception as errore:
            print(f"  [{citta}] orario non caricabile per {sd}: {errore}")

    # Dall'archivio conviene una passata sola per tutte le finestre insieme.
    voluti = [n for finestra in finestre for n in finestra]
    contenuti = dict(sorgente.leggi(voluti))

    pezzi, saltate_tot, collisioni_tot, passate = [], 0, 0, []
    for finestra in finestre:
        blocco = [(n, contenuti[n]) for n in finestra if n in contenuti]
        if not blocco:
            continue
        d, stato, saltate, collisioni = leggi_finestra(blocco, orari)
        saltate_tot += saltate
        collisioni_tot += collisioni
        if d.empty:
            continue
        pezzi.append(d)
        ultimo, corse = stato["ultimo"], stato["corse"]
        for (trip, seq), i in ultimo.items():
            if i < len(blocco) - 1 and any(trip in corse[j] for j in range(i + 1, len(blocco))):
                riga = d[(d.trip == trip) & (d.seq == seq) & (d.dump == i)]
                if len(riga):
                    passate.append(riga.iloc[0])

    if not pezzi:
        print(f"  [{citta}] nessuna osservazione utilizzabile")
        return
    d = pd.concat(pezzi, ignore_index=True)
    d["anticipo"] = d.previsto - d.ts
    d["ora"] = pd.to_datetime(d.prog, unit="s", utc=True).dt.tz_convert(FUSO).dt.hour
    f = pd.DataFrame(passate)
    if not f.empty:
        f["ora"] = pd.to_datetime(f.prog, unit="s", utc=True).dt.tz_convert(FUSO).dt.hour

    print(f"  [{citta}] {len(d):,} osservazioni, {saltate_tot:,} SKIPPED escluse")

    print(f"\n    --- 2. Coppie (corsa, fermata) con piu' di una data di servizio ---")
    print(f"    collisioni nelle finestre esaminate: {collisioni_tot:,}")
    print(f"    (ogni collisione e' una riga soppressa: la chiave di deduplica")
    print(f"     non contiene la data di servizio)")

    print(f"\n    --- 4. Anticipo con cui la previsione e' emessa ---")
    a = d.anticipo
    print(f"    mediana {a.median()/60:>6.1f} min | q1 {a.quantile(.25)/60:>6.1f} | "
          f"q3 {a.quantile(.75)/60:>6.1f} | max {a.max()/60:>6.0f} min  (n={len(a):,})")
    # Un anticipo di molte ore non e' una previsione lontana: e' l'istante di
    # passaggio calcolato su un ritardo enorme, quindi la stessa anomalia del
    # quadro 1-ter vista da un altro lato. Si verifica invece di supporlo.
    estremi = d[d.anticipo > 6 * 3600]
    if len(estremi):
        print(f"    righe con anticipo oltre 6 h: {len(estremi):,} ({len(estremi)/len(d):.3%}) "
              f"su {estremi.trip.nunique():,} corse")
        print(f"      loro ritardo: mediana {estremi.rit.median():,.0f} s, "
              f"quota con |ritardo| > 1 h: {(estremi.rit.abs() > 3600).mean():.1%}")
        print(f"      (quota alta = l'anticipo estremo E' il ritardo estremo, non una previsione)")
    else:
        print(f"    nessuna riga con anticipo oltre 6 h")

    print(f"\n    --- 5. Ritardo per anticipo, CONTROLLANDO per l'ora programmata ---")
    print(f"    {'ora':>4} " + " ".join(f"{et:>14}" for _, _, et in FASCE_ANTICIPO))
    for ora in sorted(d.ora.unique()):
        blocco = d[d.ora == ora]
        celle = []
        for lo, hi, _ in FASCE_ANTICIPO:
            s = blocco[(blocco.anticipo > lo) & (blocco.anticipo <= hi)]
            celle.append(f"{_mediana(s.rit.values):>7}({len(s):>6,})" if len(s) else f"{'-':>14}")
        print(f"    {ora:>4} " + " ".join(celle))
    print(f"    Se dentro una stessa riga la mediana NON varia con l'anticipo,")
    print(f"    l'ottimismo delle previsioni lontane e' escluso.")

    print(f"\n    --- 6. Filtro al momento del passaggio ---")
    if f.empty:
        print("    nessuna fermata osservata sparire mentre la corsa era ancora nel feed")
        return
    print(f"    righe attuali {len(d):>9,}  mediana {d.rit.median():>7.0f} s")
    print(f"    righe filtrate {len(f):>8,} ({len(f)/len(d):.2%})  mediana {f.rit.median():>7.0f} s")
    print(f"    {'ora':>4} {'righe att.':>11} {'med att.':>9} | {'righe filt.':>12} {'med filt.':>10}")
    for ora in sorted(set(d.ora) | set(f.ora)):
        bb, ff = d[d.ora == ora], f[f.ora == ora]
        print(f"    {ora:>4} {len(bb):>11,} {_mediana(bb.rit.values):>9} | "
              f"{len(ff):>12,} {_mediana(ff.rit.values):>10}")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--giorno", required=True, help="data di servizio, per esempio 2026-08-28")
    parser.add_argument("--citta", nargs="*", default=list(CITTA))
    parser.add_argument("--finestre", type=int, default=6,
                        help="blocchi di dump consecutivi distribuiti sulla giornata")
    parser.add_argument("--dump-per-finestra", type=int, default=20)
    parser.add_argument("--radice", type=Path, default=RADICE)
    argomenti = parser.parse_args(argv)

    giorno = date.fromisoformat(argomenti.giorno)
    cartella_gtfs = argomenti.radice / "data" / "raw" / "gtfs"
    cartella_rt = argomenti.radice / "data" / "raw" / "rt"
    cartella_pq = argomenti.radice / "data" / "processed" / "osservazioni"

    print("=" * 78)
    print(f"DIAGNOSI DEL CONSOLIDAMENTO - giorno {giorno}")
    print("Sola lettura: nessun file viene modificato.")
    print("=" * 78)

    print("\n" + "-" * 78)
    print("PARTE A - dai parquet consolidati")
    print("-" * 78)
    for citta in argomenti.citta:
        analizza_parquet(cartella_pq / citta / f"{giorno.isoformat()}.parquet",
                         citta, cartella_gtfs)

    print("\n" + "-" * 78)
    print("PARTE B - dai dump grezzi, a campione stratificato sulla giornata")
    print("-" * 78)
    for citta in argomenti.citta:
        analizza_dump(citta, giorno, argomenti.finestre, argomenti.dump_per_finestra,
                      cartella_rt, cartella_gtfs)

    print("\n" + "=" * 78)
    print("Nessuna tabella qui e' una conclusione: le basi sottili vanno lette")
    print("come indicazione, non come stima.")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
