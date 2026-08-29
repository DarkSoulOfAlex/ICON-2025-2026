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
        columns=["service_date", "trip_id", "route_id", "stop_sequence",
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
            prog = pd.Timestamp(x.orario_programmato, unit="s", tz="UTC").tz_convert(FUSO)
            oss = pd.Timestamp(x.orario_osservato, unit="s", tz="UTC").tz_convert(FUSO)
            print(f"      servizio {x.service_date} corsa {x.trip_id} seq {x.stop_sequence:>3} "
                  f"prog {prog:%m-%d %H:%M} oss {oss:%m-%d %H:%M} ritardo {x.ritardo_secondi:,}")

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

    tabella_per_tipo(d, ore, citta, sorted(d.service_date.unique()), cartella_gtfs)
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


def tabella_per_tipo(d: pd.DataFrame, ore: pd.Series, citta: str,
                     date_servizio: Sequence[str], cartella_gtfs: Path) -> None:
    """Ritardo per ora e per tipo di veicolo.

    Serve a mettere alla prova la spiegazione del margine negli orari. Una linea
    in sede propria - metro, tram protetto - non incontra la congestione che il
    margine dovrebbe assorbire, quindi se il margine fosse davvero una risposta al
    traffico dovrebbe risultare piu' piccolo li' e piu' grande sulle linee di
    superficie nel traffico misto. Se invece fosse uguale ovunque, la spiegazione
    sarebbe un'altra.
    """
    print()
    print("    --- 3-bis. Ritardo per ora e per TIPO DI LINEA ---")
    mappa = tipi_di_linea(citta, date_servizio, cartella_gtfs)
    if not mappa:
        print("    tipi di linea non disponibili")
        return
    d = d.assign(ora=ore, tipo=d.route_id.map(mappa))
    noti = d[d.tipo.notna()]
    if noti.empty:
        print("    nessuna riga con tipo di linea riconosciuto")
        return
    presenti = sorted(noti.tipo.unique())
    etichette = [TIPI_LINEA.get(int(x), f"tipo {int(x)}") for x in presenti]
    print(f"    righe con tipo noto: {len(noti):,} su {len(d):,}")
    print(f"    {'ora':>4} " + " ".join(f"{e:>16}" for e in etichette))
    for ora in sorted(noti.ora.unique()):
        blocco = noti[noti.ora == ora]
        celle = []
        for tipo in presenti:
            s = blocco[blocco.tipo == tipo]
            celle.append(f"{_mediana(s.ritardo_secondi.values):>8}({len(s):>6,})"
                         if len(s) else f"{'-':>16}")
        print(f"    {ora:>4} " + " ".join(celle))
    print(f"    {'tutte':>4} " + " ".join(
        f"{_mediana(noti[noti.tipo == tipo].ritardo_secondi.values):>8}"
        f"({len(noti[noti.tipo == tipo]):>6,})" for tipo in presenti))


def corse_oltre_24h(citta: str, date_servizio: Iterable[str], cartella_gtfs: Path) -> set[str]:
    """Corse il cui orario statico supera le 24 ore, per le date indicate."""
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
