"""Ogni nome usato deve esistere, anche nei rami mai eseguiti sui dati di sviluppo.

**Perche' questo test esiste.** Gli script hanno rami che i dati di sviluppo non
attraversano: un ramo che si apre solo in presenza di righe anomale, o solo su una
citta', o solo attorno alla mezzanotte. Un nome cancellato per sbaglio dentro uno
di quei rami non fa fallire nulla in locale - il ramo non entra mai in funzione -
e si manifesta soltanto sulla macchina di raccolta, dopo un trasferimento e
un'esecuzione. E' gia' successo due volte con la stessa funzione, e il collaudo
sui dati locali per costruzione non puo' vederlo.

Il controllo e' statico e non esegue nulla: costruisce l'albero degli **ambiti**
di ciascun modulo e verifica che ogni nome letto sia risolvibile fra le variabili
locali, quelle delle funzioni che lo racchiudono, quelle del modulo e le
incorporate. E' una versione ridotta di cio' che farebbe pyflakes, scritta a mano
perche' lo stack del progetto e' chiuso e non vale una dipendenza in piu' per un
solo controllo.

**Gli ambiti vanno costruiti con precisione, e la prima versione non lo faceva.**
Raccogliendo le funzioni annidate con una visita indiscriminata dell'albero, una
funzione definita dentro un'altra veniva agganciata **anche** all'ambito del
modulo, perdendo per strada le variabili della funzione che la racchiude: ogni
chiusura produceva un falso allarme. Un verificatore che segnala cio' che e'
corretto viene disattivato dopo il terzo falso allarme, e a quel punto non
protegge piu' da nulla. Si scende percio' un ambito alla volta, senza entrare in
quelli annidati, e si trattano come ambiti propri anche le espressioni lambda e le
comprensioni, che in Python lo sono.

**Cosa non copre**, dichiarato per non dargli piu' credito di quanto ne meriti: le
annotazioni di tipo, che con ``from __future__ import annotations`` non vengono
valutate e possono contenere riferimenti in avanti legittimi; gli attributi, di
cui si verifica solo la radice; i nomi introdotti da ``import *``, che il progetto
non usa; e i costrutti ``match``, che il progetto non usa.
"""

from __future__ import annotations

import ast
import builtins
import importlib
import sys
from pathlib import Path

import pytest

RADICE = Path(__file__).resolve().parents[1]
INCORPORATI = set(dir(builtins)) | {
    "__file__", "__name__", "__doc__", "__spec__", "__package__", "__builtins__",
}

SCRIPT = sorted(p for p in (RADICE / "scripts").glob("*.py") if not p.name.startswith("_"))
SORGENTI = sorted(p for p in (RADICE / "src").rglob("*.py") if not p.name.startswith("_"))
MODULI = SCRIPT + SORGENTI

SCOPE = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)
COMPRENSIONI = (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)


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
            # consulta solo quando e' l'ambito in cui il nome viene letto.
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


def _percorri(nodi: list[ast.AST]) -> tuple[list[ast.AST], list[ast.AST]]:
    """Separa cio' che appartiene a questo ambito da cio' che ne apre uno nuovo.

    E' il cuore della correzione: non si scende dentro funzioni, classi, lambda e
    comprensioni, perche' il loro interno e' un ambito diverso e agganciarlo a
    quello corrente produce falsi allarmi sulle chiusure.
    """
    propri: list[ast.AST] = []
    figli: list[ast.AST] = []

    def visita(nodo: ast.AST) -> None:
        for figlio in ast.iter_child_nodes(nodo):
            if isinstance(figlio, SCOPE + COMPRENSIONI):
                figli.append(figlio)
            else:
                propri.append(figlio)
                visita(figlio)

    for nodo in nodi:
        if isinstance(nodo, SCOPE + COMPRENSIONI):
            figli.append(nodo)
        else:
            propri.append(nodo)
            visita(nodo)
    return propri, figli


