"""Esperimenti della Fase 2: costo del grafo e confronto A* contro Dijkstra.

Produce quattro artefatti destinati al documento:

    results/grafo_finestra.csv    costo del grafo al crescere della finestra
    results/ricerca_astar.csv     una riga per query, dati grezzi
    results/ricerca_astar.png     figura a 150 dpi
    results/velocita_archi.csv    distribuzione delle velocita' fra fermate

Uso:
    python scripts/ricerca_confronto.py
    python scripts/ricerca_confronto.py --coppie 20 --citta torino
"""

from __future__ import annotations

import argparse
import random
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

from src.gtfs.loader import carica_archivio  # noqa: E402
from src.graph.search import cerca_frontiera_pareto, cerca_primo_arrivo  # noqa: E402
from src.graph.time_expanded import costruisci, velocita_massima  # noqa: E402

FINESTRE = (15, 30, 60, 120, 240)
ORIZZONTE = 120
COPPIE = 50
SEME = 20260826
ORA_PARTENZA = 8

COLORI = {"roma": "#1f77b4", "torino": "#ff7f0e"}
MARCATORI = {"roma": "o", "torino": "s"}
RISULTATI = RADICE / "results"


def archivio_piu_recente(citta: str) -> Path:
    archivi = sorted((RADICE / "data" / "raw" / "gtfs" / citta).glob("*.zip"))
    if not archivi:
        raise SystemExit(f"Nessun archivio GTFS per '{citta}'.")
    return archivi[-1]


def giorno_dell_archivio(percorso: Path) -> date:
    return date.fromisoformat(percorso.stem.split("_")[0])


def misura_grafo(citta: str, archivio, giorno: date, inizio: int) -> list[dict]:
    """Costo del grafo al crescere della finestra temporale."""
    righe = []
    for minuti in FINESTRE:
        for ripetizione in (1, 2, 3):
            avvio = datetime.now()
            grafo = costruisci(archivio, citta, giorno, inizio, minuti)
            durata = (datetime.now() - avvio).total_seconds()
            righe.append(
                {
                    "citta": citta,
                    "finestra_minuti": minuti,
                    "ripetizione": ripetizione,
                    "eventi": grafo.n_eventi,
                    "archi": grafo.n_archi(),
                    "memoria_mb": grafo.memoria_mb(),
                    "secondi_costruzione": durata,
                }
            )
        ultimo = righe[-1]
        print(
            f"  finestra {minuti:>4} min: {ultimo['eventi']:>8,} eventi, "
            f"{ultimo['archi']:>9,} archi, {ultimo['memoria_mb']:6.1f} MB, "
            f"{ultimo['secondi_costruzione']:5.2f}s",
            flush=True,
        )
    return righe


def coppie_casuali(grafo, quante: int, seme: int) -> list[tuple[str, str]]:
    """Coppie origine-destinazione fra fermate effettivamente servite.

    Il seme e' dichiarato perche' l'esperimento sia riproducibile. Si escludono
    le fermate senza partenze nella finestra: una coppia che parte da una fermata
    non servita non misura la ricerca, misura l'assenza di servizio.
    """
    generatore = random.Random(seme)
    servite = sorted(
        grafo.fermate[f] for f, v in grafo.partenze_per_fermata.items() if v.size >= 3
    )
    if len(servite) < 2:
        raise SystemExit("troppe poche fermate servite nella finestra")
    return [tuple(generatore.sample(servite, 2)) for _ in range(quante)]


