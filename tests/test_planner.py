"""Test della composizione delle probabilita' e delle strategie di scelta.

Coprono cio' che puo' sbagliare in silenzio: una probabilita' che non e' una
probabilita', due metodi di calcolo che divergono senza dirlo, una catena che
perde massa, e una baseline che non risponde nei casi difficili.
"""

from __future__ import annotations

import numpy as np
import pytest

from src.delays.interfaccia import Distribuzione, ModelloSintetico, Tratta
from src.planner import robust
from src.planner.baselines import margine_fisso, meno_cambi, piu_veloce
from src.planner.robust import (
    Candidato,
    ErrorePianificatore,
    Itinerario,
    Salita,
    Tappa,
    pianifica_robusto,
    probabilita_convoluzione,
    probabilita_montecarlo,
)

BASE = 1_800_000_000


def _tappa(partenza: int, arrivo: int, minimo: int = 0, linea: str = "L1",
           quante: int = 3, passo: int = 600, seq: int = 1) -> Tappa:
    alternative = tuple(
        Salita(f"T{linea}_{k}", linea, partenza + k * passo, arrivo + k * passo)
        for k in range(quante)
    )
    return Tappa("A", seq, "B", seq + 5, minimo, alternative)


def _una_tappa(partenza: int, arrivo: int) -> Itinerario:
    return Itinerario("prova", BASE, (_tappa(partenza, arrivo),))


# =============================================================================
# La catena calcola una probabilita'
# =============================================================================


def test_una_sola_tappa_coincide_con_la_forma_chiusa() -> None:
    """Senza cambi e senza correlazione, P(arrivo <= T) e' la ripartizione del ritardo.

    E' l'unico caso in cui esiste un valore di riferimento indipendente
    dall'implementazione, ed e' percio' l'unico ancoraggio non circolare.
    """
    modello = ModelloSintetico(correlazione=0.0)
    partenza, arrivo = BASE + 3600, BASE + 5400  # si prende sempre: nessuna mescolanza
    itinerario = _una_tappa(partenza, arrivo)
    attesa = modello.distribuzione(Tratta("prova", "L1", "TL1_0", "B", 6, arrivo))

    for scarto in (0, 300, 900):
        esito = probabilita_convoluzione(itinerario, modello, arrivo + scarto)
        assert esito.probabilita == pytest.approx(attesa.cdf(scarto), abs=0.02)


def test_i_due_metodi_concordano() -> None:
    modello = ModelloSintetico(correlazione=0.7)
    itinerario = Itinerario(
        "prova", BASE,
        (_tappa(BASE, BASE + 1500), _tappa(BASE + 1800, BASE + 3000, minimo=180, linea="L2", seq=3)),
    )
    for scadenza in (BASE + 3300, BASE + 3900, BASE + 5400):
        convoluzione = probabilita_convoluzione(itinerario, modello, scadenza)
        campionamento = probabilita_montecarlo(
            itinerario, modello, scadenza, campioni=40_000,
            generatore=np.random.default_rng(7),
        )
        assert convoluzione.probabilita == pytest.approx(campionamento.probabilita, abs=0.05)


@pytest.mark.parametrize("metodo", ["convoluzione", "montecarlo"])
def test_la_probabilita_non_decresce_al_crescere_della_scadenza(metodo: str) -> None:
    """Una violazione qui non solleva nulla e rende insensato l'intero confronto."""
    modello = ModelloSintetico()
    itinerario = Itinerario(
        "prova", BASE,
        (_tappa(BASE, BASE + 1500), _tappa(BASE + 1800, BASE + 3000, minimo=180, linea="L2", seq=3)),
    )
    valori = []
    for minuti in (45, 55, 65, 90, 150):
        scadenza = BASE + minuti * 60
        if metodo == "convoluzione":
            valori.append(probabilita_convoluzione(itinerario, modello, scadenza).probabilita)
        else:
            valori.append(
                probabilita_montecarlo(
                    itinerario, modello, scadenza, campioni=20_000,
                    generatore=np.random.default_rng(11),
                ).probabilita
            )
    assert all(a <= b + 1e-9 for a, b in zip(valori, valori[1:])), valori


