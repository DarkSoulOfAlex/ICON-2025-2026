"""Curva di complessita' della base di conoscenza.

Misura come crescono atomi generati, tempo di grounding e tempo di solving al
crescere del numero di fermate, su entrambe le citta' del progetto, e produce i
due artefatti destinati al documento:

    results/complessita_kb.csv   dati grezzi, una riga per ripetizione
    results/complessita_kb.png   figura a 150 dpi

Oltre alla curva principale misura due varianti, che servono a **attribuire** il
costo invece di dedurlo:

* ``senza_indice`` confronta tutte le coppie di fermate anziche' le sole celle
  adiacenti. Serve a due cose: quantificare il risparmio dell'indice spaziale e
  verificare che l'insieme dei trasbordi derivati sia identico, cioe' che
  l'indice non alteri la semantica. Gira solo sulle dimensioni piccole, perche'
  a 2000 fermate richiederebbe quattro milioni di coppie.
* ``senza_chiusura`` disattiva la ricorsione. La differenza rispetto alla curva
  completa misura quanti atomi nascano dalla sola chiusura transitiva, che e' la
  risposta alla domanda "quale regola domina il grounding".

Uso:
    python scripts/complessita_kb.py
    python scripts/complessita_kb.py --ripetizioni 5 --dimensioni 50,150,400
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Sequence

RADICE = Path(__file__).resolve().parent.parent
if str(RADICE) not in sys.path:
    sys.path.insert(0, str(RADICE))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

from src.gtfs.loader import carica_archivio, fermate_fisiche  # noqa: E402
from src.kb.engine import (  # noqa: E402
    esegui,
    fermata_centrale,
    genera_fatti,
    sottoinsieme_per_prossimita,
)

DIMENSIONI_PREDEFINITE = (50, 150, 400, 1000, 2000)
RIPETIZIONI_PREDEFINITE = 3

# Oltre questa dimensione la variante esaustiva istanzierebbe milioni di coppie
# senza aggiungere informazione: la sua curva e' gia' leggibile sotto.
LIMITE_SENZA_INDICE = 400

# Palette a due serie, verificata con lo strumento di validazione: separazione
# CVD 24,6 (protanopia) e 35,7 a visione normale, ampiamente sopra le soglie.
# I marcatori sono diversi per serie, cosi' l'identita' non e' affidata al solo
# colore ne' in stampa in bianco e nero.
COLORI = {"roma": "#1f77b4", "torino": "#ff7f0e"}
MARCATORI = {"roma": "o", "torino": "s"}

CARTELLA_RISULTATI = RADICE / "results"


@dataclass
class Misura:
    citta: str
    variante: str
    fermate_richieste: int
    fermate_effettive: int
    ripetizione: int
    soddisfacibile: bool
    atomi: int
    regole: int
    tempo_grounding: float
    tempo_solving: float
    trasbordi: int


def archivio_piu_recente(citta: str) -> Path:
    cartella = RADICE / "data" / "raw" / "gtfs" / citta
    archivi = sorted(cartella.glob("*.zip"))
    if not archivi:
        raise SystemExit(
            f"Nessun archivio GTFS per '{citta}' in {cartella}. "
            "La raccolta deve averne scaricato almeno uno."
        )
    return archivi[-1]


def misura_citta(
    citta: str, dimensioni: Sequence[int], ripetizioni: int
) -> tuple[list[Misura], list[str]]:
    """Esegue la griglia di misure per una citta'. Restituisce anche le note."""
    note: list[str] = []
    percorso = archivio_piu_recente(citta)
    print(f"\n=== {citta} ({percorso.name}) ===")
    archivio = carica_archivio(percorso, con_stop_times=True)
    fermate = fermate_fisiche(archivio.stops)
    centro = fermata_centrale(fermate)
    nome_centro = str(archivio.stops.loc[archivio.stops["stop_id"] == centro, "stop_name"].iloc[0])
    print(f"  {len(fermate):,} fermate fisiche | centro del campionamento: {centro} ({nome_centro})")
    note.append(f"{citta}: centro {centro} ({nome_centro}), {len(fermate):,} fermate disponibili")

    misure: list[Misura] = []
    for quante in dimensioni:
        if quante > len(fermate):
            note.append(f"{citta}: {quante} fermate non disponibili, dimensione saltata")
            continue
        sottoinsieme = sottoinsieme_per_prossimita(fermate, quante, centro)
        fatti = genera_fatti(archivio, stops=sottoinsieme)

        varianti = [("completa", True, True), ("senza_chiusura", True, False)]
        if quante <= LIMITE_SENZA_INDICE:
            varianti.append(("senza_indice", False, True))

        riferimento = None
        for nome, con_indice, con_chiusura in varianti:
            for ripetizione in range(1, ripetizioni + 1):
                risultato = esegui(
                    fatti, con_indice=con_indice, con_chiusura=con_chiusura
                )
                misure.append(
                    Misura(
                        citta=citta,
                        variante=nome,
                        fermate_richieste=quante,
                        fermate_effettive=len(sottoinsieme),
                        ripetizione=ripetizione,
                        soddisfacibile=risultato.soddisfacibile,
                        atomi=risultato.atomi,
                        regole=risultato.regole,
                        tempo_grounding=risultato.tempo_grounding,
                        tempo_solving=risultato.tempo_solving,
                        trasbordi=len(risultato.trasbordi),
                    )
                )
                if nome == "completa" and ripetizione == 1:
                    riferimento = risultato.trasbordi
                # La verifica che conta: l'indice non deve cambiare il risultato.
                if nome == "senza_indice" and ripetizione == 1 and riferimento is not None:
                    identici = riferimento.equals(risultato.trasbordi)
                    note.append(
                        f"{citta} n={quante}: trasbordi con e senza indice "
                        f"{'IDENTICI' if identici else 'DIVERSI (!)'}"
                    )
                    if not identici:
                        raise SystemExit(
                            "L'indice spaziale ha cambiato l'insieme dei trasbordi derivati: "
                            "l'affermazione di neutralita' semantica non regge e va indagata."
                        )
        ultima = [m for m in misure if m.fermate_richieste == quante and m.variante == "completa"]
        print(
            f"  n={quante:>5}: {ultima[-1].atomi:>10,} atomi, "
            f"grounding {ultima[-1].tempo_grounding:6.2f}s, "
            f"solving {ultima[-1].tempo_solving:6.3f}s, "
            f"{ultima[-1].trasbordi:>7,} trasbordi"
        )
    return misure, note