def misura_ricerca(
    citta: str, grafo, inizio: int, velocita_max: float, velocita_p999: float, quante: int
) -> list[dict]:
    """Confronta le varianti della ricerca sulle stesse query, in formato lungo.

    Ogni riga porta il valore di ``V`` usato e se sia il massimo assoluto o un
    percentile, perche' un risultato prodotto con un'euristica non ammissibile
    resti riconoscibile come tale anche mesi dopo, guardando solo il CSV.

    La colonna ``ottimo`` e' il numero che conta davvero sulla variante non
    ammissibile: dice su quante query rinunciare alla garanzia costa davvero un
    itinerario peggiore, invece di lasciarlo come rischio teorico.
    """
    righe = []
    for indice, (origine, destinazione) in enumerate(coppie_casuali(grafo, quante, SEME), 1):
        esiti = {
            "astar_ammissibile": (
                cerca_primo_arrivo(grafo, origine, destinazione, inizio, velocita_max, True),
                True, velocita_max, "massimo",
            ),
            "dijkstra": (
                cerca_primo_arrivo(grafo, origine, destinazione, inizio, velocita_max, False),
                True, float("nan"), "nessuna",
            ),
            "astar_cambi_proiettati": (
                cerca_primo_arrivo(grafo, origine, destinazione, inizio, velocita_max, True,
                                   cambi_nello_stato=False),
                True, velocita_max, "massimo",
            ),
            "astar_p999": (
                cerca_primo_arrivo(grafo, origine, destinazione, inizio, velocita_p999, True),
                False, velocita_p999, "p99.9",
            ),
        }

        # L'ottimo e' quello di Dijkstra, che non usa alcuna euristica e quindi
        # non puo' essere influenzato da una stima sbagliata.
        riferimento = esiti["dijkstra"][0]
        if esiti["astar_ammissibile"][0].trovato and riferimento.trovato:
            if esiti["astar_ammissibile"][0].orario_arrivo != riferimento.orario_arrivo:
                raise SystemExit(
                    f"A* ammissibile discorda da Dijkstra su {origine}->{destinazione}: "
                    "l'euristica non e' ammissibile, il che contraddice la dimostrazione."
                )

        for nome, (esito, ammissibile, velocita, tipo) in esiti.items():
            righe.append(
                {
                    "citta": citta, "coppia": indice,
                    "origine": origine, "destinazione": destinazione,
                    "variante": nome,
                    "ammissibile": ammissibile,
                    "velocita_m_s": velocita,
                    "tipo_velocita": tipo,
                    "trovato": esito.trovato,
                    "minuti_arrivo": (esito.orario_arrivo - inizio) / 60 if esito.trovato else None,
                    "cambi": esito.cambi,
                    "espansi": esito.stati_espansi,
                    "secondi": esito.tempo_secondi,
                    "ottimo": (
                        None if not (esito.trovato and riferimento.trovato)
                        else esito.orario_arrivo == riferimento.orario_arrivo
                    ),
                    "pareto_soluzioni": None,
                }
            )

        pareto = cerca_frontiera_pareto(grafo, origine, destinazione, inizio)
        righe.append(
            {
                "citta": citta, "coppia": indice,
                "origine": origine, "destinazione": destinazione,
                "variante": "pareto", "ammissibile": True,
                "velocita_m_s": float("nan"), "tipo_velocita": "nessuna",
                "trovato": bool(pareto.frontiera),
                "minuti_arrivo": (min(e.orario_arrivo for e in pareto.frontiera) - inizio) / 60
                if pareto.frontiera else None,
                "cambi": None,
                "espansi": pareto.stati_espansi,
                "secondi": pareto.tempo_secondi,
                "ottimo": None,
                "pareto_soluzioni": len(pareto.frontiera),
            }
        )
        if indice % 10 == 0:
            print(f"    {indice}/{quante} coppie", flush=True)
    return righe


def _per_variante(ricerca: pd.DataFrame, citta: str, variante: str) -> pd.DataFrame:
    selezione = ricerca[(ricerca["citta"] == citta) & (ricerca["variante"] == variante)]
    return selezione.set_index("coppia")


