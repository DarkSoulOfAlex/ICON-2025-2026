"""Ogni nome usato negli script deve esistere, anche nei rami mai eseguiti in locale.

**Perche' questo test esiste.** Gli script di `scripts/` hanno rami che i dati di
sviluppo non attraversano: un ramo che si apre solo in presenza di righe anomale,
o solo su una citta', o solo attorno alla mezzanotte. Un nome cancellato per
sbaglio dentro uno di quei rami non fa fallire nulla in locale - il ramo non entra
mai in funzione - e si manifesta soltanto sulla macchina di raccolta, dopo un
trasferimento e un'esecuzione. E' gia' successo due volte con la stessa funzione,
e il collaudo sui dati locali per costruzione non puo' vederlo.

Il controllo e' statico e non esegue nulla: costruisce l'albero degli ambiti di
ciascun modulo e verifica che ogni nome letto sia risolvibile fra le variabili
locali, quelle delle funzioni che lo racchiudono, quelle del modulo e le
incorporate. E' una versione ridotta di cio' che farebbe pyflakes, scritta a mano
perche' lo stack del progetto e' chiuso e non vale una dipendenza in piu' per un
solo controllo.

**Cosa non copre**, dichiarato per non dargli piu' credito di quanto ne meriti: le
annotazioni di tipo, che con ``from __future__ import annotations`` non vengono
valutate e possono contenere riferimenti in avanti legittimi; gli attributi, di
cui si verifica solo la radice; e i nomi introdotti da ``import *``, che il
progetto non usa.
"""

from __future__ import annotations

import ast
import builtins
import importlib
import sys
from pathlib import Path

import pytest

RADICE = Path(__file__).resolve().parents[1]
CARTELLA = RADICE / "scripts"
INCORPORATI = set(dir(builtins)) | {"__file__", "__name__", "__doc__", "__spec__", "__package__"}

SCRIPT = sorted(p for p in CARTELLA.glob("*.py") if not p.name.startswith("_"))


class Ambito:
    """Un ambito di nomi, con il riferimento a quello che lo racchiude."""

    def __init__(self, tipo: str, genitore: "Ambito | None" = None) -> None:
        self.tipo = tipo  # modulo | funzione | classe | comprensione
        self.genitore = genitore
        self.nomi: set[str] = set()
        self.globali: set[str] = set()

    def dichiara(self, nome: str | None) -> None:
        if nome:
            self.nomi.add(nome)

    def risolve(self, nome: str) -> bool:
        if nome in INCORPORATI:
            return True
        corrente: Ambito | None = self
        primo = True
        while corrente is not None:
            # Il corpo di una classe non e' visibile alle funzioni annidate: lo si
            # consulta solo se e' l'ambito in cui il nome viene letto.
            if corrente.tipo != "classe" or primo:
                if nome in corrente.nomi or nome in corrente.globali:
                    return True
            corrente = corrente.genitore
            primo = False
        return False


def _bersagli(nodo: ast.AST) -> list[str]:
    """Nomi legati da un bersaglio di assegnamento, anche annidato."""
    if isinstance(nodo, ast.Name):
        return [nodo.id]
    if isinstance(nodo, (ast.Tuple, ast.List)):
        return [n for elemento in nodo.elts for n in _bersagli(elemento)]
    if isinstance(nodo, ast.Starred):
        return _bersagli(nodo.value)
    return []


def _dichiara_argomenti(ambito: Ambito, argomenti: ast.arguments) -> None:
    for gruppo in (argomenti.posonlyargs, argomenti.args, argomenti.kwonlyargs):
        for argomento in gruppo:
            ambito.dichiara(argomento.arg)
    for opzionale in (argomenti.vararg, argomenti.kwarg):
        if opzionale is not None:
            ambito.dichiara(opzionale.arg)


