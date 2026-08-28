"""Quanto spesso il greedy fallisce dove una soluzione esiste.

E' la misura che decide se il viaggio multi-tappa sia davvero un problema di
soddisfacimento di vincoli. Il controesempio costruito in
:func:`src.csp.risolutori.controesempio_budget` dimostra che il caso e'
**possibile**; questo esperimento dice se sia **frequente** su istanze costruite
dalla rete vera. Se la quota fosse prossima a zero, l'argomento si chiuderebbe
qui come risultato negativo: i budget globali non stringono quasi mai, e il
problema si risolve tappa per tappa senza mai tornare indietro.

Le istanze non sono inventate. Le catene di fermate sono estratte con un seme
dichiarato fra quelle effettivamente servite, i domini sono le frontiere di
Pareto prodotte dalla ricerca multi-criterio della Fase 2, e i budget sono
derivati dai dati come "minimo ottenibile piu' un margine" invece che scelti a
occhio: un tetto sotto quel minimo renderebbe l'istanza infattibile per
aritmetica e non per interazione fra le tappe.

**Perche' piu' grafi brevi invece di uno lungo.** Un viaggio a quattro tappe di
tratte casuali attraversa la citta' per cinque o sei ore, e un grafo che copra
tutto quel periodo rende ogni ricerca proibitiva: misurato su Roma, la stessa
ricerca costa 2,87 s su un orizzonte di 150 minuti e **38,63 s** su uno di 420,
perche' il numero di stati raggiungibili cresce con la finestra. Si costruisce
percio' una successione di grafi brevi sfalsati di un'ora, e ogni tratta viene
cercata su quello che copre il suo istante di disponibilita'. L'orizzonte
effettivo di ciascuna ricerca resta cosi' fra i 90 e i 150 minuti, confrontabile
con i 120 della Fase 2, e vale la stessa limitazione gia' dichiarata li': si
trova l'ottimo dentro la finestra.

Nessun modello dei ritardi entra in questo esperimento: i risultati sono
deterministici e si calcolano sull'orario programmato.

    python scripts/csp_greedy.py
"""

from __future__ import annotations

import argparse
import random
import sys
from dataclasses import dataclass
from datetime import date, datetime, time
from pathlib import Path
from typing import Sequence
from zoneinfo import ZoneInfo

import pandas as pd

RADICE = Path(__file__).resolve().parents[1]
if str(RADICE) not in sys.path:
    sys.path.insert(0, str(RADICE))

from src.csp.modello import Candidato, Istanza, Tappa, limiti_inferiori  # noqa: E402
from src.csp.risolutori import risolvi_completo, risolvi_greedy  # noqa: E402
from src.graph.search import cerca_frontiera_pareto  # noqa: E402
from src.graph.time_expanded import costruisci  # noqa: E402
from src.gtfs.loader import carica_archivio  # noqa: E402

CITTA = ("roma", "torino")
FUSO = "Europe/Rome"

ORA_PARTENZA = 8
ORIZZONTE_MINUTI = 150
PASSO_GRAFI_MINUTI = 60
QUANTI_GRAFI = 6
"""Grafi sfalsati di un'ora dalle 08:00: coprono le disponibilita' fino alle 13:00."""

SEME = 20260828
CATENE_PER_CITTA = 25
TAPPE_MASSIME = 4
PUNTI_GRIGLIA = 3
"""Istanti di disponibilita' da cui si interroga il pianificatore per ogni tratta.

Ogni punto e' una ricerca di Pareto completa: tre e' il compromesso fra ricchezza
del dominio, che serve perche' il CSP abbia scelte vere, e durata
dell'esperimento.
"""
PASSO_GRIGLIA_MINUTI = 10
SOSTA_MINIMA_MINUTI = 10
"""Tempo speso alla tappa intermedia per la ragione per cui ci si e' fermati."""
AMPIEZZA_FINESTRA_MINUTI = 20
MARGINE_SCADENZA_MINUTI = 45
SLACK_PIEDI_SECONDI = 1800
"""Margine sul budget di cammino, largo di proposito.

L'esperimento isola l'effetto del budget sui **cambi**: far stringere anche
quello sul cammino mescolerebbe due cause in un solo numero.
"""

