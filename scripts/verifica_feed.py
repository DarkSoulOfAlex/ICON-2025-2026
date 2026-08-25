"""Verifica una tantum di tutti i feed configurati.

Scarica una volta ciascun feed di ciascuna citta', lo decodifica e riporta cosa
contiene davvero. Serve a rispondere, prima di impegnare settimane di raccolta,
all'unica domanda che conta su un feed real-time: contiene gli scostamenti fra
orario programmato e orario osservato?

Il conteggio viene rifatto qui camminando sul messaggio decodificato invece di
riusare il riepilogo del collector: e' una verifica indipendente, e se i due
numeri divergessero sarebbe il segnale che il parser del collector sta contando
qualcosa di diverso da quello che crediamo.

Uso:
    python scripts/verifica_feed.py
    python scripts/verifica_feed.py --citta roma
    python scripts/verifica_feed.py --config config.yaml
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

RADICE = Path(__file__).resolve().parent.parent
if str(RADICE) not in sys.path:
    sys.path.insert(0, str(RADICE))

from google.transit import gtfs_realtime_pb2  # noqa: E402

from src.collector.poll_realtime import (  # noqa: E402
    ConfigCitta,
    ErroreConfigurazione,
    FeedNonValido,
    analizza_feed,
    carica_configurazione,
    scarica,
)

LARGHEZZA = 78


def _titolo(testo: str) -> str:
    return f"\n{'=' * LARGHEZZA}\n{testo}\n{'=' * LARGHEZZA}"


def conta_ritardi(dati: bytes) -> dict[str, int]:
    """Conta entita' e passaggi con scostamento orario, camminando sul messaggio.

    Distingue il campo ``delay`` dall'orario assoluto ``time`` perche' non sono
    equivalenti per il progetto: con ``delay`` il ritardo e' gia' pronto, con il
    solo ``time`` va ricavato per differenza rispetto all'orario programmato del
    GTFS statico, e quindi quella citta' e' inutilizzabile finche' non abbiamo
    anche l'archivio statico del giorno.
    """
    messaggio = gtfs_realtime_pb2.FeedMessage()
    messaggio.ParseFromString(dati)

    conteggi = {
        "entita": len(messaggio.entity),
        "con_trip_update": 0,
        "con_vehicle": 0,
        "con_alert": 0,
        "stop_time_update": 0,
        "stu_con_delay": 0,
        "stu_con_time": 0,
        "stu_senza_nulla": 0,
    }
    for entita in messaggio.entity:
        if entita.HasField("vehicle"):
            conteggi["con_vehicle"] += 1
        if entita.HasField("alert"):
            conteggi["con_alert"] += 1
        if not entita.HasField("trip_update"):
            continue
        conteggi["con_trip_update"] += 1
        for tappa in entita.trip_update.stop_time_update:
            conteggi["stop_time_update"] += 1
            ha_delay = ha_time = False
            for evento in ("arrival", "departure"):
                if tappa.HasField(evento):
                    dettaglio = getattr(tappa, evento)
                    ha_delay = ha_delay or dettaglio.HasField("delay")
                    ha_time = ha_time or dettaglio.HasField("time")
            conteggi["stu_con_delay"] += int(ha_delay)
            conteggi["stu_con_time"] += int(ha_time)
            conteggi["stu_senza_nulla"] += int(not ha_delay and not ha_time)
    return conteggi


def primo_esempio(dati: bytes, righe_max: int = 26) -> str:
    """Prima entita' con un TripUpdate, stampata nella forma testuale di protobuf.

    Un esempio decodificato vale piu' di qualunque conteggio quando si tratta di
    capire come una specifica agenzia popola i campi: ogni implementazione del
    formato ha le sue abitudini.
    """
    messaggio = gtfs_realtime_pb2.FeedMessage()
    messaggio.ParseFromString(dati)
    for entita in messaggio.entity:
        if entita.HasField("trip_update"):
            testo = str(entita).rstrip().splitlines()
            if len(testo) > righe_max:
                testo = testo[:righe_max] + [f"... (altre {len(str(entita).splitlines()) - righe_max} righe)"]
            return "\n".join("    " + riga for riga in testo)
    for entita in messaggio.entity:
        testo = str(entita).rstrip().splitlines()[:righe_max]
        return "\n".join("    " + riga for riga in testo)
    return "    (nessuna entita' nel feed)"


def verifica_indirizzo(
    etichetta: str, url: str, intestazioni: dict[str, str], timeout: float
) -> bool:
    """Scarica e analizza un singolo feed. Restituisce True se e' utilizzabile."""
    print(f"\n--- {etichetta}")
    print(f"    {url}")
    if url.lower().startswith("http://"):
        print("    NOTA: indirizzo in HTTP, non cifrato.")

    risultato = scarica(url, intestazioni, timeout, tentativi_max=2, backoff_base=1.0, backoff_max=4.0)
    if not risultato.ok or risultato.dati is None:
        print(f"    FALLITO ({risultato.esito}): {risultato.dettaglio}")
        return False

    print(f"    HTTP {risultato.stato_http}, {len(risultato.dati):,} byte")

    try:
        riepilogo = analizza_feed(risultato.dati)
    except FeedNonValido as errore:
        anteprima = risultato.dati[:150].decode("utf-8", errors="replace").replace("\n", " ")
        print(f"    NON e' un feed GTFS Real-Time valido: {errore}")
        print(f"    primi byte: {anteprima!r}")
        return False

    conteggi = conta_ritardi(risultato.dati)
    print(f"    versione GTFS-RT            : {riepilogo.versione}")
    if riepilogo.timestamp_feed:
        istante = datetime.fromtimestamp(riepilogo.timestamp_feed, tz=timezone.utc)
        eta = (datetime.now(timezone.utc) - istante).total_seconds()
        print(f"    timestamp del feed          : {istante.isoformat(timespec='seconds')} ({eta:.0f} s fa)")
    else:
        print("    timestamp del feed          : ASSENTE (la deduplica non potra' funzionare)")

    print(f"    entita' totali              : {conteggi['entita']:,}")
    print(f"      con trip_update           : {conteggi['con_trip_update']:,}")
    print(f"      con vehicle               : {conteggi['con_vehicle']:,}")
    print(f"      con alert                 : {conteggi['con_alert']:,}")
    print(f"    stop_time_update totali     : {conteggi['stop_time_update']:,}")
    print(f"      con campo 'delay'         : {conteggi['stu_con_delay']:,}")
    print(f"      con orario assoluto 'time': {conteggi['stu_con_time']:,}")
    print(f"      senza ne' l'uno ne' l'altro: {conteggi['stu_senza_nulla']:,}")

    print("    esempio decodificato:")
    print(primo_esempio(risultato.dati))

    return _giudizio(etichetta, conteggi)


