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


def misura_ricerca(citta: str, grafo, inizio: int, velocita: float, quante: int) -> list[dict]:
    """Confronto A* contro Dijkstra, piu' il costo dei cambi nello stato."""
    righe = []
    for indice, (origine, destinazione) in enumerate(coppie_casuali(grafo, quante, SEME), 1):
        astar = cerca_primo_arrivo(grafo, origine, destinazione, inizio, velocita, True)
        dijkstra = cerca_primo_arrivo(grafo, origine, destinazione, inizio, velocita, False)
        proiettato = cerca_primo_arrivo(
            grafo, origine, destinazione, inizio, velocita, True, cambi_nello_stato=False
        )
        pareto = cerca_frontiera_pareto(grafo, origine, destinazione, inizio)

        if astar.trovato and dijkstra.trovato and astar.orario_arrivo != dijkstra.orario_arrivo:
            raise SystemExit(
                f"A* e Dijkstra discordano su {origine}->{destinazione}: "
                f"{astar.orario_arrivo} contro {dijkstra.orario_arrivo}. "
                "L'euristica non e' ammissibile."
            )

        righe.append(
            {
                "citta": citta,
                "coppia": indice,
                "origine": origine,
                "destinazione": destinazione,
                "trovato": astar.trovato,
                "minuti_arrivo": (astar.orario_arrivo - inizio) / 60 if astar.trovato else None,
                "cambi": astar.cambi,
                "astar_espansi": astar.stati_espansi,
                "astar_secondi": astar.tempo_secondi,
                "dijkstra_espansi": dijkstra.stati_espansi,
                "dijkstra_secondi": dijkstra.tempo_secondi,
                "proiettato_espansi": proiettato.stati_espansi,
                "pareto_soluzioni": len(pareto.frontiera),
                "pareto_secondi": pareto.tempo_secondi,
            }
        )
        if indice % 10 == 0:
            print(f"    {indice}/{quante} coppie", flush=True)
    return righe