SLACK_CAMBI = (0, 1, 2, 3)
RISULTATI = RADICE / "results"


@dataclass(frozen=True)
class Catena:
    """Una successione di fermate con i domini gia' calcolati per ogni tratta."""

    citta: str
    identificativo: str
    fermate: tuple[str, ...]
    domini: tuple[tuple[Candidato, ...], ...]
    primi_arrivi: tuple[int, ...]
    """Arrivo piu' precoce ottenibile su ciascuna tratta, per derivare le finestre."""


class Grafi:
    """I grafi sfalsati di una citta', con la scelta di quello giusto per un istante."""

    def __init__(self, inizi: Sequence[int], grafi: Sequence) -> None:
        self.inizi = list(inizi)
        self.grafi = list(grafi)

    def per(self, istante: int):
        """Il grafo con inizio piu' tardo fra quelli che non partono dopo l'istante.

        Cosi' l'istante di disponibilita' cade al piu' un'ora dentro la finestra e
        restano almeno novanta minuti di orizzonte utile.
        """
        scelto = self.grafi[0]
        for inizio, grafo in zip(self.inizi, self.grafi):
            if inizio <= istante:
                scelto = grafo
            else:
                break
        return scelto

    @property
    def primo(self):
        return self.grafi[0]


def archivio_piu_recente(citta: str) -> Path:
    archivi = sorted((RADICE / "data" / "raw" / "gtfs" / citta).glob("*.zip"))
    if not archivi:
        raise SystemExit(f"Nessun archivio GTFS per '{citta}'.")
    return archivi[-1]


def giorno_dell_archivio(percorso: Path) -> date:
    return date.fromisoformat(percorso.stem.split("_")[0])


def istante_partenza(giorno: date) -> int:
    return int(datetime.combine(giorno, time(ORA_PARTENZA), tzinfo=ZoneInfo(FUSO)).timestamp())


def catene_casuali(grafo, quante: int, lunghezza: int, seme: int) -> list[tuple[str, ...]]:
    """Successioni di fermate distinte, estratte fra quelle effettivamente servite.

    Una fermata senza partenze nella finestra non misura il problema, misura
    l'assenza di servizio: la stessa esclusione della Fase 2, con la stessa soglia.
    """
    generatore = random.Random(seme)
    servite = sorted(
        grafo.fermate[f] for f, v in grafo.partenze_per_fermata.items() if v.size >= 3
    )
    if len(servite) < lunghezza:
        raise SystemExit("troppe poche fermate servite nella finestra")
    return [tuple(generatore.sample(servite, lunghezza)) for _ in range(quante)]


def dominio_di_tratta(
    grafi: Grafi, origine: str, destinazione: str, pronti_da: Sequence[int]
) -> tuple[Candidato, ...]:
    """Frontiere di Pareto interrogate da piu' istanti di disponibilita', unite.

    Ogni candidato conserva l'istante da cui e' stato calcolato: e' cio' che
    permette al vincolo di precedenza di restare una condizione sull'assegnazione
    invece di diventare una modifica del dominio, che renderebbe i domini dinamici
    e il problema non piu' un CSP in senso stretto.
    """
    trovati: dict[tuple[int, int, int, int], Candidato] = {}
    for pronto in pronti_da:
        esito = cerca_frontiera_pareto(grafi.per(pronto), origine, destinazione, pronto)
        for etichetta in esito.frontiera:
            chiave = (pronto, etichetta.orario_arrivo, etichetta.cambi,
                      etichetta.secondi_a_piedi)
            if chiave not in trovati:
                trovati[chiave] = Candidato(
                    pronto_da=pronto,
                    orario_arrivo=etichetta.orario_arrivo,
                    cambi=etichetta.cambi,
                    secondi_a_piedi=etichetta.secondi_a_piedi,
                )
    return tuple(trovati.values())


