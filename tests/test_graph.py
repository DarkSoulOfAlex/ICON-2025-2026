"""Test del grafo tempo-espanso e della ricerca.

Coprono le tre cose che possono sbagliare senza sollevare nulla:

* l'A* che restituisce un itinerario non ottimo perche' l'euristica sovrastima;
* l'euristica non ammissibile, che non fa fallire niente e degrada in silenzio la
  qualita' delle risposte;
* la dominanza di Pareto sbagliata, che produce una frontiera con soluzioni
  dominate oppure senza soluzioni che avrebbero dovuto esserci.

La rete di prova e' costruita a mano perche' i risultati siano verificabili senza
eseguire il codice.
"""

from __future__ import annotations

import random
import zipfile
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from src.graph.search import (
    Etichetta,
    cerca_frontiera_pareto,
    cerca_primo_arrivo,
    euristica_geografica,
)
from src.graph.time_expanded import ATerra, costruisci, velocita_massima
from src.gtfs.loader import carica_archivio
from tests.test_gtfs import GIOCATTOLO

GIORNO = date(2026, 8, 25)  # martedi': il servizio FERIALE del giocattolo

# Percorso del parquet dei trasbordi di ogni grafo costruito dalla fixture: serve
# ai test che devono ricostruire lo stesso grafo con una finestra diversa.
_PERCORSI: dict[int, Path] = {}


def _percorso_trasbordi(grafo) -> Path:
    return _PERCORSI[id(grafo)]


@pytest.fixture
def rete(tmp_path: Path):
    """GTFS giocattolo piu' i trasbordi che la base di conoscenza deriverebbe."""
    archivio_zip = tmp_path / "gtfs.zip"
    with zipfile.ZipFile(archivio_zip, "w") as zip_gtfs:
        for nome, testo in GIOCATTOLO.items():
            zip_gtfs.writestr(nome, testo)
    archivio = carica_archivio(archivio_zip, con_stop_times=True)

    # A1, A2 e B sono a poche decine di metri: sono i trasbordi che la Fase 1
    # deriva su questa rete.
    coppie = [("A1", "A2"), ("A2", "A1"), ("A1", "B"), ("B", "A1"), ("A2", "B"), ("B", "A2")]
    trasbordi = pd.DataFrame(
        [
            {"from_stop_id": a, "to_stop_id": b, "min_transfer_time": 180,
             "a_piedi": True, "accessibile": True, "utile": True}
            for a, b in coppie
        ]
    )
    percorso = tmp_path / "transfers.parquet"
    trasbordi.to_parquet(percorso, index=False)

    inizio = int(datetime(2026, 8, 25, 7, 30, tzinfo=ZoneInfo("Europe/Rome")).timestamp())
    grafo = costruisci(archivio, "prova", GIORNO, inizio, 180, percorso_trasbordi=percorso)
    _PERCORSI[id(grafo)] = percorso
    return grafo, inizio, archivio


def _esaustiva(grafo, origine: str, destinazione: str, partenza: int) -> int | None:
    """Primo orario di arrivo per esplorazione esaustiva, senza euristiche.

    E' volutamente ingenua: espande tutto quello che puo' e tiene il minimo. Non
    e' efficiente, ma non ha nulla da cui possa dipendere un errore comune con
    l'implementazione sotto esame, il che e' l'unico requisito di un oracolo.
    """
    partenza_idx = grafo.indice_fermata[origine]
    arrivo_idx = grafo.indice_fermata[destinazione]
    da_visitare = [ATerra(partenza_idx, partenza, 0)]
    visti: set = set()
    migliore: int | None = None
    for _ in range(200_000):
        if not da_visitare:
            break
        stato = da_visitare.pop()
        chiave = (type(stato).__name__, getattr(stato, "evento", None),
                  getattr(stato, "fermata", None), getattr(stato, "istante", None), stato.cambi)
        if chiave in visti:
            continue
        visti.add(chiave)
        if isinstance(stato, ATerra) and stato.fermata == arrivo_idx:
            migliore = stato.istante if migliore is None else min(migliore, stato.istante)
            continue
        for successivo, arrivo in grafo.successori(stato):
            if arrivo <= grafo.fine and successivo.cambi <= 4:
                da_visitare.append(successivo)
    return migliore