def _giudizio(tipo_feed: str, conteggi: dict[str, int]) -> bool:
    """Giudizio adeguato al tipo di feed che ci si aspetta di aver interrogato.

    Un ``vehicle_positions`` non contiene TripUpdate per definizione: giudicarlo
    con lo stesso metro dei ``trip_updates`` lo dichiarerebbe inutilizzabile
    proprio quando funziona come deve. Il criterio giusto e' che ogni feed
    contenga il tipo di entita' per cui lo interroghiamo.
    """
    if tipo_feed == "vehicle_positions":
        if conteggi["con_vehicle"] == 0:
            print("    GIUDIZIO: nessuna posizione di veicolo. Il feed non serve a nulla.")
            return False
        print(
            "    GIUDIZIO: utilizzabile come ridondanza. Non contiene ritardi (ne' deve):\n"
            "              serve a ricostruire i passaggi se i trip_updates si rivelassero poveri."
        )
        return True

    if conteggi["con_trip_update"] == 0:
        print("    GIUDIZIO: nessun TripUpdate. Non e' una fonte di ritardi.")
        return False
    if conteggi["stu_con_delay"] == 0 and conteggi["stu_con_time"] == 0:
        print("    GIUDIZIO: TripUpdate presenti ma senza scostamenti orari. Inutilizzabile.")
        return False
    if conteggi["stu_con_delay"] > 0:
        print("    GIUDIZIO: utilizzabile, i ritardi sono gia' espliciti nel campo 'delay'.")
    else:
        print(
            "    GIUDIZIO: utilizzabile, ma i ritardi vanno ricavati per differenza dagli "
            "orari\n              programmati: serve per forza l'archivio GTFS statico del giorno."
        )
    return True