def costruisci_catena(
    grafi: Grafi, citta: str, fermate: tuple[str, ...], partenza: int, indice: int
) -> Catena | None:
    """Calcola i domini finche' le tratte sono percorribili, poi si ferma.

    Una catena che si interrompe alla terza tratta resta utilizzabile per le
    istanze a due tappe, quindi se ne conserva il prefisso invece di scartare
    tutto: buttarla via intera toglierebbe istanze valide e farebbe sembrare il
    fenomeno piu' raro di quanto sia. Restituisce ``None`` solo sotto le due
    tappe, sotto le quali non esiste viaggio multi-tappa.
    """
    domini: list[tuple[Candidato, ...]] = []
    primi: list[int] = []
    disponibile = partenza
    passo = PASSO_GRIGLIA_MINUTI * 60

    for posizione in range(len(fermate) - 1):
        griglia = [disponibile + k * passo for k in range(PUNTI_GRIGLIA)]
        dominio = dominio_di_tratta(grafi, fermate[posizione], fermate[posizione + 1], griglia)
        if not dominio:
            break
        domini.append(dominio)
        primo_arrivo = min(c.orario_arrivo for c in dominio)
        primi.append(primo_arrivo)
        disponibile = primo_arrivo + SOSTA_MINIMA_MINUTI * 60

    if len(domini) < 2:
        return None

    return Catena(
        citta=citta,
        identificativo=f"{citta}-{indice:03d}",
        fermate=fermate[: len(domini) + 1],
        domini=tuple(domini),
        primi_arrivi=tuple(primi),
    )


def istanza_da_catena(catena: Catena, n_tappe: int, slack_cambi: int) -> Istanza:
    """Ritaglia un viaggio di ``n_tappe`` dal prefisso della catena.

    I budget sono il minimo ottenibile piu' un margine, cosi' che ``slack_cambi``
    misuri quanto il tetto sia stringente **rispetto a quella istanza** e non in
    assoluto: istanze diverse hanno minimi diversi, e un tetto fisso confronterebbe
    cose non confrontabili.
    """
    tappe: list[Tappa] = []
    for posizione in range(n_tappe):
        ultima = posizione == n_tappe - 1
        finestra = None
        if not ultima:
            inizio = catena.primi_arrivi[posizione]
            finestra = (inizio, inizio + AMPIEZZA_FINESTRA_MINUTI * 60)
        tappe.append(
            Tappa(
                origine=catena.fermate[posizione],
                destinazione=catena.fermate[posizione + 1],
                sosta_minima=0 if posizione == 0 else SOSTA_MINIMA_MINUTI * 60,
                dominio=catena.domini[posizione],
                finestra=finestra,
            )
        )

    parziale = Istanza(
        citta=catena.citta,
        identificativo=f"{catena.identificativo}-t{n_tappe}",
        tappe=tuple(tappe),
        cambi_max=1 << 30,
        piedi_max=1 << 30,
        scadenza=1 << 62,
    )
    minimo_cambi, minimo_piedi = limiti_inferiori(parziale)

    return Istanza(
        citta=catena.citta,
        identificativo=parziale.identificativo,
        tappe=parziale.tappe,
        cambi_max=minimo_cambi + slack_cambi,
        piedi_max=minimo_piedi + SLACK_PIEDI_SECONDI,
        scadenza=catena.primi_arrivi[n_tappe - 1] + MARGINE_SCADENZA_MINUTI * 60,
    )


def misura(catene: Sequence[Catena]) -> list[dict]:
    righe = []
    for catena in catene:
        for n_tappe in range(2, len(catena.domini) + 1):
            for slack in SLACK_CAMBI:
                istanza = istanza_da_catena(catena, n_tappe, slack)
                greedy = risolvi_greedy(istanza)
                completo = risolvi_completo(istanza)
                righe.append(
                    {
                        "citta": catena.citta,
                        "istanza": istanza.identificativo,
                        "n_tappe": n_tappe,
                        "slack_cambi": slack,
                        "cambi_max": istanza.cambi_max,
                        "dominio_medio": round(
                            sum(len(t.dominio) for t in istanza.tappe) / n_tappe, 2
                        ),
                        "greedy_risolve": int(greedy.risolta),
                        "completo_risolve": int(completo.risolta),
                        "greedy_fallisce_a_torto": int(completo.risolta and not greedy.risolta),
                        "nodi_greedy": greedy.nodi,
                        "nodi_completo": completo.nodi,
                        "secondi_completo": completo.secondi,
                    }
                )
    return righe