def disegna(ricerca: pd.DataFrame, grafo_df: pd.DataFrame, destinazione: Path) -> None:
    figura, assi = plt.subplots(2, 2, figsize=(11.5, 8.5))
    citta_elenco = sorted(ricerca["citta"].unique())

    # (a) costo del grafo al crescere della finestra
    asse = assi[0][0]
    sintesi = grafo_df.groupby(["citta", "finestra_minuti"], as_index=False).agg(
        eventi=("eventi", "mean"), archi=("archi", "mean")
    )
    for citta in citta_elenco:
        serie = sintesi[sintesi["citta"] == citta].sort_values("finestra_minuti")
        asse.plot(serie["finestra_minuti"], serie["archi"], marker=MARCATORI.get(citta, "^"),
                  color=COLORI.get(citta, "#666"), linewidth=2, markersize=6,
                  label=f"{citta.capitalize()}, archi")
        asse.plot(serie["finestra_minuti"], serie["eventi"], linestyle="--",
                  marker=MARCATORI.get(citta, "^"), color=COLORI.get(citta, "#666"),
                  linewidth=1.5, markersize=5, alpha=0.7, label=f"{citta.capitalize()}, eventi")
    asse.set_xscale("log")
    asse.set_yscale("log")
    asse.set_xlabel("Finestra temporale (minuti)")
    asse.set_ylabel("Numero")
    asse.set_title("(a) Dimensione del grafo tempo-espanso", fontsize=10)
    asse.grid(True, which="both", linewidth=0.4, alpha=0.35)
    asse.set_axisbelow(True)
    asse.legend(fontsize=8, frameon=False)

    # (b) A* ammissibile contro Dijkstra
    asse = assi[0][1]
    for citta in citta_elenco:
        astar = _per_variante(ricerca, citta, "astar_ammissibile")
        dijkstra = _per_variante(ricerca, citta, "dijkstra")
        comuni = astar.index.intersection(dijkstra.index)
        risolte = astar.loc[comuni, "trovato"] & dijkstra.loc[comuni, "trovato"]
        asse.scatter(dijkstra.loc[comuni][risolte]["espansi"],
                     astar.loc[comuni][risolte]["espansi"],
                     s=24, alpha=0.65, color=COLORI.get(citta, "#666"),
                     marker=MARCATORI.get(citta, "^"), label=citta.capitalize())
    limiti = asse.get_xlim()
    asse.plot(limiti, limiti, color="#555", linewidth=1, linestyle=":", label="nessun risparmio")
    asse.set_xscale("log")
    asse.set_yscale("log")
    asse.set_xlabel("Stati espansi da Dijkstra")
    asse.set_ylabel("Stati espansi da A* ammissibile")
    asse.set_title("(b) Effetto dell'euristica ammissibile", fontsize=10)
    asse.grid(True, which="both", linewidth=0.4, alpha=0.35)
    asse.set_axisbelow(True)
    asse.legend(fontsize=8, frameon=False)

    # (c) risparmio a confronto: ammissibile contro non ammissibile
    asse = assi[1][0]
    etichette, dati, colori = [], [], []
    for citta in citta_elenco:
        dijkstra = _per_variante(ricerca, citta, "dijkstra")
        for variante, suffisso in (
            ("astar_ammissibile", "V max\n(ammissibile)"),
            ("astar_p999", "V p99,9\n(NON amm.)"),
        ):
            serie = _per_variante(ricerca, citta, variante)
            comuni = serie.index.intersection(dijkstra.index)
            risolte = serie.loc[comuni, "trovato"] & dijkstra.loc[comuni, "trovato"]
            risparmio = (1 - serie.loc[comuni][risolte]["espansi"]
                         / dijkstra.loc[comuni][risolte]["espansi"]) * 100
            etichette.append(f"{citta.capitalize()}\n{suffisso}")
            dati.append(risparmio.to_numpy())
            colori.append(COLORI.get(citta, "#666"))
    parti = asse.boxplot(dati, tick_labels=etichette, patch_artist=True, widths=0.55)
    for corpo, colore, nome in zip(parti["boxes"], colori, etichette):
        corpo.set_facecolor(colore)
        corpo.set_alpha(0.5 if "NON" in nome else 0.25)
        if "NON" in nome:
            corpo.set_hatch("//")
    asse.axhline(0, color="#555", linewidth=1, linestyle=":")
    asse.set_ylabel("Stati espansi risparmiati (%)")
    asse.set_title("(c) Risparmio per query. Il tratteggio NON garantisce l'ottimo", fontsize=9)
    asse.tick_params(axis="x", labelsize=7)
    asse.grid(True, axis="y", linewidth=0.4, alpha=0.35)
    asse.set_axisbelow(True)

    # (d) costo dei cambi nello stato
    asse = assi[1][1]
    for citta in citta_elenco:
        esteso = _per_variante(ricerca, citta, "astar_ammissibile")
        proiettato = _per_variante(ricerca, citta, "astar_cambi_proiettati")
        comuni = esteso.index.intersection(proiettato.index)
        risolte = esteso.loc[comuni, "trovato"] & proiettato.loc[comuni, "trovato"]
        asse.scatter(proiettato.loc[comuni][risolte]["espansi"],
                     esteso.loc[comuni][risolte]["espansi"],
                     s=24, alpha=0.65, color=COLORI.get(citta, "#666"),
                     marker=MARCATORI.get(citta, "^"), label=citta.capitalize())
    limiti = asse.get_xlim()
    asse.plot(limiti, limiti, color="#555", linewidth=1, linestyle=":", label="nessun costo")
    asse.set_xscale("log")
    asse.set_yscale("log")
    asse.set_xlabel("Stati espansi con i cambi proiettati via")
    asse.set_ylabel("Stati espansi con i cambi nello stato")
    asse.set_title("(d) Cambi nello stato: costa 3x, ma la proiezione sbaglia", fontsize=9)
    asse.grid(True, which="both", linewidth=0.4, alpha=0.35)
    asse.set_axisbelow(True)
    asse.legend(fontsize=8, frameon=False)

    risolte_totali = int(
        ricerca[(ricerca["variante"] == "astar_ammissibile") & ricerca["trovato"]].shape[0]
    )
    interrogazioni = int(ricerca["coppia"].max()) * len(citta_elenco)
    figura.suptitle(
        "Ricerca di itinerari: costo del grafo ed effetto dell'euristica\n"
        f"{risolte_totali} query risolte su {interrogazioni}, finestra di {ORIZZONTE} minuti, "
        f"partenza alle {ORA_PARTENZA:02d}:00",
        fontsize=11,
    )
    figura.tight_layout(rect=(0, 0, 1, 0.93))
    destinazione.parent.mkdir(parents=True, exist_ok=True)
    figura.savefig(destinazione, dpi=150)
    plt.close(figura)