@pytest.mark.parametrize("metodo", ["convoluzione", "montecarlo"])
def test_la_probabilita_resta_fra_zero_e_uno(metodo: str) -> None:
    modello = ModelloSintetico(correlazione=0.9)
    itinerario = Itinerario(
        "prova", BASE,
        (
            _tappa(BASE, BASE + 900),
            _tappa(BASE + 960, BASE + 1800, minimo=120, linea="L2", seq=3),
            _tappa(BASE + 1860, BASE + 2700, minimo=120, linea="L3", seq=5),
        ),
    )
    scadenza = BASE + 3000
    if metodo == "convoluzione":
        valore = probabilita_convoluzione(itinerario, modello, scadenza).probabilita
    else:
        valore = probabilita_montecarlo(
            itinerario, modello, scadenza, campioni=20_000,
            generatore=np.random.default_rng(3),
        ).probabilita
    assert 0.0 <= valore <= 1.0


def test_una_scadenza_lontanissima_da_probabilita_quasi_certa() -> None:
    modello = ModelloSintetico()
    itinerario = Itinerario(
        "prova", BASE,
        (_tappa(BASE, BASE + 900), _tappa(BASE + 1500, BASE + 2400, minimo=120, linea="L2", seq=3)),
    )
    esito = probabilita_convoluzione(itinerario, modello, BASE + 3 * 3600)
    assert esito.probabilita > 0.95


# =============================================================================
# La guardia sulla conservazione della massa
# =============================================================================


def test_la_guardia_scatta_se_la_massa_non_si_conserva(monkeypatch) -> None:
    """Riproduce il difetto che si era manifestato, per sapere che la guardia funziona.

    Il difetto originale nasceva dall'usare la massa discretizzata per la
    probabilita' di prendere una corsa e la ripartizione continua per quella di
    mancarla: le due non sommano a uno e la probabilita' finale superava uno.
    Qui la si riproduce di proposito, sbilanciando la ripartizione: senza questo
    test la guardia sarebbe codice di cui non sappiamo se funziona.
    """
    originale = robust._ripartizione_discreta

    def sbilanciata(massa, griglia, valori):
        return np.clip(originale(massa, griglia, valori) * 0.5, 0.0, 1.0)

    monkeypatch.setattr(robust, "_ripartizione_discreta", sbilanciata)

    modello = ModelloSintetico()
    itinerario = Itinerario(
        "prova", BASE,
        (_tappa(BASE, BASE + 900), _tappa(BASE + 1500, BASE + 2400, minimo=120, linea="L2", seq=3)),
    )
    with pytest.raises(ErrorePianificatore, match="massa di probabilita'"):
        probabilita_convoluzione(itinerario, modello, BASE + 3000)


def test_senza_lo_sbilanciamento_la_guardia_non_scatta() -> None:
    """Controllo speculare: la guardia non deve fermare il caso corretto."""
    modello = ModelloSintetico()
    itinerario = Itinerario(
        "prova", BASE,
        (_tappa(BASE, BASE + 900), _tappa(BASE + 1500, BASE + 2400, minimo=120, linea="L2", seq=3)),
    )
    assert probabilita_convoluzione(itinerario, modello, BASE + 3000).probabilita >= 0.0


# =============================================================================
# Il recupero delle coincidenze perse
# =============================================================================


def test_una_coincidenza_persa_non_annulla_l_itinerario() -> None:
    """E' la ragione per cui il fallimento secco sarebbe stato il modello sbagliato.

    Con una coincidenza impossibile da prendere ma una corsa successiva
    disponibile, la probabilita' di arrivare entro una scadenza generosa deve
    restare alta: chi perde l'autobus prende quello dopo.
    """
    modello = ModelloSintetico(correlazione=0.0)
    # La seconda tappa parte PRIMA che si possa arrivare: la prima corsa e' persa
    # con certezza, ma la successiva parte dieci minuti dopo.
    itinerario = Itinerario(
        "prova", BASE,
        (
            _tappa(BASE, BASE + 1800),
            _tappa(BASE + 1500, BASE + 2400, minimo=120, linea="L2", quante=3, passo=600, seq=3),
        ),
    )
    stretta = probabilita_convoluzione(itinerario, modello, BASE + 2700)
    larga = probabilita_convoluzione(itinerario, modello, BASE + 5400)
    assert stretta.probabilita < 0.1, "la prima corsa non e' prendibile"
    assert larga.probabilita > 0.5, "il recupero deve salvare l'itinerario"
    assert larga.quota_tetto_raggiunto < 1.0