def riassumi(dati: pd.DataFrame) -> None:
    print("\n=== Tabella 1 - il greedy fallisce dove una soluzione esiste? ===\n")
    for citta in sorted(dati["citta"].unique()):
        parte = dati[dati["citta"] == citta]
        print(f"  {citta.upper()}")
        print(f"  {'tappe':>5} {'slack':>6} {'istanze':>8} {'risolubili':>11} "
              f"{'greedy ok':>10}  {'greedy sbaglia':>16}")
        for n_tappe in sorted(parte["n_tappe"].unique()):
            for slack in sorted(parte["slack_cambi"].unique()):
                b = parte[(parte["n_tappe"] == n_tappe) & (parte["slack_cambi"] == slack)]
                risolubili = int(b["completo_risolve"].sum())
                sbagli = int(b["greedy_fallisce_a_torto"].sum())
                quota = f"{sbagli / risolubili:.0%}" if risolubili else "-"
                print(f"  {n_tappe:>5} {slack:>6} {len(b):>8} {risolubili:>11} "
                      f"{int(b['greedy_risolve'].sum()):>10}  {sbagli:>7} ({quota:>4})")
        print()

    risolubili = int(dati["completo_risolve"].sum())
    sbagli = int(dati["greedy_fallisce_a_torto"].sum())
    if risolubili:
        print(f"  COMPLESSIVO: su {risolubili} istanze risolubili il greedy ne dichiara "
              f"infattibili {sbagli}, cioe' il {sbagli / risolubili:.1%}.")
    else:
        print("  COMPLESSIVO: nessuna istanza risolubile.")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catene", type=int, default=CATENE_PER_CITTA)
    parser.add_argument("--seme", type=int, default=SEME)
    argomenti = parser.parse_args(argv)

    RISULTATI.mkdir(exist_ok=True)
    tutte: list[Catena] = []

    for citta in CITTA:
        percorso = archivio_piu_recente(citta)
        giorno = giorno_dell_archivio(percorso)
        partenza = istante_partenza(giorno)
        print(f"[{citta}] archivio {percorso.name}, giorno {giorno}", flush=True)

        archivio = carica_archivio(percorso, con_stop_times=True)
        inizi = [partenza + k * PASSO_GRAFI_MINUTI * 60 for k in range(QUANTI_GRAFI)]
        avvio = datetime.now()
        grafi = Grafi(inizi, [costruisci(archivio, citta, giorno, i, ORIZZONTE_MINUTI)
                              for i in inizi])
        print(f"  {QUANTI_GRAFI} grafi da {ORIZZONTE_MINUTI} min sfalsati di "
              f"{PASSO_GRAFI_MINUTI} min, in "
              f"{(datetime.now() - avvio).total_seconds():.1f}s", flush=True)

        catene = catene_casuali(grafi.primo, argomenti.catene, TAPPE_MASSIME + 1, argomenti.seme)
        buone, perse = [], 0
        for indice, fermate in enumerate(catene):
            costruita = costruisci_catena(grafi, citta, fermate, partenza, indice)
            if costruita is None:
                perse += 1
            else:
                buone.append(costruita)
            if (indice + 1) % 5 == 0 or indice + 1 == len(catene):
                print(f"    catena {indice + 1}/{len(catene)}", flush=True)
        tutte.extend(buone)
        lunghezze: dict[int, int] = {}
        for costruita in buone:
            lunghezze[len(costruita.domini)] = lunghezze.get(len(costruita.domini), 0) + 1
        dettaglio = ", ".join(f"{v} da {k} tratte" for k, v in sorted(lunghezze.items()))
        print(f"  utilizzabili {len(buone)}/{len(catene)} ({dettaglio}); "
              f"{perse} sotto le due tratte", flush=True)

    if not tutte:
        raise SystemExit("nessuna catena utilizzabile: esperimento non eseguibile")

    dati = pd.DataFrame(misura(tutte))
    destinazione = RISULTATI / "csp_greedy.csv"
    dati.to_csv(destinazione, index=False)
    print(f"\nscritto {destinazione} ({len(dati)} righe)")
    riassumi(dati)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