def disegna(ricerca: pd.DataFrame, grafo_df: pd.DataFrame, destinazione: Path) -> None:
    figura, assi = plt.subplots(2, 2, figsize=(11, 8.5))

    # (a) costo del grafo al crescere della finestra
    asse = assi[0][0]
    sintesi = grafo_df.groupby(["citta", "finestra_minuti"], as_index=False).agg(
        eventi=("eventi", "mean"), archi=("archi", "mean"), memoria=("memoria_mb", "mean")
    )
    for citta in sorted(sintesi["citta"].unique()):
        serie = sintesi[sintesi["citta"] == citta].sort_values("finestra_minuti")
        asse.plot(serie["finestra_minuti"], serie["archi"], marker=MARCATORI.get(citta, "^"),
                  color=COLORI.get(citta, "#666"), linewidth=2, markersize=6,
                  label=f"{citta.capitalize()}, archi")
        asse.plot(serie["finestra_minuti"], serie["eventi"], linestyle="--",
                  marker=MARCATORI.get(citta, "^"), color=COLORI.get(citta, "#666"),
                  linewidth=1.5, markersize=5, label=f"{citta.capitalize()}, eventi")
    asse.set_xscale("log"); asse.set_yscale("log")
    asse.set_xlabel("Finestra temporale (minuti)"); asse.set_ylabel("Numero")
    asse.set_title("(a) Dimensione del grafo tempo-espanso", fontsize=10)
    asse.grid(True, which="both", linewidth=0.4, alpha=0.35); asse.set_axisbelow(True)
    asse.legend(fontsize=8, frameon=False)

    # (b) nodi espansi, A* contro Dijkstra
    asse = assi[0][1]
    trovate = ricerca[ricerca["trovato"]]
    for posizione, citta in enumerate(sorted(trovate["citta"].unique())):
        serie = trovate[trovate["citta"] == citta]
        asse.scatter(serie["dijkstra_espansi"], serie["astar_espansi"], s=22, alpha=0.65,
                     color=COLORI.get(citta, "#666"), marker=MARCATORI.get(citta, "^"),
                     label=citta.capitalize())
    limite = [1, float(max(trovate["dijkstra_espansi"].max(), 1))]
    asse.plot(limite, limite, color="#555", linewidth=1, linestyle=":", label="nessun risparmio")
    asse.set_xscale("log"); asse.set_yscale("log")
    asse.set_xlabel("Stati espansi da Dijkstra"); asse.set_ylabel("Stati espansi da A*")
    asse.set_title("(b) Effetto dell'euristica geografica", fontsize=10)
    asse.grid(True, which="both", linewidth=0.4, alpha=0.35); asse.set_axisbelow(True)
    asse.legend(fontsize=8, frameon=False)

    # (c) distribuzione del risparmio
    asse = assi[1][0]
    dati = [
        (1 - trovate[trovate["citta"] == c]["astar_espansi"]
         / trovate[trovate["citta"] == c]["dijkstra_espansi"]) * 100
        for c in sorted(trovate["citta"].unique())
    ]
    parti = asse.boxplot(dati, tick_labels=[c.capitalize() for c in sorted(trovate["citta"].unique())],
                         patch_artist=True, widths=0.5)
    for corpo, citta in zip(parti["boxes"], sorted(trovate["citta"].unique())):
        corpo.set_facecolor(COLORI.get(citta, "#666")); corpo.set_alpha(0.35)
    asse.axhline(0, color="#555", linewidth=1, linestyle=":")
    asse.set_ylabel("Stati espansi risparmiati (%)")
    asse.set_title("(c) Risparmio dell'euristica, per query", fontsize=10)
    asse.grid(True, axis="y", linewidth=0.4, alpha=0.35); asse.set_axisbelow(True)

    # (d) costo dei cambi nello stato
    asse = assi[1][1]
    for citta in sorted(trovate["citta"].unique()):
        serie = trovate[trovate["citta"] == citta]
        asse.scatter(serie["proiettato_espansi"], serie["astar_espansi"], s=22, alpha=0.65,
                     color=COLORI.get(citta, "#666"), marker=MARCATORI.get(citta, "^"),
                     label=citta.capitalize())
    limite = [1, float(max(trovate["proiettato_espansi"].max(), 1))]
    asse.plot(limite, limite, color="#555", linewidth=1, linestyle=":", label="nessun costo")
    asse.set_xscale("log"); asse.set_yscale("log")
    asse.set_xlabel("Stati espansi con i cambi proiettati via")
    asse.set_ylabel("Stati espansi con i cambi nello stato")
    asse.set_title("(d) Costo dei cambi nello stato", fontsize=10)
    asse.grid(True, which="both", linewidth=0.4, alpha=0.35); asse.set_axisbelow(True)
    asse.legend(fontsize=8, frameon=False)

    figura.suptitle(
        "Ricerca di itinerari: costo del grafo ed effetto dell'euristica\n"
        f"{len(trovate)} query risolte, finestra di {ORIZZONTE} minuti, partenza alle "
        f"{ORA_PARTENZA:02d}:00",
        fontsize=11,
    )
    figura.tight_layout(rect=(0, 0, 1, 0.93))
    destinazione.parent.mkdir(parents=True, exist_ok=True)
    figura.savefig(destinazione, dpi=150)
    plt.close(figura)


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
            misura_ricerca(citta, grafo, inizio, misura["massimo_m_s"], argomenti.coppie)
        )

    grafo_df = pd.DataFrame(righe_grafo)
    ricerca_df = pd.DataFrame(righe_ricerca)
    pd.DataFrame(righe_velocita).to_csv(RISULTATI / "velocita_archi.csv", index=False)
    grafo_df.to_csv(RISULTATI / "grafo_finestra.csv", index=False)
    ricerca_df.to_csv(RISULTATI / "ricerca_astar.csv", index=False)
    disegna(ricerca_df, grafo_df, RISULTATI / "ricerca_astar.png")

    print("\n=== Sintesi (media +/- dev.std) ===")
    for citta in sorted(ricerca_df["citta"].unique()):
        serie = ricerca_df[(ricerca_df["citta"] == citta) & ricerca_df["trovato"]]
        totale = int((ricerca_df["citta"] == citta).sum())
        risparmio = (1 - serie["astar_espansi"] / serie["dijkstra_espansi"]) * 100
        costo_cambi = serie["astar_espansi"] / serie["proiettato_espansi"]
        print(f"  {citta}:")
        print(f"    coppie risolte nella finestra : {len(serie)}/{totale} "
              f"({len(serie) / totale:.0%})")
        print(f"    stati espansi A*              : {serie['astar_espansi'].mean():>10,.0f} "
              f"+/- {serie['astar_espansi'].std():,.0f}")
        print(f"    stati espansi Dijkstra        : {serie['dijkstra_espansi'].mean():>10,.0f} "
              f"+/- {serie['dijkstra_espansi'].std():,.0f}")
        print(f"    risparmio dell'euristica      : {risparmio.mean():>9.1f}% "
              f"+/- {risparmio.std():.1f}%")
        print(f"    tempo A*                      : {serie['astar_secondi'].mean():>10.3f} s "
              f"+/- {serie['astar_secondi'].std():.3f}")
        print(f"    tempo Dijkstra                : {serie['dijkstra_secondi'].mean():>10.3f} s "
              f"+/- {serie['dijkstra_secondi'].std():.3f}")
        print(f"    cambi nello stato, fattore    : {costo_cambi.mean():>10.2f}x "
              f"+/- {costo_cambi.std():.2f}")
        print(f"    soluzioni di Pareto           : {serie['pareto_soluzioni'].mean():>10.2f} "
              f"+/- {serie['pareto_soluzioni'].std():.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