def _raccogli(corpo: list[ast.stmt] | ast.AST, ambito: Ambito) -> None:
    """Registra nell'ambito tutti i nomi che vi vengono legati.

    Si ferma alle funzioni e alle classi annidate, di cui registra il solo nome:
    il loro interno e' un ambito a se' e viene percorso separatamente.
    """
    nodi = corpo if isinstance(corpo, list) else [corpo]
    for radice in nodi:
        for nodo in ast.walk(radice):
            if isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                ambito.dichiara(nodo.name)
            elif isinstance(nodo, (ast.Import, ast.ImportFrom)):
                for alias in nodo.names:
                    ambito.dichiara(alias.asname or alias.name.split(".")[0])
            elif isinstance(nodo, ast.Assign):
                for bersaglio in nodo.targets:
                    for nome in _bersagli(bersaglio):
                        ambito.dichiara(nome)
            elif isinstance(nodo, (ast.AnnAssign, ast.AugAssign)):
                for nome in _bersagli(nodo.target):
                    ambito.dichiara(nome)
            elif isinstance(nodo, ast.NamedExpr):
                for nome in _bersagli(nodo.target):
                    ambito.dichiara(nome)
            elif isinstance(nodo, (ast.For, ast.AsyncFor)):
                for nome in _bersagli(nodo.target):
                    ambito.dichiara(nome)
            elif isinstance(nodo, (ast.With, ast.AsyncWith)):
                for elemento in nodo.items:
                    if elemento.optional_vars is not None:
                        for nome in _bersagli(elemento.optional_vars):
                            ambito.dichiara(nome)
            elif isinstance(nodo, ast.ExceptHandler):
                ambito.dichiara(nodo.name)
            elif isinstance(nodo, (ast.Global, ast.Nonlocal)):
                ambito.globali.update(nodo.names)
            elif isinstance(nodo, comprehension_nodi):
                for generatore in nodo.generators:
                    for nome in _bersagli(generatore.target):
                        ambito.dichiara(nome)


comprehension_nodi = (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)


def _letti(nodo: ast.AST) -> set[str]:
    """Nomi letti direttamente in un nodo, escluse le annotazioni.

    Le annotazioni sono escluse perche' con ``from __future__ import
    annotations`` non vengono valutate: un riferimento in avanti li' e' legittimo
    e segnalarlo sarebbe un falso allarme.
    """
    da_saltare: set[int] = set()
    for interno in ast.walk(nodo):
        if isinstance(interno, ast.AnnAssign) and interno.annotation is not None:
            da_saltare.add(id(interno.annotation))
        elif isinstance(interno, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if interno.returns is not None:
                da_saltare.add(id(interno.returns))
            for gruppo in (interno.args.posonlyargs, interno.args.args,
                           interno.args.kwonlyargs):
                for argomento in gruppo:
                    if argomento.annotation is not None:
                        da_saltare.add(id(argomento.annotation))

    saltati: set[int] = set()
    for interno in ast.walk(nodo):
        if id(interno) in da_saltare:
            saltati.update(id(x) for x in ast.walk(interno))

    return {
        interno.id
        for interno in ast.walk(nodo)
        if isinstance(interno, ast.Name)
        and isinstance(interno.ctx, ast.Load)
        and id(interno) not in saltati
    }


def _controlla(nodo: ast.AST, ambito: Ambito, problemi: list[tuple[int, str]]) -> None:
    """Percorre un ambito, verifica i nomi letti e ricorre in quelli annidati."""
    corpo = getattr(nodo, "body", [])
    if not isinstance(corpo, list):
        corpo = [corpo]

    interni: list[tuple[ast.AST, Ambito]] = []
    for istruzione in corpo:
        for interno in ast.walk(istruzione):
            if isinstance(interno, (ast.FunctionDef, ast.AsyncFunctionDef)):
                figlio = Ambito("funzione", ambito)
                _dichiara_argomenti(figlio, interno.args)
                _raccogli(interno.body, figlio)
                interni.append((interno, figlio))
            elif isinstance(interno, ast.ClassDef):
                figlio = Ambito("classe", ambito)
                _raccogli(interno.body, figlio)
                interni.append((interno, figlio))

    annidati = {id(x) for interno, _ in interni for x in ast.walk(interno)} - {
        id(interno) for interno, _ in interni
    }
    for istruzione in corpo:
        for nome in _letti(istruzione):
            pass
        for interno in ast.walk(istruzione):
            if id(interno) in annidati:
                continue
            if isinstance(interno, ast.Name) and isinstance(interno.ctx, ast.Load):
                if not ambito.risolve(interno.id) and interno.id not in _letti_annotazione(istruzione):
                    problemi.append((getattr(interno, "lineno", 0), interno.id))

    for interno, figlio in interni:
        _controlla(interno, figlio, problemi)


def _letti_annotazione(istruzione: ast.stmt) -> set[str]:
    """Nomi che compaiono solo dentro annotazioni, da non segnalare."""
    tutti = {
        n.id for n in ast.walk(istruzione)
        if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)
    }
    return tutti - _letti(istruzione)


