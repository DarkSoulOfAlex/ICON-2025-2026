"""Esperimenti della Fase 4: pianificazione robusta contro baseline.

Produce gli artefatti destinati al documento:

    results/robusto_griglia_T.csv    una riga per (citta, coppia, margine, strategia)
    results/robusto_griglia_T.png    le tre curve in funzione del margine
    results/conv_vs_montecarlo.csv   errore e costo dei due metodi di calcolo
    results/conv_vs_montecarlo.png   figura a 150 dpi

**Nessun risultato di questa fase e' un risultato sperimentale sui ritardi.** Il
modello dei ritardi e' sintetico: i numeri dicono se il metodo funziona, non
quanto valga sul trasporto pubblico reale. Ogni file prodotto porta il nome del
modello in una colonna, e lo script rifiuta di scrivere senza il permesso
esplicito.

Uso:
    python scripts/pianificazione_robusta.py --sintetico-ammesso
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Sequence
from zoneinfo import ZoneInfo

RADICE = Path(__file__).resolve().parent.parent
if str(RADICE) not in sys.path:
    sys.path.insert(0, str(RADICE))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from src.delays.interfaccia import ModelloSintetico, assicura_utilizzabile  # noqa: E402
from src.graph.search import cerca_frontiera_pareto  # noqa: E402
from src.graph.time_expanded import costruisci  # noqa: E402
from src.gtfs.loader import carica_archivio  # noqa: E402
from src.planner.baselines import STRATEGIE  # noqa: E402
from src.planner.robust import (  # noqa: E402
    candidati_da_frontiera,
    pianifica_robusto,
    probabilita_convoluzione,
    probabilita_montecarlo,
)

MARGINI = (0, 300, 600, 900, 1200, 1800)
ORIZZONTE = 120
ORA_PARTENZA = 8
SEME = 20260826
COPPIE = 40

COLORI = {"roma": "#1f77b4", "torino": "#ff7f0e"}
MARCATORI = {"roma": "o", "torino": "s"}
RISULTATI = RADICE / "results"


def archivio_piu_recente(citta: str) -> Path:
    archivi = sorted((RADICE / "data" / "raw" / "gtfs" / citta).glob("*.zip"))
    if not archivi:
        raise SystemExit(f"Nessun archivio GTFS per '{citta}'.")
    return archivi[-1]


def prepara(citta: str):
    percorso = archivio_piu_recente(citta)
    giorno = date.fromisoformat(percorso.stem.split("_")[0])
    archivio = carica_archivio(percorso, con_stop_times=True)
    inizio = int(
        datetime(giorno.year, giorno.month, giorno.day, ORA_PARTENZA, 0,
                 tzinfo=ZoneInfo("Europe/Rome")).timestamp()
    )
    grafo = costruisci(archivio, citta, giorno, inizio, ORIZZONTE)
    return grafo, inizio


def coppie_valutabili(grafo, inizio: int, quante: int) -> list[tuple[str, str, list]]:
    """Coppie con almeno due itinerari candidati distinti da confrontare."""
    sys.path.insert(0, str(RADICE / "scripts"))
    from ricerca_confronto import coppie_casuali

    trovate = []
    for origine, destinazione in coppie_casuali(grafo, quante * 4, SEME):
        esito = cerca_frontiera_pareto(grafo, origine, destinazione, inizio)
        if len(esito.frontiera) < 2:
            continue
        candidati = candidati_da_frontiera(grafo, esito, inizio)
        if len(candidati) < 2:
            continue
        trovate.append((origine, destinazione, candidati))
        if len(trovate) >= quante:
            break
    return trovate


def misura_griglia(citta: str, coppie, modello) -> list[dict]:
    """Per ogni coppia e ogni margine, valuta robusto e baseline sulla stessa T."""
    righe = []
    for indice, (origine, destinazione, candidati) in enumerate(coppie, 1):
        piu_rapido = min(c.orario_arrivo for c in candidati)
        for margine in MARGINI:
            scadenza = piu_rapido + margine
            scelta = pianifica_robusto(candidati, modello, scadenza)
            probabilita = dict(zip(range(len(candidati)), scelta.probabilita_per_candidato))

            # Ampiezza su itinerari NOMINALMENTE fattibili: e' cio' che isola la
            # robustezza dalla pura velocita'. Con quelli infattibili inclusi si
            # misurerebbe soprattutto che un itinerario in ritardo sull'orario
            # arriva tardi, che non e' una scoperta.
            fattibili = [
                probabilita[i] for i, c in enumerate(candidati) if c.orario_arrivo <= scadenza
            ]
            ampiezza = (max(fattibili) - min(fattibili)) if len(fattibili) >= 2 else float("nan")

            for nome, strategia in STRATEGIE.items():
                scelto = strategia(candidati).candidato
                posizione = candidati.index(scelto)
                righe.append({
                    "citta": citta, "coppia": indice,
                    "origine": origine, "destinazione": destinazione,
                    "margine_secondi": margine, "scadenza": scadenza,
                    "strategia": nome,
                    "probabilita": probabilita[posizione],
                    "arrivo_programmato": scelto.itinerario.arrivo_programmato,
                    "cambi": scelto.itinerario.cambi,
                    "coincide_con_robusto": posizione == candidati.index(scelta.candidato),
                    "ampiezza_frontiera": ampiezza,
                    "candidati": len(candidati),
                    "modello_ritardo": modello.nome,
                })
            righe.append({
                "citta": citta, "coppia": indice,
                "origine": origine, "destinazione": destinazione,
                "margine_secondi": margine, "scadenza": scadenza,
                "strategia": "robusto",
                "probabilita": scelta.probabilita,
                "arrivo_programmato": scelta.itinerario.arrivo_programmato,
                "cambi": scelta.itinerario.cambi,
                "coincide_con_robusto": True,
                "ampiezza_frontiera": ampiezza,
                "candidati": len(candidati),
                "modello_ritardo": modello.nome,
            })
        if indice % 5 == 0:
            print(f"    {indice}/{len(coppie)} coppie", flush=True)
    return righe


def misura_metodi(citta: str, coppie, modello) -> list[dict]:
    """Errore e costo di convoluzione e Monte Carlo al crescere delle coincidenze."""
    righe = []
    for origine, destinazione, candidati in coppie[:12]:
        for candidato in candidati:
            itinerario = candidato.itinerario
            scadenza = itinerario.arrivo_programmato + 600
            riferimento = probabilita_montecarlo(
                itinerario, modello, scadenza, campioni=200_000,
                generatore=np.random.default_rng(SEME),
            )
            for passo in (5, 10, 30, 60):
                esito = probabilita_convoluzione(itinerario, modello, scadenza, passo=passo)
                righe.append({
                    "citta": citta, "cambi": itinerario.cambi, "metodo": "convoluzione",
                    "parametro": passo, "probabilita": esito.probabilita,
                    "errore": abs(esito.probabilita - riferimento.probabilita),
                    "secondi": esito.secondi,
                    "quota_tetto": esito.quota_tetto_raggiunto,
                    "modello_ritardo": modello.nome,
                })
            for campioni in (100, 1_000, 10_000, 100_000):
                esito = probabilita_montecarlo(
                    itinerario, modello, scadenza, campioni=campioni,
                    generatore=np.random.default_rng(SEME + campioni),
                )
                righe.append({
                    "citta": citta, "cambi": itinerario.cambi, "metodo": "montecarlo",
                    "parametro": campioni, "probabilita": esito.probabilita,
                    "errore": abs(esito.probabilita - riferimento.probabilita),
                    "secondi": esito.secondi,
                    "quota_tetto": esito.quota_tetto_raggiunto,
                    "modello_ritardo": modello.nome,
                })
    return righe


def disegna_griglia(dati: pd.DataFrame, destinazione: Path) -> None:
    figura, assi = plt.subplots(1, 3, figsize=(13.5, 4.4))
    citta_elenco = sorted(dati["citta"].unique())

    for citta in citta_elenco:
        parte = dati[dati["citta"] == citta]
        margini = sorted(parte["margine_secondi"].unique())
        colore = COLORI.get(citta, "#666")
        marcatore = MARCATORI.get(citta, "^")

        ampiezze_medie, ampiezze_std, coincidenze, guadagni, guadagni_std = [], [], [], [], []
        for margine in margini:
            fetta = parte[parte["margine_secondi"] == margine]
            amp = fetta.drop_duplicates("coppia")["ampiezza_frontiera"].dropna()
            ampiezze_medie.append(amp.mean())
            ampiezze_std.append(amp.std())
            veloce = fetta[fetta["strategia"] == "piu_veloce"]
            coincidenze.append(veloce["coincide_con_robusto"].mean() * 100)
            robusto = fetta[fetta["strategia"] == "robusto"].set_index("coppia")["probabilita"]
            rapido = veloce.set_index("coppia")["probabilita"]
            differenza = (robusto - rapido).dropna()
            guadagni.append(differenza.mean())
            guadagni_std.append(differenza.std())

        minuti = [m / 60 for m in margini]
        assi[0].errorbar(minuti, ampiezze_medie, yerr=ampiezze_std, color=colore,
                         marker=marcatore, linewidth=2, markersize=6, capsize=3,
                         label=citta.capitalize())
        assi[1].plot(minuti, coincidenze, color=colore, marker=marcatore,
                     linewidth=2, markersize=6, label=citta.capitalize())
        assi[2].errorbar(minuti, guadagni, yerr=guadagni_std, color=colore,
                         marker=marcatore, linewidth=2, markersize=6, capsize=3,
                         label=citta.capitalize())

    assi[0].set_ylabel("Ampiezza di P sulla frontiera")
    assi[0].set_title("(a) Quanto si distinguono gli itinerari", fontsize=10)
    assi[1].set_ylabel("Coincidenza (%)")
    assi[1].set_title("(b) Il piu' veloce e' anche il piu' robusto", fontsize=10)
    assi[1].set_ylim(0, 105)
    assi[2].set_ylabel("P(robusto) - P(piu' veloce)")
    assi[2].set_title("(c) Guadagno del criterio probabilistico", fontsize=10)
    assi[2].axhline(0, color="#555", linewidth=1, linestyle=":")
    for asse in assi:
        asse.set_xlabel("Margine sulla scadenza (minuti)")
        asse.grid(True, linewidth=0.4, alpha=0.35)
        asse.set_axisbelow(True)
        asse.legend(fontsize=8, frameon=False)

    figura.suptitle(
        "Pianificazione robusta al variare della scadenza T = arrivo del piu' veloce + margine\n"
        "MODELLO DEI RITARDI SINTETICO: i numeri qualificano il metodo, non il trasporto reale",
        fontsize=10.5,
    )
    figura.tight_layout(rect=(0, 0, 1, 0.88))
    destinazione.parent.mkdir(parents=True, exist_ok=True)
    figura.savefig(destinazione, dpi=150)
    plt.close(figura)


def disegna_metodi(dati: pd.DataFrame, destinazione: Path) -> None:
    figura, assi = plt.subplots(1, 2, figsize=(11, 4.4))
    for metodo, colore, marcatore in (("convoluzione", "#1f77b4", "o"),
                                      ("montecarlo", "#ff7f0e", "s")):
        parte = dati[dati["metodo"] == metodo]
        sintesi = parte.groupby("parametro", as_index=False).agg(
            errore=("errore", "mean"), errore_std=("errore", "std"), secondi=("secondi", "mean")
        )
        etichetta = "convoluzione (passo, s)" if metodo == "convoluzione" else "Monte Carlo (campioni)"
        assi[0].errorbar(sintesi["parametro"], sintesi["errore"], yerr=sintesi["errore_std"],
                         color=colore, marker=marcatore, linewidth=2, markersize=6, capsize=3,
                         label=etichetta)
        assi[1].plot(sintesi["secondi"], sintesi["errore"], color=colore, marker=marcatore,
                     linewidth=2, markersize=6, label=etichetta)
    assi[0].set_xscale("log"); assi[0].set_yscale("log")
    assi[0].set_xlabel("Parametro del metodo"); assi[0].set_ylabel("Errore su P")
    assi[0].set_title("(a) Accuratezza in funzione del parametro", fontsize=10)
    assi[1].set_xscale("log"); assi[1].set_yscale("log")
    assi[1].set_xlabel("Secondi per valutazione"); assi[1].set_ylabel("Errore su P")
    assi[1].set_title("(b) Accuratezza in funzione del costo", fontsize=10)
    for asse in assi:
        asse.grid(True, which="both", linewidth=0.4, alpha=0.35)
        asse.set_axisbelow(True)
        asse.legend(fontsize=8, frameon=False)
    figura.suptitle(
        "Convoluzione numerica contro Monte Carlo, su distribuzioni SINTETICHE\n"
        "riferimento: Monte Carlo con 200.000 campioni",
        fontsize=10.5,
    )
    figura.tight_layout(rect=(0, 0, 1, 0.86))
    figura.savefig(destinazione, dpi=150)
    plt.close(figura)


def main(argv: Sequence[str] | None = None) -> int:
    analizzatore = argparse.ArgumentParser(description=__doc__)
    analizzatore.add_argument("--citta", default="roma,torino")
    analizzatore.add_argument("--coppie", type=int, default=COPPIE)
    analizzatore.add_argument("--correlazione", type=float, default=0.7)
    analizzatore.add_argument(
        "--sintetico-ammesso", action="store_true",
        help="riconosce che i risultati saranno prodotti con ritardi inventati",
    )
    argomenti = analizzatore.parse_args(argv)

    modello = ModelloSintetico(correlazione=argomenti.correlazione)
    assicura_utilizzabile(modello, argomenti.sintetico_ammesso)

    RISULTATI.mkdir(parents=True, exist_ok=True)
    griglia: list[dict] = []
    metodi: list[dict] = []

    for citta in (c.strip() for c in argomenti.citta.split(",")):
        print(f"\n=== {citta} ===", flush=True)
        grafo, inizio = prepara(citta)
        coppie = coppie_valutabili(grafo, inizio, argomenti.coppie)
        print(f"  {len(coppie)} coppie con almeno due itinerari candidati", flush=True)
        griglia.extend(misura_griglia(citta, coppie, modello))
        metodi.extend(misura_metodi(citta, coppie, modello))

    dati_griglia = pd.DataFrame(griglia)
    dati_metodi = pd.DataFrame(metodi)
    dati_griglia.to_csv(RISULTATI / "robusto_griglia_T.csv", index=False)
    dati_metodi.to_csv(RISULTATI / "conv_vs_montecarlo.csv", index=False)
    disegna_griglia(dati_griglia, RISULTATI / "robusto_griglia_T.png")
    disegna_metodi(dati_metodi, RISULTATI / "conv_vs_montecarlo.png")

    print("\n=== Griglia dei margini (media +/- dev.std) ===")
    print(f"  {'citta':<8} {'margine':>8} {'ampiezza':>16} {'coincidenza':>13} {'guadagno':>18}")
    for citta in sorted(dati_griglia["citta"].unique()):
        parte = dati_griglia[dati_griglia["citta"] == citta]
        for margine in sorted(parte["margine_secondi"].unique()):
            fetta = parte[parte["margine_secondi"] == margine]
            amp = fetta.drop_duplicates("coppia")["ampiezza_frontiera"].dropna()
            veloce = fetta[fetta["strategia"] == "piu_veloce"]
            robusto = fetta[fetta["strategia"] == "robusto"].set_index("coppia")["probabilita"]
            rapido = veloce.set_index("coppia")["probabilita"]
            differenza = (robusto - rapido).dropna()
            print(f"  {citta:<8} {margine // 60:>6} min {amp.mean():>8.4f} +/- {amp.std():.4f}"
                  f" {veloce['coincide_con_robusto'].mean() * 100:>10.0f}%"
                  f" {differenza.mean():>10.4f} +/- {differenza.std():.4f}")

    print("\n=== Baseline a confronto (P media, tutte le coppie e i margini) ===")
    for citta in sorted(dati_griglia["citta"].unique()):
        parte = dati_griglia[dati_griglia["citta"] == citta]
        print(f"  {citta}:")
        for strategia in ("robusto", "piu_veloce", "margine_fisso", "meno_cambi"):
            fetta = parte[parte["strategia"] == strategia]
            print(f"    {strategia:<15} P = {fetta['probabilita'].mean():.4f} "
                  f"+/- {fetta['probabilita'].std():.4f}")

    print("\n=== Convoluzione contro Monte Carlo ===")
    for metodo in ("convoluzione", "montecarlo"):
        parte = dati_metodi[dati_metodi["metodo"] == metodo]
        for parametro in sorted(parte["parametro"].unique()):
            fetta = parte[parte["parametro"] == parametro]
            print(f"  {metodo:<13} {parametro:>7}: errore {fetta['errore'].mean():.5f} "
                  f"+/- {fetta['errore'].std():.5f}, {fetta['secondi'].mean() * 1000:7.1f} ms")
    tetto = dati_metodi["quota_tetto"].mean()
    print(f"\n  quota media di massa che esaurisce i recuperi: {tetto:.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
