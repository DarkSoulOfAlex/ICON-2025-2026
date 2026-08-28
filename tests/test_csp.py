"""Test del viaggio multi-tappa come problema di soddisfacimento di vincoli.

Coprono le due cose che possono sbagliare in silenzio: un vincolo che non rifiuta
cio' che dovrebbe rifiutare, e un risolutore che dichiara infattibile un'istanza
risolubile. La seconda e' l'oggetto stesso dell'argomento, quindi e' collaudata
sia nel verso che deve accadere sia in quello che non deve.
"""

from __future__ import annotations

import pytest

from src.csp.modello import (
    Candidato,
    ErroreCSP,
    Istanza,
    Tappa,
    ammissibile,
    limiti_inferiori,
    violazioni,
)
from src.csp.risolutori import (
    controesempio_budget,
    risolvi_completo,
    risolvi_greedy,
)

BASE = 1_800_000_000
MINUTO = 60


def _istanza_semplice(cambi_max: int = 99, piedi_max: int = 99_999) -> Istanza:
    """Due tappe con due alternative ciascuna e budget non stringenti."""
    a1 = Candidato(BASE, BASE + 10 * MINUTO, cambi=1, secondi_a_piedi=120)
    a2 = Candidato(BASE, BASE + 20 * MINUTO, cambi=0, secondi_a_piedi=600)
    b1 = Candidato(BASE + 15 * MINUTO, BASE + 40 * MINUTO, cambi=1, secondi_a_piedi=60)
    b2 = Candidato(BASE + 25 * MINUTO, BASE + 50 * MINUTO, cambi=0, secondi_a_piedi=300)
    return Istanza(
        citta="prova",
        identificativo="semplice",
        tappe=(
            Tappa("A", "B", sosta_minima=0, dominio=(a1, a2)),
            Tappa("B", "C", sosta_minima=5 * MINUTO, dominio=(b1, b2)),
        ),
        cambi_max=cambi_max,
        piedi_max=piedi_max,
        scadenza=BASE + 120 * MINUTO,
    )


# =============================================================================
# Il controesempio: e' la ragione per cui l'argomento esiste
# =============================================================================


def test_il_greedy_fallisce_dove_una_soluzione_esiste() -> None:
    """Il caso costruito a mano riportato nel documento.

    Se questo test passasse per la ragione sbagliata - per esempio perche' il
    risolutore completo sbaglia - l'intero argomento poggerebbe sul nulla, quindi
    si verifica anche che la soluzione trovata sia davvero ammissibile e che sia
    quella attesa.
    """
    istanza = controesempio_budget(BASE)

    greedy = risolvi_greedy(istanza)
    completo = risolvi_completo(istanza)

    assert not greedy.risolta, "il greedy non dovrebbe trovare soluzione"
    assert completo.risolta, "una soluzione esiste e il risolutore completo deve trovarla"
    assert ammissibile(istanza, completo.assegnazione)

    # La soluzione passa per X2, che arriva SETTE MINUTI DOPO X1: e' il punto.
    assert completo.assegnazione[0].orario_arrivo == BASE + 12 * MINUTO
    assert sum(c.cambi for c in completo.assegnazione) == istanza.cambi_max


def test_senza_budget_globale_il_controesempio_si_risolve_da_solo() -> None:
    """Controllo speculare: e' il budget ad accoppiare le tappe, non altro.

    Alzando il solo tetto sui cambi, la stessa istanza diventa risolubile anche
    dal greedy. Senza questo test non sapremmo se a far fallire il greedy sia il
    budget o un difetto della costruzione.
    """
    stretta = controesempio_budget(BASE)
    larga = Istanza(
        citta=stretta.citta,
        identificativo="controesempio_senza_budget",
        tappe=stretta.tappe,
        cambi_max=99,
        piedi_max=stretta.piedi_max,
        scadenza=stretta.scadenza,
    )
    assert risolvi_greedy(larga).risolta


def test_il_greedy_concorda_col_completo_quando_i_budget_non_stringono() -> None:
    """Se i vincoli sono solo di precedenza, arrivare prima non puo' nuocere."""
    istanza = _istanza_semplice()
    assert risolvi_greedy(istanza).risolta == risolvi_completo(istanza).risolta


# =============================================================================
# Ogni vincolo deve poter rifiutare, e rifiutare per la ragione giusta
# =============================================================================


def test_la_precedenza_rifiuta_chi_riparte_prima_di_essere_arrivato() -> None:
    istanza = _istanza_semplice()
    primo = istanza.tappe[0].dominio[1]      # arriva a +20 min
    secondo = istanza.tappe[1].dominio[0]    # pronto a +15 min, con sosta 5 servirebbe +25
    assert "precedenza[1]" in violazioni(istanza, (primo, secondo))


