"""Test dell'indice delle revisioni dell'orario statico.

E' la funzione che il consolidamento notturno usa per risalire, data una data di
servizio, all'archivio GTFS con cui interpretarla. Sbagliarla non produce
eccezioni: produce orari programmati presi dalla revisione sbagliata, quindi
ritardi falsi che sembrano un problema dei dati.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.gtfs.indice_statico import carica_indice, indice_vuoto, salva_indice, versione_valida


def test_la_versione_valida_e_quella_del_giorno_stesso() -> None:
    indice = {"giorni": {"2026-08-25": {"file": "a.zip"}, "2026-08-26": {"file": "b.zip"}}}
    assert versione_valida(indice, "2026-08-26")["file"] == "b.zip"


def test_senza_voce_esplicita_vale_l_ultima_precedente() -> None:
    """Se il collector era fermo, l'orario in vigore resta quello dell'ultima revisione."""
    indice = {"giorni": {"2026-08-20": {"file": "a.zip"}, "2026-08-26": {"file": "b.zip"}}}
    assert versione_valida(indice, "2026-08-23")["file"] == "a.zip"


def test_prima_della_prima_revisione_non_c_e_nulla() -> None:
    indice = {"giorni": {"2026-08-20": {"file": "a.zip"}}}
    assert versione_valida(indice, "2026-08-19") is None

# =============================================================================
# Persistenza
# =============================================================================


def test_l_indice_sopravvive_al_giro_su_disco(tmp_path: Path) -> None:
    percorso = tmp_path / "index.json"
    indice = indice_vuoto("roma")
    indice["giorni"]["2026-08-25"] = {"file": "2026-08-25.zip", "md5": "abc", "origine": "scaricato"}
    salva_indice(percorso, indice)
    assert carica_indice(percorso, "roma") == indice


def test_un_indice_illeggibile_non_ferma_la_raccolta(tmp_path: Path) -> None:
    """Meglio riscaricare l'orario che interrompere il real-time, che e' irripetibile."""
    percorso = tmp_path / "index.json"
    percorso.write_text("{rotto", encoding="utf-8")
    assert carica_indice(percorso, "roma") == indice_vuoto("roma")


def test_un_indice_inesistente_ne_produce_uno_vuoto(tmp_path: Path) -> None:
    assert carica_indice(tmp_path / "mai-scritto.json", "torino") == indice_vuoto("torino")
