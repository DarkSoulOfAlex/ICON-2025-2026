"""Indice delle revisioni dell'orario statico.

Ogni citta' ha un ``index.json`` che associa a ogni data di servizio la revisione
dell'orario GTFS in vigore quel giorno. Serve perche' gli identificativi di corsa
del feed real-time hanno senso solo rispetto alla versione dell'orario di quel
giorno, e l'orario di Roma cambia quasi quotidianamente: senza questa mappa, i
dump gia' raccolti diventerebbero impossibili da interpretare.

Il modulo sta sotto ``src/gtfs`` e non dentro il collector perche' lo usano
entrambi i lati del progetto: il collector lo scrive mentre archivia, il
consolidamento notturno lo legge per risalire agli orari programmati. Tenerlo qui
evita che il consolidamento debba importare l'intero collector per tre funzioni.

Non dipende da pandas: e' deliberato, cosi' resta utilizzabile anche dove pandas
non serve.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

log = logging.getLogger("gtfs.indice")


def indice_vuoto(citta: str) -> dict[str, Any]:
    """Struttura iniziale di index.json.

    ``giorni`` mappa ogni data alla versione dell'orario valida quel giorno;
    ``versioni`` raccoglie le revisioni distinte, cosi' una revisione che ritorna
    identica non produce un secondo archivio.
    """
    return {"citta": citta, "aggiornato": None, "giorni": {}, "versioni": {}}


def carica_indice(percorso: Path, citta: str) -> dict[str, Any]:
    """Legge index.json, ripartendo da vuoto se e' illeggibile.

    Un indice corrotto non deve impedire la raccolta del real-time, che e'
    l'unico dato irripetibile: al peggio si riscarica l'orario statico, che e'
    sempre recuperabile.
    """
    if not percorso.is_file():
        return indice_vuoto(citta)
    try:
        indice = json.loads(percorso.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        log.warning("[%s] index.json illeggibile: ne creo uno nuovo.", citta)
        return indice_vuoto(citta)
    if not isinstance(indice, dict) or "giorni" not in indice:
        return indice_vuoto(citta)
    indice.setdefault("citta", citta)
    indice.setdefault("versioni", {})
    return indice


def salva_indice(percorso: Path, indice: dict[str, Any]) -> None:
    percorso.parent.mkdir(parents=True, exist_ok=True)
    percorso.write_text(
        json.dumps(indice, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8"
    )


def versione_valida(indice: dict[str, Any], data_locale: str) -> dict[str, Any] | None:
    """Versione dell'orario statico in vigore in una certa data di servizio.

    Se per quella data non c'e' una voce esplicita (per esempio perche' il
    collector era fermo), si ripiega sulla data precedente piu' vicina: l'orario
    in vigore resta quello finche' l'agenzia non ne pubblica uno nuovo. E' la
    funzione che la Fase 3 usera' per sapere con quale archivio interpretare i
    ``trip_id`` di un certo giorno.
    """
    giorni = indice.get("giorni") or {}
    if data_locale in giorni:
        return giorni[data_locale]
    precedenti = [data for data in giorni if data < data_locale]
    if not precedenti:
        return None
    return giorni[max(precedenti)]
