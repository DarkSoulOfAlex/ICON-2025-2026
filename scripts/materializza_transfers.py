"""Esegue la base di conoscenza sull'intera rete di ogni citta'.

Produce ``data/processed/transfers_<citta>.parquet``, che e' l'artefatto su cui
poggera' il grafo tempo-espanso della Fase 2, e riporta il costo dell'esecuzione
a piena scala. Quest'ultimo numero serve al documento: e' la misura reale, non
l'estrapolazione della curva di complessita'.

Uso:
    python scripts/materializza_transfers.py
    python scripts/materializza_transfers.py --citta torino
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from time import monotonic
from typing import Sequence

RADICE = Path(__file__).resolve().parent.parent
if str(RADICE) not in sys.path:
    sys.path.insert(0, str(RADICE))

from src.gtfs.loader import carica_archivio, fermate_fisiche  # noqa: E402
from src.kb.engine import ErroreKB, esegui, genera_fatti  # noqa: E402

CARTELLA_USCITA = RADICE / "data" / "processed"


def archivio_piu_recente(citta: str) -> Path:
    archivi = sorted((RADICE / "data" / "raw" / "gtfs" / citta).glob("*.zip"))
    if not archivi:
        raise SystemExit(f"Nessun archivio GTFS per '{citta}'.")
    return archivi[-1]


def materializza_citta(citta: str) -> None:
    percorso = archivio_piu_recente(citta)
    inizio = monotonic()
    archivio = carica_archivio(percorso, con_stop_times=True)
    fermate = fermate_fisiche(archivio.stops)
    print(
        f"\n=== {citta} ({percorso.name}) ===\n"
        f"  {len(fermate):,} fermate fisiche, archivio letto in {monotonic() - inizio:.0f}s",
        flush=True,
    )

    inizio = monotonic()
    fatti = genera_fatti(archivio)
    tempo_fatti = monotonic() - inizio
    print(f"  {fatti.n_fatti:,} fatti generati in {tempo_fatti:.0f}s: {dict(fatti.conteggi)}", flush=True)

    risultato = esegui(fatti)
    if not risultato.soddisfacibile:
        # Un vincolo ha rifiutato il modello: si rilancia senza vincoli per
        # poter almeno dire quanti trasbordi ci sarebbero stati, e si segnala.
        diagnosi = esegui(fatti, con_vincoli=False)
        raise ErroreKB(
            f"[{citta}] la base di conoscenza e' insoddisfacibile: un vincolo di integrita' "
            f"ha rifiutato il modello. Senza vincoli il modello esiste e contiene "
            f"{len(diagnosi.trasbordi):,} trasbordi, quindi il rifiuto viene da un vincolo e "
            "non da un errore nelle regole. Vanno ispezionati i dati della citta'."
        )

    print(
        f"  atomi {risultato.atomi:,} | grounding {risultato.tempo_grounding:.1f}s | "
        f"solving {risultato.tempo_solving:.2f}s | {len(risultato.trasbordi):,} trasbordi",
        flush=True,
    )
    tabella = risultato.trasbordi
    print(
        f"  di cui a piedi {int(tabella['a_piedi'].sum()):,}, "
        f"accessibili {int(tabella['accessibile'].sum()):,}, "
        f"utili {int(tabella['utile'].sum()):,}",
        flush=True,
    )

    CARTELLA_USCITA.mkdir(parents=True, exist_ok=True)
    destinazione = CARTELLA_USCITA / f"transfers_{citta}.parquet"
    tabella.to_parquet(destinazione, index=False)
    print(f"  scritto {destinazione.name} ({destinazione.stat().st_size / 1024:.0f} KB)", flush=True)


def main(argv: Sequence[str] | None = None) -> int:
    analizzatore = argparse.ArgumentParser(description=__doc__)
    analizzatore.add_argument("--citta", default="torino,roma")
    argomenti = analizzatore.parse_args(argv)
    for citta in (c.strip() for c in argomenti.citta.split(",")):
        materializza_citta(citta)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
