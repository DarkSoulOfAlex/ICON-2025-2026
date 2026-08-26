"""Strategie di riferimento contro cui misurare il pianificatore robusto.

Le tre baseline non sono avversari di comodo: rappresentano cio' che si fa
davvero quando non si dispone di un modello probabilistico dei ritardi.

* :func:`piu_veloce` e' il pianificatore di qualunque applicazione di viaggio:
  minimizza l'orario di arrivo secondo l'orario pubblicato. E' il termine di
  paragone naturale, perche' e' quello che l'utente ha oggi.
* :func:`meno_cambi` sceglie l'itinerario con il minor numero di trasbordi. E'
  cio' che fa chi ha imparato per esperienza che ogni cambio e' un'occasione di
  perdere una coincidenza, ma non sa quantificarlo.
* :func:`margine_fisso` e' **la baseline che conta**. Rappresenta la persona
  ragionevole che, senza modello, si da' una regola: accetto solo itinerari in
  cui ogni coincidenza ha almeno cinque minuti di margine, e fra quelli prendo il
  piu' veloce. E' una strategia sensata, gratuita e sorprendentemente efficace,
  ed e' quella che il pianificatore probabilistico deve battere per giustificare
  la propria esistenza. Se non la battesse, tutta la complessita' del modello dei
  ritardi non sarebbe ripagata.

Tutte restituiscono una :class:`Scelta`, e tutte vengono poi valutate con lo
**stesso** calcolo di P(arrivo <= T): il confronto misura cosi' la strategia di
scelta, non il metodo di valutazione.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.planner.robust import Candidato

MARGINE_PREDEFINITO = 300


@dataclass(frozen=True)
class Scelta:
    """L'itinerario selezionato da una strategia, con la ragione della scelta."""

    strategia: str
    candidato: Candidato
    motivo: str

    @property
    def itinerario(self):
        return self.candidato.itinerario


def piu_veloce(candidati: list[Candidato]) -> Scelta:
    """Il primo arrivo secondo l'orario pubblicato."""
    scelto = min(candidati, key=lambda c: (c.orario_arrivo, c.cambi))
    return Scelta(
        strategia="piu_veloce",
        candidato=scelto,
        motivo="minimo orario di arrivo programmato",
    )


def meno_cambi(candidati: list[Candidato]) -> Scelta:
    """Il minor numero di trasbordi; a parita', il piu' veloce."""
    scelto = min(candidati, key=lambda c: (c.cambi, c.orario_arrivo))
    return Scelta(
        strategia="meno_cambi",
        candidato=scelto,
        motivo=f"minimo numero di cambi ({min(c.cambi for c in candidati)})",
    )


def margine_fisso(candidati: list[Candidato], margine: int = MARGINE_PREDEFINITO) -> Scelta:
    """Il piu' veloce fra quelli in cui ogni coincidenza ha almeno ``margine`` secondi.

    Se nessun itinerario soddisfa la regola, la strategia **allenta il vincolo**
    invece di rinunciare, e lo dichiara nel motivo. E' cio' che farebbe una
    persona reale: di fronte a nessuna alternativa comoda, si prende quella meno
    scomoda. Fingere che la strategia non risponda renderebbe il confronto
    ingiusto a suo sfavore, perche' la si giudicherebbe solo sui casi facili.
    """
    ammessi = [
        c for c in candidati
        if all(m >= margine for m in c.itinerario.margini_programmati)
    ]
    if ammessi:
        scelto = min(ammessi, key=lambda c: (c.orario_arrivo, c.cambi))
        return Scelta(
            strategia="margine_fisso",
            candidato=scelto,
            motivo=f"piu' veloce fra i {len(ammessi)} con margine >= {margine // 60} min",
        )

    # Nessuno soddisfa la regola: si prende quello con il margine minimo piu' alto.
    def margine_peggiore(candidato: Candidato) -> int:
        margini = candidato.itinerario.margini_programmati
        return min(margini) if margini else 1 << 30

    scelto = max(candidati, key=lambda c: (margine_peggiore(c), -c.orario_arrivo))
    return Scelta(
        strategia="margine_fisso",
        candidato=scelto,
        motivo=(
            f"nessun itinerario raggiunge {margine // 60} min di margine: "
            f"scelto quello con il margine minimo piu' alto "
            f"({margine_peggiore(scelto) // 60} min)"
        ),
    )


STRATEGIE = {
    "piu_veloce": piu_veloce,
    "meno_cambi": meno_cambi,
    "margine_fisso": margine_fisso,
}