def riassumi(dati: pd.DataFrame) -> pd.DataFrame:
    """Media e deviazione standard per ogni combinazione citta' x dimensione x variante."""
    return (
        dati.groupby(["citta", "variante", "fermate_richieste"], as_index=False)
        .agg(
            fermate=("fermate_effettive", "first"),
            atomi_media=("atomi", "mean"),
            atomi_std=("atomi", "std"),
            grounding_media=("tempo_grounding", "mean"),
            grounding_std=("tempo_grounding", "std"),
            solving_media=("tempo_solving", "mean"),
            solving_std=("tempo_solving", "std"),
            trasbordi=("trasbordi", "first"),
            ripetizioni=("ripetizione", "count"),
        )
        .fillna({"atomi_std": 0.0, "grounding_std": 0.0, "solving_std": 0.0})
    )


def _pannello(
    asse,
    sintesi: pd.DataFrame,
    colonna_media: str,
    colonna_std: str,
    titolo: str,
    etichetta_y: str,
    variante: str = "completa",
) -> None:
    for citta in sorted(sintesi["citta"].unique()):
        serie = sintesi[(sintesi["citta"] == citta) & (sintesi["variante"] == variante)]
        serie = serie.sort_values("fermate")
        if serie.empty:
            continue
        asse.errorbar(
            serie["fermate"],
            serie[colonna_media],
            yerr=serie[colonna_std],
            label=citta.capitalize(),
            color=COLORI.get(citta, "#666666"),
            marker=MARCATORI.get(citta, "^"),
            markersize=6,
            linewidth=2,
            capsize=3,
        )
    asse.set_xscale("log")
    asse.set_yscale("log")
    asse.set_xlabel("Numero di fermate")
    asse.set_ylabel(etichetta_y)
    asse.set_title(titolo, fontsize=10)
    asse.grid(True, which="both", linewidth=0.4, alpha=0.35)
    asse.set_axisbelow(True)