def _dichiara_argomenti(ambito: Ambito, argomenti: ast.arguments) -> None:
    for gruppo in (argomenti.posonlyargs, argomenti.args, argomenti.kwonlyargs):
        for argomento in gruppo:
            ambito.dichiara(argomento.arg)
    for opzionale in (argomenti.vararg, argomenti.kwarg):
        if opzionale is not None:
            ambito.dichiara(opzionale.arg)


def _lega(propri: list[ast.AST], ambito: Ambito) -> None:
    """Registra nell'ambito i nomi legati dai nodi che gli appartengono."""
    for nodo in propri:
        if isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            ambito.dichiara(nodo.name)
        elif isinstance(nodo, (ast.Import, ast.ImportFrom)):
            for alias in nodo.names:
                ambito.dichiara(alias.asname or alias.name.split(".")[0])
        elif isinstance(nodo, ast.Assign):
            for bersaglio in nodo.targets:
                for nome in _bersagli(bersaglio):
                    ambito.dichiara(nome)
        elif isinstance(nodo, (ast.AnnAssign, ast.AugAssign, ast.NamedExpr)):
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


def _da_saltare(propri: list[ast.AST]) -> set[int]:
    """Sottoalberi delle annotazioni, che non vengono valutate."""
    radici: list[ast.AST] = []
    for nodo in propri:
        if isinstance(nodo, ast.AnnAssign) and nodo.annotation is not None:
            radici.append(nodo.annotation)
    saltati: set[int] = set()
    for radice in radici:
        saltati.update(id(x) for x in ast.walk(radice))
    return saltati


def _corpo_di(nodo: ast.AST) -> list[ast.AST]:
    """I nodi che formano il corpo di un ambito, qualunque sia il suo tipo."""
    if isinstance(nodo, ast.Lambda):
        return [nodo.body]
    if isinstance(nodo, COMPRENSIONI):
        parti: list[ast.AST] = []
        if isinstance(nodo, ast.DictComp):
            parti += [nodo.key, nodo.value]
        else:
            parti.append(nodo.elt)
        for generatore in nodo.generators:
            parti.append(generatore.iter)
            parti.extend(generatore.ifs)
        return parti
    corpo = getattr(nodo, "body", [])
    return corpo if isinstance(corpo, list) else [corpo]