def nomi_irrisolti(percorso: Path) -> list[tuple[int, str]]:
    """Nomi letti e non risolvibili in un modulo, con la riga in cui compaiono."""
    albero = ast.parse(percorso.read_text(encoding="utf-8"), filename=str(percorso))
    modulo = Ambito("modulo")
    _raccogli(albero.body, modulo)
    problemi: list[tuple[int, str]] = []
    _controlla(albero, modulo, problemi)
    # Un nome puo' comparire piu' volte: si riporta la prima occorrenza di ognuno.
    visti: set[str] = set()
    unici = []
    for riga, nome in sorted(problemi):
        if nome not in visti:
            visti.add(nome)
            unici.append((riga, nome))
    return unici


@pytest.mark.parametrize("percorso", SCRIPT, ids=lambda p: p.name)
def test_ogni_nome_usato_esiste(percorso: Path) -> None:
    """Nessun nome letto deve restare senza definizione.

    E' il controllo che i dati locali non possono fare: vale su tutti i rami,
    compresi quelli che si aprono solo in presenza di anomalie.
    """
    irrisolti = nomi_irrisolti(percorso)
    assert not irrisolti, (
        f"{percorso.name}: nomi usati e mai definiti -> "
        + ", ".join(f"{nome} (riga {riga})" for riga, nome in irrisolti)
    )


@pytest.mark.parametrize("percorso", SCRIPT, ids=lambda p: p.name)
def test_ogni_script_si_importa(percorso: Path) -> None:
    """L'importazione coglie cio' che l'analisi statica non vede.

    Un import rotto, una costante calcolata all'importazione che solleva, un
    modulo assente: sono errori che si manifestano prima ancora che lo script
    faccia qualcosa, e che pure sono arrivati fino alla macchina di raccolta.
    """
    if str(RADICE) not in sys.path:
        sys.path.insert(0, str(RADICE))
    importlib.import_module(f"scripts.{percorso.stem}")


def test_il_controllo_riconosce_un_nome_mancante(tmp_path: Path) -> None:
    """Il controllo deve fallire dove deve, altrimenti non protegge da nulla.

    Riproduce il difetto vero: una funzione chiamata dentro un ramo che i dati di
    sviluppo non attraversano, e la cui definizione e' stata cancellata.
    """
    finto = tmp_path / "finto.py"
    finto.write_text(
        "def principale(dati):\n"
        "    if dati:\n"
        "        return funzione_cancellata(dati)\n"
        "    return None\n",
        encoding="utf-8",
    )
    assert [nome for _, nome in nomi_irrisolti(finto)] == ["funzione_cancellata"]


def test_il_controllo_non_segnala_cio_che_e_definito(tmp_path: Path) -> None:
    """Controllo speculare: senza questo, un controllo che segnala tutto passerebbe."""
    finto = tmp_path / "sano.py"
    finto.write_text(
        "import math\n"
        "COSTANTE = 3\n"
        "def aiuto(x):\n"
        "    return math.sqrt(x) + COSTANTE\n"
        "def principale(dati):\n"
        "    quadrati = [aiuto(v) for v in dati]\n"
        "    with open('f') as f:\n"
        "        pass\n"
        "    try:\n"
        "        pass\n"
        "    except ValueError as errore:\n"
        "        print(errore)\n"
        "    return quadrati\n",
        encoding="utf-8",
    )
    assert nomi_irrisolti(finto) == []