def disegna(sintesi: pd.DataFrame, destinazione: Path) -> None:
    figura, assi = plt.subplots(2, 2, figsize=(11, 8.5))

    _pannello(assi[0][0], sintesi, "atomi_media", "atomi_std", "(a) Atomi generati", "Atomi")
    _pannello(
        assi[0][1], sintesi, "grounding_media", "grounding_std",
        "(b) Tempo di grounding", "Secondi",
    )
    _pannello(
        assi[1][0], sintesi, "solving_media", "solving_std",
        "(c) Tempo di solving", "Secondi",
    )

    # Pannello (d): il costo dell'indice spaziale, sulle sole dimensioni in cui
    # la variante esaustiva e' stata eseguita.
    asse = assi[1][1]
    for citta in sorted(sintesi["citta"].unique()):
        for variante, stile, etichetta in (
            ("completa", "-", "con indice"),
            ("senza_indice", "--", "senza indice"),
        ):
            serie = sintesi[(sintesi["citta"] == citta) & (sintesi["variante"] == variante)]
            serie = serie.sort_values("fermate")
            if serie.empty:
                continue
            asse.plot(
                serie["fermate"],
                serie["atomi_media"],
                stile,
                color=COLORI.get(citta, "#666666"),
                marker=MARCATORI.get(citta, "^"),
                markersize=6,
                linewidth=2,
                label=f"{citta.capitalize()}, {etichetta}",
            )
    asse.set_xscale("log")
    asse.set_yscale("log")
    asse.set_xlabel("Numero di fermate")
    asse.set_ylabel("Atomi")
    asse.set_title("(d) Costo dell'indice spaziale", fontsize=10)
    asse.grid(True, which="both", linewidth=0.4, alpha=0.35)
    asse.set_axisbelow(True)
    asse.legend(fontsize=8, frameon=False)

    for riga in assi[:1]:
        for singolo in riga:
            singolo.legend(fontsize=9, frameon=False)
    assi[1][0].legend(fontsize=9, frameon=False)

    figura.suptitle(
        "Complessita' della base di conoscenza al crescere della rete\n"
        "media e deviazione standard su ripetizioni indipendenti, scala doppio logaritmica",
        fontsize=11,
    )
    figura.tight_layout(rect=(0, 0, 1, 0.94))
    destinazione.parent.mkdir(parents=True, exist_ok=True)
    figura.savefig(destinazione, dpi=150)
    plt.close(figura)


def main(argv: Sequence[str] | None = None) -> int:
    analizzatore = argparse.ArgumentParser(description=__doc__)
    analizzatore.add_argument("--citta", default="roma,torino")
    analizzatore.add_argument(
        "--dimensioni", default=",".join(str(d) for d in DIMENSIONI_PREDEFINITE)
    )
    analizzatore.add_argument("--ripetizioni", type=int, default=RIPETIZIONI_PREDEFINITE)
    argomenti = analizzatore.parse_args(argv)

    dimensioni = tuple(int(d) for d in argomenti.dimensioni.split(","))
    citta = tuple(c.strip() for c in argomenti.citta.split(","))

    misure: list[Misura] = []
    note: list[str] = []
    for nome in citta:
        parziali, note_citta = misura_citta(nome, dimensioni, argomenti.ripetizioni)
        misure.extend(parziali)
        note.extend(note_citta)

    dati = pd.DataFrame([asdict(m) for m in misure])
    CARTELLA_RISULTATI.mkdir(parents=True, exist_ok=True)
    percorso_csv = CARTELLA_RISULTATI / "complessita_kb.csv"
    dati.to_csv(percorso_csv, index=False)

    sintesi = riassumi(dati)
    disegna(sintesi, CARTELLA_RISULTATI / "complessita_kb.png")

    print("\n=== Sintesi (media +/- dev.std) ===")
    completa = sintesi[sintesi["variante"] == "completa"].sort_values(["citta", "fermate"])
    for riga in completa.itertuples(index=False):
        print(
            f"  {riga.citta:>7} n={riga.fermate:>5}: "
            f"{riga.atomi_media:>12,.0f} atomi +/- {riga.atomi_std:,.0f} | "
            f"grounding {riga.grounding_media:6.3f} +/- {riga.grounding_std:.3f} s | "
            f"solving {riga.solving_media:6.4f} +/- {riga.solving_std:.4f} s"
        )

    print("\n=== Quota di atomi dovuta alla chiusura transitiva ===")
    for citta_nome in sorted(sintesi["citta"].unique()):
        for dimensione in sorted(sintesi["fermate_richieste"].unique()):
            tutto = sintesi[
                (sintesi["citta"] == citta_nome)
                & (sintesi["fermate_richieste"] == dimensione)
            ]
            con = tutto[tutto["variante"] == "completa"]["atomi_media"]
            senza = tutto[tutto["variante"] == "senza_chiusura"]["atomi_media"]
            if con.empty or senza.empty:
                continue
            quota = 1.0 - float(senza.iloc[0]) / float(con.iloc[0])
            print(
                f"  {citta_nome:>7} n={dimensione:>5}: "
                f"{float(con.iloc[0]):>12,.0f} con chiusura, {float(senza.iloc[0]):>10,.0f} senza "
                f"-> {quota:6.1%} degli atomi nasce dalla ricorsione"
            )

    print("\n=== Note ===")
    for riga in note:
        print(f"  {riga}")
    print(f"\nScritti {percorso_csv} e {CARTELLA_RISULTATI / 'complessita_kb.png'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