def test_senza_recuperi_l_itinerario_fallisce() -> None:
    modello = ModelloSintetico(correlazione=0.0)
    itinerario = Itinerario(
        "prova", BASE,
        (
            _tappa(BASE, BASE + 1800),
            _tappa(BASE + 1500, BASE + 2400, minimo=120, linea="L2", seq=3),
        ),
    )
    esito = probabilita_convoluzione(itinerario, modello, BASE + 5400, recuperi_massimi=0)
    # Non e' zero: la coincidenza resta prendibile quando il mezzo in arrivo e'
    # molto in anticipo e quello in partenza molto in ritardo. E' il
    # comportamento giusto, ed e' il motivo per cui la soglia non e' stretta.
    assert esito.probabilita < 0.25
    assert esito.quota_tetto_raggiunto > 0.7
    con_recuperi = probabilita_convoluzione(itinerario, modello, BASE + 5400)
    assert con_recuperi.probabilita > esito.probabilita + 0.3


# =============================================================================
# Strategie di scelta
# =============================================================================


def _candidato(arrivo_offset: int, cambi: int, margine: int = 600) -> Candidato:
    tappe = [_tappa(BASE, BASE + 900)]
    for indice in range(cambi):
        precedente = tappe[-1].alternative[0].arrivo_programmato
        tappe.append(
            _tappa(precedente + margine + 120, precedente + margine + 900,
                   minimo=120, linea=f"L{indice + 2}", seq=3 + indice)
        )
    itinerario = Itinerario("prova", BASE, tuple(tappe))
    return Candidato(itinerario, BASE + arrivo_offset, cambi, 0)


def test_il_piu_veloce_sceglie_il_primo_arrivo() -> None:
    candidati = [_candidato(3600, 2), _candidato(2400, 3), _candidato(3000, 1)]
    assert piu_veloce(candidati).candidato.orario_arrivo == BASE + 2400


def test_meno_cambi_sceglie_il_minor_numero_di_trasbordi() -> None:
    candidati = [_candidato(3600, 2), _candidato(2400, 3), _candidato(3000, 1)]
    assert meno_cambi(candidati).candidato.cambi == 1


def test_il_margine_fisso_scarta_gli_itinerari_troppo_tesi() -> None:
    teso = _candidato(2400, 1, margine=60)
    comodo = _candidato(3000, 1, margine=900)
    scelta = margine_fisso([teso, comodo], margine=300)
    assert scelta.candidato is comodo
    assert "margine >= 5 min" in scelta.motivo


def test_il_margine_fisso_non_rinuncia_quando_nessuno_soddisfa_la_regola() -> None:
    """Fingere che non risponda la giudicherebbe solo sui casi facili."""
    teso = _candidato(2400, 1, margine=60)
    piu_teso = _candidato(3000, 1, margine=30)
    scelta = margine_fisso([teso, piu_teso], margine=300)
    assert scelta.candidato is teso
    assert "nessun itinerario raggiunge" in scelta.motivo


def test_il_pianificatore_robusto_sceglie_il_massimo() -> None:
    modello = ModelloSintetico(correlazione=0.5)
    candidati = [_candidato(3600, 1, margine=60), _candidato(3900, 1, margine=1200)]
    scelta = pianifica_robusto(candidati, modello, BASE + 4500)
    assert scelta.probabilita == max(scelta.probabilita_per_candidato)
    assert len(scelta.probabilita_per_candidato) == 2


def test_senza_candidati_il_pianificatore_lo_dice() -> None:
    with pytest.raises(ErrorePianificatore, match="nessun itinerario"):
        pianifica_robusto([], ModelloSintetico(), BASE + 3600)