def riassumi(ricerca: pd.DataFrame) -> None:
    """Stampa media e deviazione standard per ogni variante e citta'."""
    for citta in sorted(ricerca["citta"].unique()):
        dijkstra = _per_variante(ricerca, citta, "dijkstra")
        totale = int(dijkstra.shape[0])
        print(f"\n  {citta}:")
        for variante in ("astar_ammissibile", "dijkstra", "astar_cambi_proiettati", "astar_p999"):
            serie = _per_variante(ricerca, citta, variante)
            comuni = serie.index.intersection(dijkstra.index)
            risolte = serie.loc[comuni, "trovato"] & dijkstra.loc[comuni, "trovato"]
            selezione = serie.loc[comuni][risolte]
            confronto = dijkstra.loc[comuni][risolte]
            risparmio = (1 - selezione["espansi"] / confronto["espansi"]) * 100
            marchio = "" if bool(serie["ammissibile"].iloc[0]) else "   [NON AMMISSIBILE]"
            print(f"    {variante}{marchio}")
            print(f"      V usata              : {serie['velocita_m_s'].iloc[0]:.2f} m/s "
                  f"({serie['tipo_velocita'].iloc[0]})")
            print(f"      stati espansi        : {selezione['espansi'].mean():>10,.0f} "
                  f"+/- {selezione['espansi'].std():,.0f}")
            print(f"      secondi              : {selezione['secondi'].mean():>10.3f} "
                  f"+/- {selezione['secondi'].std():.3f}")
            print(f"      risparmio su Dijkstra: {risparmio.mean():>9.1f}% "
                  f"+/- {risparmio.std():.1f}%")
            non_ottime = int((selezione["ottimo"] == False).sum())  # noqa: E712
            print(f"      query NON ottime     : {non_ottime} su {len(selezione)}")
        risolte_tot = int(dijkstra["trovato"].sum())
        print(f"    coppie risolte nella finestra: {risolte_tot}/{totale} "
              f"({risolte_tot / totale:.0%})")
        pareto = _per_variante(ricerca, citta, "pareto")
        soluzioni = pareto[pareto["trovato"]]["pareto_soluzioni"]
        print(f"    soluzioni di Pareto          : {soluzioni.mean():.2f} "
              f"+/- {soluzioni.std():.2f}")


def main(argv: Sequence[str] | None = None) -> int:
    analizzatore = argparse.ArgumentParser(description=__doc__)
    analizzatore.add_argument("--citta", default="roma,torino")
    analizzatore.add_argument("--coppie", type=int, default=COPPIE)
    argomenti = analizzatore.parse_args(argv)

    RISULTATI.mkdir(parents=True, exist_ok=True)
    righe_grafo: list[dict] = []
    righe_ricerca: list[dict] = []
    righe_velocita: list[dict] = []

    for citta in (c.strip() for c in argomenti.citta.split(",")):
        percorso = archivio_piu_recente(citta)
        giorno = giorno_dell_archivio(percorso)
        print(f"\n=== {citta} ({percorso.name}, servizio del {giorno}) ===", flush=True)
        archivio = carica_archivio(percorso, con_stop_times=True)

        misura = velocita_massima(archivio)
        misura["citta"] = citta
        righe_velocita.append(misura)
        print(
            f"  velocita' fra fermate: mediana {misura['p50'] * 3.6:.1f} km/h, "
            f"p99 {misura['p99'] * 3.6:.1f}, MASSIMO {misura['massimo_km_h']:.0f} km/h "
            f"({misura['oltre_150_km_h']:.0f} archi oltre 150 km/h)",
            flush=True,
        )

        inizio = int(
            datetime(giorno.year, giorno.month, giorno.day, ORA_PARTENZA, 0,
                     tzinfo=ZoneInfo("Europe/Rome")).timestamp()
        )
        righe_grafo.extend(misura_grafo(citta, archivio, giorno, inizio))

        grafo = costruisci(archivio, citta, giorno, inizio, ORIZZONTE)
        print(f"  ricerca su {argomenti.coppie} coppie...", flush=True)
        righe_ricerca.extend(
            misura_ricerca(
                citta, grafo, inizio, misura["massimo_m_s"], misura["p999"], argomenti.coppie
            )
        )

    grafo_df = pd.DataFrame(righe_grafo)
    ricerca_df = pd.DataFrame(righe_ricerca)
    pd.DataFrame(righe_velocita).to_csv(RISULTATI / "velocita_archi.csv", index=False)
    grafo_df.to_csv(RISULTATI / "grafo_finestra.csv", index=False)
    ricerca_df.to_csv(RISULTATI / "ricerca_astar.csv", index=False)
    disegna(ricerca_df, grafo_df, RISULTATI / "ricerca_astar.png")

    print("\n=== Sintesi (media +/- dev.std) ===")
    riassumi(ricerca_df)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