def test_la_finestra_rifiuta_sia_l_anticipo_sia_il_ritardo() -> None:
    """L'estremo inferiore non e' decorativo: arrivare troppo presto e' una violazione."""
    presto = Candidato(BASE, BASE + 5 * MINUTO, cambi=0, secondi_a_piedi=0)
    tardi = Candidato(BASE, BASE + 60 * MINUTO, cambi=0, secondi_a_piedi=0)
    coda = Candidato(BASE + 90 * MINUTO, BASE + 100 * MINUTO, cambi=0, secondi_a_piedi=0)
    istanza = Istanza(
        citta="prova",
        identificativo="finestra",
        tappe=(
            Tappa("A", "B", sosta_minima=0, dominio=(presto, tardi),
                  finestra=(BASE + 10 * MINUTO, BASE + 30 * MINUTO)),
            Tappa("B", "C", sosta_minima=0, dominio=(coda,)),
        ),
        cambi_max=99,
        piedi_max=99_999,
        scadenza=BASE + 120 * MINUTO,
    )
    assert "finestra_anticipo[0]" in violazioni(istanza, (presto, coda))
    assert "finestra_ritardo[0]" in violazioni(istanza, (tardi, coda))


def test_i_due_budget_globali_rifiutano_separatamente() -> None:
    stretta_cambi = _istanza_semplice(cambi_max=1)
    stretta_piedi = _istanza_semplice(piedi_max=100)
    costosa = (
        Candidato(BASE, BASE + 10 * MINUTO, cambi=1, secondi_a_piedi=120),
        Candidato(BASE + 15 * MINUTO, BASE + 40 * MINUTO, cambi=1, secondi_a_piedi=60),
    )
    assert "cambi_max" in violazioni(stretta_cambi, costosa)
    assert "piedi_max" in violazioni(stretta_piedi, costosa)


def test_la_scadenza_finale_rifiuta_l_arrivo_tardivo() -> None:
    istanza = _istanza_semplice()
    stretta = Istanza(
        citta=istanza.citta,
        identificativo="scadenza",
        tappe=istanza.tappe,
        cambi_max=99,
        piedi_max=99_999,
        scadenza=BASE + 30 * MINUTO,
    )
    tardi = (istanza.tappe[0].dominio[0], istanza.tappe[1].dominio[0])
    assert "scadenza" in violazioni(stretta, tardi)
    assert not risolvi_completo(stretta).risolta


# =============================================================================
# Proprieta' dei risolutori
# =============================================================================


def test_il_completo_restituisce_l_arrivo_finale_piu_precoce() -> None:
    istanza = _istanza_semplice()
    esito = risolvi_completo(istanza)
    assert esito.risolta
    ultimi = [c.orario_arrivo for c in istanza.tappe[-1].dominio]
    assert esito.assegnazione[-1].orario_arrivo == min(ultimi)


def test_il_completo_non_restituisce_mai_un_assegnazione_non_ammissibile() -> None:
    for tetto in (0, 1, 2, 3, 4, 5, 99):
        istanza = _istanza_semplice(cambi_max=tetto)
        esito = risolvi_completo(istanza)
        if esito.risolta:
            assert ammissibile(istanza, esito.assegnazione), f"tetto {tetto}"


def test_il_limite_inferiore_non_supera_mai_il_consumo_di_una_soluzione() -> None:
    """Se il limite sovrastimasse, la potatura taglierebbe soluzioni valide."""
    istanza = _istanza_semplice()
    minimo_cambi, minimo_piedi = limiti_inferiori(istanza)
    esito = risolvi_completo(istanza)
    assert esito.risolta
    assert minimo_cambi <= sum(c.cambi for c in esito.assegnazione)
    assert minimo_piedi <= sum(c.secondi_a_piedi for c in esito.assegnazione)


# =============================================================================
# Istanze malformate
# =============================================================================


def test_una_tappa_senza_candidati_e_un_errore_non_una_istanza_infattibile() -> None:
    with pytest.raises(ErroreCSP, match="dominio vuoto"):
        Tappa("A", "B", sosta_minima=0, dominio=())


def test_una_finestra_rovesciata_e_un_errore() -> None:
    c = Candidato(BASE, BASE + 60, cambi=0, secondi_a_piedi=0)
    with pytest.raises(ErroreCSP, match="finestra rovesciata"):
        Tappa("A", "B", sosta_minima=0, dominio=(c,), finestra=(BASE + 100, BASE))


def test_un_viaggio_con_una_sola_tappa_non_e_multi_tappa() -> None:
    c = Candidato(BASE, BASE + 60, cambi=0, secondi_a_piedi=0)
    with pytest.raises(ErroreCSP, match="almeno due tappe"):
        Istanza(
            citta="prova",
            identificativo="corta",
            tappe=(Tappa("A", "B", sosta_minima=0, dominio=(c,)),),
            cambi_max=1,
            piedi_max=1,
            scadenza=BASE + 3600,
        )