# =============================================================================
# Correttezza dell'A*
# =============================================================================


def test_astar_trova_lo_stesso_arrivo_della_ricerca_esaustiva(rete) -> None:
    """Se l'euristica sovrastimasse, A* restituirebbe un ottimo peggiore in silenzio."""
    grafo, inizio, archivio = rete
    velocita = velocita_massima(archivio)["massimo_m_s"]
    for origine, destinazione in (("A1", "C"), ("A2", "D"), ("B", "C")):
        esito = cerca_primo_arrivo(grafo, origine, destinazione, inizio, velocita)
        atteso = _esaustiva(grafo, origine, destinazione, inizio)
        assert esito.trovato == (atteso is not None), (origine, destinazione)
        if atteso is not None:
            assert esito.orario_arrivo == atteso, (origine, destinazione)


def test_astar_e_dijkstra_concordano_sempre(rete) -> None:
    grafo, inizio, archivio = rete
    velocita = velocita_massima(archivio)["massimo_m_s"]
    for origine, destinazione in (("A1", "C"), ("A2", "D"), ("B", "C"), ("A1", "D")):
        con = cerca_primo_arrivo(grafo, origine, destinazione, inizio, velocita, True)
        senza = cerca_primo_arrivo(grafo, origine, destinazione, inizio, velocita, False)
        assert con.trovato == senza.trovato
        assert con.orario_arrivo == senza.orario_arrivo


def test_una_destinazione_irraggiungibile_non_viene_inventata(rete) -> None:
    """C e D non sono collegate fra loro da nessuna corsa del giocattolo."""
    grafo, inizio, archivio = rete
    velocita = velocita_massima(archivio)["massimo_m_s"]
    assert not cerca_primo_arrivo(grafo, "C", "D", inizio, velocita).trovato


def test_restare_a_bordo_non_conta_come_cambio(rete) -> None:
    """T1 va da A1 a C passando per B senza che si debba scendere."""
    grafo, inizio, archivio = rete
    velocita = velocita_massima(archivio)["massimo_m_s"]
    esito = cerca_primo_arrivo(grafo, "A1", "C", inizio, velocita)
    assert esito.trovato
    assert esito.cambi == 1, "una sola salita: A1 -> C e' servita da una corsa unica"


# =============================================================================
# Ammissibilita' dell'euristica
# =============================================================================


def test_l_euristica_non_sovrastima_mai_il_costo_residuo(rete) -> None:
    """Verifica per campionamento della proprieta' su cui poggia l'ottimalita'.

    Un'euristica non ammissibile non solleva nulla e non rallenta nulla: fa solo
    restituire itinerari peggiori. E' esattamente il genere di difetto che i test
    di questo progetto devono intercettare.
    """
    grafo, inizio, archivio = rete
    velocita = velocita_massima(archivio)["massimo_m_s"]
    destinazione = grafo.indice_fermata["C"]
    h = euristica_geografica(grafo, destinazione, velocita)

    generatore = random.Random(7)
    fermate_servite = [f for f, v in grafo.partenze_per_fermata.items() if v.size]
    controllati = 0
    for _ in range(60):
        fermata = generatore.choice(fermate_servite)
        istante = generatore.randrange(inizio, grafo.fine)
        stato = ATerra(fermata, istante, 0)
        reale = _esaustiva(grafo, grafo.fermate[fermata], "C", istante)
        if reale is None:
            continue
        controllati += 1
        assert h(stato) <= (reale - istante) + 1e-6, (
            f"euristica {h(stato):.1f} s maggiore del costo reale {(reale - istante):.1f} s"
        )
    assert controllati >= 5, "campione troppo piccolo per dire qualcosa"