def verifica_citta(citta: ConfigCitta, user_agent: str, timeout: float) -> dict[str, bool]:
    print(_titolo(f"CITTA': {citta.nome}   (fuso {citta.fuso_orario})"))
    if not citta.attiva:
        print("  citta' disattivata in configurazione: la verifico comunque.")
    if not citta.url_gtfs_statico:
        print(
            "  ATTENZIONE: nessun orario statico configurato. Senza, i ritardi raccolti\n"
            "  non saranno riconducibili a un orario programmato e la citta' sara'\n"
            "  inutilizzabile in Fase 3."
        )

    intestazioni = {"User-Agent": user_agent, **citta.intestazioni_http}
    esiti: dict[str, bool] = {}

    if citta.url_gtfs_statico:
        esiti["gtfs_statico"] = _verifica_statico(citta, intestazioni, timeout)
    for tipo_feed, url in sorted(citta.feed_rt.items()):
        esiti[tipo_feed] = verifica_indirizzo(tipo_feed, url, intestazioni, timeout)
    return esiti


def _verifica_statico(citta: ConfigCitta, intestazioni: dict[str, str], timeout: float) -> bool:
    """Controlla che l'orario statico sia raggiungibile, senza scaricarlo tutto.

    Se l'agenzia pubblica il .md5 basta quello: sono cinquanta byte e dicono
    comunque che l'indirizzo funziona.
    """
    print("\n--- gtfs_statico")
    print(f"    {citta.url_gtfs_statico}")
    if citta.url_gtfs_statico_md5:
        risultato = scarica(
            citta.url_gtfs_statico_md5, intestazioni, timeout, 2, 1.0, 4.0
        )
        if risultato.ok and risultato.dati is not None:
            print(f"    .md5 raggiungibile: {risultato.dati.decode('ascii', 'replace').strip()}")
            return True
        print(f"    .md5 NON raggiungibile: {risultato.dettaglio}")
        return False
    print("    nessun .md5 configurato: l'archivio verra' scaricato per intero ogni giorno.")
    return True


def main(argv: Sequence[str] | None = None) -> int:
    analizzatore = argparse.ArgumentParser(
        prog="python scripts/verifica_feed.py",
        description="Scarica una volta ogni feed configurato e riporta cosa contiene.",
    )
    analizzatore.add_argument("--config", type=Path, default=RADICE / "config.yaml")
    analizzatore.add_argument("--citta", metavar="NOME", help="verifica solo questa citta'")
    argomenti = analizzatore.parse_args(argv)

    try:
        config = carica_configurazione(argomenti.config)
    except ErroreConfigurazione as errore:
        print(f"\n{errore}\n", file=sys.stderr)
        return 2

    citta = list(config.citta)
    if argomenti.citta:
        citta = [c for c in citta if c.nome == argomenti.citta]
        if not citta:
            print(f"Citta' '{argomenti.citta}' non presente in configurazione.", file=sys.stderr)
            return 2

    tutti: dict[str, dict[str, bool]] = {}
    for singola in citta:
        tutti[singola.nome] = verifica_citta(
            singola, config.raccolta.user_agent, config.raccolta.timeout_richiesta_secondi
        )

    print(_titolo("RIEPILOGO"))
    problemi = 0
    for nome, esiti in tutti.items():
        for feed, ok in sorted(esiti.items()):
            marcatore = "OK " if ok else "KO "
            print(f"  {marcatore} {nome} / {feed}")
            problemi += int(not ok)
    print()
    if problemi:
        print(f"{problemi} feed non utilizzabili: vanno risolti prima di lasciar girare la raccolta.")
    else:
        print("Tutti i feed configurati sono utilizzabili.")
    return 1 if problemi else 0


if __name__ == "__main__":
    raise SystemExit(main())