def _controlla(nodo: ast.AST, ambito: Ambito, problemi: list[tuple[int, str]]) -> None:
    """Verifica i nomi letti in un ambito e ricorre in quelli che vi si aprono."""
    propri, figli = _percorri(_corpo_di(nodo))
    _lega(propri, ambito)
    # Una funzione o una classe apre un ambito nuovo, ma il suo NOME appartiene a
    # quello che la contiene: senza questa riga ogni definizione risulterebbe
    # sconosciuta al modulo che la ospita.
    for figlio in figli:
        if isinstance(figlio, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            ambito.dichiara(figlio.name)
    saltati = _da_saltare(propri)

    for interno in propri:
        if (isinstance(interno, ast.Name) and isinstance(interno.ctx, ast.Load)
                and id(interno) not in saltati and not ambito.risolve(interno.id)):
            problemi.append((getattr(interno, "lineno", 0), interno.id))

    for figlio in figli:
        if isinstance(figlio, (ast.FunctionDef, ast.AsyncFunctionDef)):
            interno_ambito = Ambito("funzione", ambito)
            _dichiara_argomenti(interno_ambito, figlio.args)
        elif isinstance(figlio, ast.Lambda):
            interno_ambito = Ambito("funzione", ambito)
            _dichiara_argomenti(interno_ambito, figlio.args)
        elif isinstance(figlio, ast.ClassDef):
            interno_ambito = Ambito("classe", ambito)
        else:
            interno_ambito = Ambito("comprensione", ambito)
            for generatore in figlio.generators:  # type: ignore[attr-defined]
                for nome in _bersagli(generatore.target):
                    interno_ambito.dichiara(nome)
        _controlla(figlio, interno_ambito, problemi)


def nomi_irrisolti(percorso: Path) -> list[tuple[int, str]]:
    """Nomi letti e non risolvibili in un modulo, con la riga in cui compaiono."""
    albero = ast.parse(percorso.read_text(encoding="utf-8"), filename=str(percorso))
    modulo = Ambito("modulo")
    problemi: list[tuple[int, str]] = []
    _controlla(albero, modulo, problemi)
    visti: set[str] = set()
    unici = []
    for riga, nome in sorted(problemi):
        if nome not in visti:
            visti.add(nome)
            unici.append((riga, nome))
    return unici


@pytest.mark.parametrize("percorso", MODULI, ids=lambda p: f"{p.parent.name}/{p.name}")
def test_ogni_nome_usato_esiste(percorso: Path) -> None:
    """Nessun nome letto deve restare senza definizione.

    Vale su `scripts/` e su `src/`, e su tutti i rami, compresi quelli che si
    aprono solo in presenza di anomalie che i dati di sviluppo non contengono.
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
    modulo assente: errori che si manifestano prima ancora che lo script faccia
    qualcosa, e che pure sono arrivati fino alla macchina di raccolta.
    """
    if str(RADICE) not in sys.path:
        sys.path.insert(0, str(RADICE))
    importlib.import_module(f"scripts.{percorso.stem}")


def test_il_controllo_riconosce_un_nome_mancante(tmp_path: Path) -> None:
    """Riproduce il difetto vero: funzione chiamata in un ramo, e mai definita."""
    finto = tmp_path / "finto.py"
    finto.write_text(
        "def principale(dati):\n"
        "    if dati:\n"
        "        return funzione_cancellata(dati)\n"
        "    return None\n",
        encoding="utf-8",
    )
    assert [nome for _, nome in nomi_irrisolti(finto)] == ["funzione_cancellata"]


def test_il_controllo_non_segnala_le_chiusure(tmp_path: Path) -> None:
    """La regressione che ha reso necessario riscrivere il verificatore.

    Una funzione annidata che legge una variabile della funzione che la racchiude
    e' corretta, e la prima versione la segnalava perche' agganciava gli ambiti
    annidati anche al modulo. Su `src/` produceva quattro falsi allarmi.
    """
    finto = tmp_path / "chiusure.py"
    finto.write_text(
        "def esterna(istanza):\n"
        "    totale = 0\n"
        "    def interna(indice):\n"
        "        nonlocal totale\n"
        "        totale += istanza.valori[indice]\n"
        "        def piu_interna():\n"
        "            return istanza, totale, indice\n"
        "        return piu_interna\n"
        "    return interna\n",
        encoding="utf-8",
    )
    assert nomi_irrisolti(finto) == []


def test_il_controllo_non_segnala_lambda_e_comprensioni(tmp_path: Path) -> None:
    """Anche lambda e comprensioni aprono un ambito proprio, e vanno trattate come tale."""
    finto = tmp_path / "ambiti.py"
    finto.write_text(
        "def principale(elementi):\n"
        "    scelto = min(elementi, key=lambda e: (e.a, e.b))\n"
        "    quadrati = [v * v for v in elementi if v]\n"
        "    mappa = {k: [w for w in elementi if w != k] for k in elementi}\n"
        "    return scelto, quadrati, mappa\n",
        encoding="utf-8",
    )
    assert nomi_irrisolti(finto) == []


def test_il_controllo_non_segnala_cio_che_e_definito(tmp_path: Path) -> None:
    """Controllo speculare: un verificatore che segnala tutto passerebbe gli altri."""
    finto = tmp_path / "sano.py"
    finto.write_text(
        "import math\n"
        "COSTANTE = 3\n"
        "def aiuto(x):\n"
        "    return math.sqrt(x) + COSTANTE\n"
        "def principale(dati):\n"
        "    with open('f') as f:\n"
        "        righe = f.read()\n"
        "    try:\n"
        "        pass\n"
        "    except ValueError as errore:\n"
        "        print(errore)\n"
        "    return [aiuto(v) for v in dati], righe\n",
        encoding="utf-8",
    )
    assert nomi_irrisolti(finto) == []