def test_l_euristica_e_nulla_a_destinazione(rete) -> None:
    grafo, inizio, archivio = rete
    destinazione = grafo.indice_fermata["C"]
    h = euristica_geografica(grafo, destinazione, 10.0)
    assert h(ATerra(destinazione, inizio, 0)) == pytest.approx(0.0)


# =============================================================================
# Dominanza di Pareto
# =============================================================================


def test_la_dominanza_richiede_un_miglioramento_stretto() -> None:
    """Senza la disuguaglianza stretta due etichette uguali si escluderebbero."""
    una = Etichetta(1000, 2, 300)
    assert not una.domina(Etichetta(1000, 2, 300))
    assert una.domina(Etichetta(1001, 2, 300))
    assert una.domina(Etichetta(1000, 3, 300))
    assert una.domina(Etichetta(1000, 2, 301))


def test_nessun_criterio_da_solo_decide_la_dominanza() -> None:
    """Arrivare prima ma con piu' cambi non domina, ed e' il cuore del problema."""
    presto_scomodo = Etichetta(1000, 3, 0)
    tardi_comodo = Etichetta(1200, 1, 0)
    assert not presto_scomodo.domina(tardi_comodo)
    assert not tardi_comodo.domina(presto_scomodo)


def test_la_frontiera_non_contiene_soluzioni_dominate(rete) -> None:
    grafo, inizio, _ = rete
    esito = cerca_frontiera_pareto(grafo, "A1", "C", inizio)
    for una in esito.frontiera:
        for altra in esito.frontiera:
            if una is not altra:
                assert not altra.domina(una), f"{altra} domina {una}"


def test_la_frontiera_contiene_l_ottimo_mono_criterio(rete) -> None:
    """Il primo arrivo possibile deve comparire fra le soluzioni non dominate.

    Se non ci fosse, la ricerca multi-criterio starebbe perdendo soluzioni, cosa
    che nessun controllo di dominanza rivelerebbe.
    """
    grafo, inizio, archivio = rete
    velocita = velocita_massima(archivio)["massimo_m_s"]
    mono = cerca_primo_arrivo(grafo, "A1", "C", inizio, velocita)
    pareto = cerca_frontiera_pareto(grafo, "A1", "C", inizio)
    assert mono.trovato and pareto.frontiera
    assert min(e.orario_arrivo for e in pareto.frontiera) == mono.orario_arrivo


# =============================================================================
# Grafo
# =============================================================================


def test_dalla_finestra_non_si_sale_su_corse_fuori_orizzonte(rete) -> None:
    """L'indice delle partenze non deve contenere nulla oltre la fine.

    Se ci fosse, la ricerca proporrebbe di salire su una corsa che parte dopo
    l'orizzonte dichiarato, e l'itinerario restituito non sarebbe quello che il
    modello promette.
    """
    grafo, _inizio, _archivio = rete
    assert grafo.n_eventi > 0
    for fermata, orari in grafo.partenze_orari.items():
        assert bool((orari <= grafo.fine).all()), fermata
        assert bool((orari >= grafo.inizio).all()), fermata


def test_una_finestra_piu_stretta_produce_un_grafo_piu_piccolo(rete) -> None:
    grafo, inizio, archivio = rete
    stretto = costruisci(archivio, "prova", GIORNO, inizio, 30,
                         percorso_trasbordi=_percorso_trasbordi(grafo))
    assert stretto.n_eventi <= grafo.n_eventi


def test_la_velocita_massima_si_misura_sull_orario(rete) -> None:
    _grafo, _inizio, archivio = rete
    misura = velocita_massima(archivio)
    assert misura["massimo_m_s"] > 0
    assert misura["p50"] <= misura["p99"] <= misura["massimo_m_s"]
    assert misura["archi"] > 0
