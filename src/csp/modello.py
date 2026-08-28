"""Il viaggio con piu' tappe obbligate, come problema di soddisfacimento di vincoli.

**Che cosa si sta modellando.** Un viaggiatore deve toccare piu' luoghi nella
stessa giornata: essere in stazione fra le 9:00 e le 9:15, poi in ufficio entro le
10:00. Per ogni tratta il pianificatore della Fase 2 sa gia' produrre gli
itinerari non dominati; qui si sceglie **quale** itinerario usare su ciascuna
tratta, in modo che le scelte siano fra loro compatibili.

**Perche' non e' una ricerca sequenziale.** Con i soli vincoli di precedenza - la
tappa successiva non puo' partire prima che io sia arrivato - il problema si
risolverebbe da sinistra a destra scegliendo ogni volta l'arrivo piu' precoce, e
chiamarlo soddisfacimento di vincoli sarebbe una millanteria. Cio' che rompe
quella struttura sono i **budget globali**: un tetto sul numero totale di cambi
dell'intera giornata e uno sui minuti totali a piedi. Non sono vincoli inventati
per creare l'accoppiamento: sono i vincoli che un viaggiatore reale ha. Nessuno
accetta dodici cambi in una mattina, e le aziende stesse pubblicano tempi minimi
di trasbordo proprio perche' il cambio ha un costo; il tetto sul cammino e' ancora
piu' concreto, ed e' stringente per chi ha ridotta mobilita' - la stessa persona
per cui esiste la regola ``accessibile/2`` della base di conoscenza.
L'accoppiamento fra le variabili e' una **conseguenza** di quei vincoli, non la
loro ragione.

Sotto un budget globale l'arrivo piu' precoce non e' piu' sempre la scelta
migliore, perche' un itinerario che arriva prima puo' consumare cambi che
serviranno dopo. Il modulo :mod:`src.csp.risolutori` contiene il controesempio
costruito che lo dimostra, e l'esperimento che misura quanto spesso accada.

**Una scelta di modellazione da dichiarare.** Il dominio di una tappa e' costruito
interrogando il pianificatore da una griglia di istanti di disponibilita', e ogni
candidato porta con se' l'istante da cui e' stato calcolato (``pronto_da``). Un
itinerario calcolato per chi e' pronto alle 9:20 e' eseguibile da chiunque sia
pronto **entro** le 9:20, quindi il vincolo di precedenza si scrive sul solo
``pronto_da`` e i domini restano statici. E' leggermente conservativo, perche' un
viaggiatore pronto alle 9:12 potrebbe prendere qualcosa che la griglia non offre;
ma vale per tutti i metodi confrontati, quindi non falsa il confronto.
"""

from __future__ import annotations

from dataclasses import dataclass

INFINITO = 1 << 62


class ErroreCSP(Exception):
    """L'istanza non e' formulata in modo valutabile."""


@dataclass(frozen=True)
class Candidato:
    """Un itinerario possibile per una tappa, con cio' che i vincoli guardano.

    Non porta il cammino effettivo: al soddisfacimento dei vincoli servono solo
    l'istante da cui e' eseguibile, quando fa arrivare, e quanto consuma dei due
    budget globali. Tenere fuori il resto e' cio' che rende i vincoli collaudabili
    senza costruire un grafo.
    """

    pronto_da: int
    """Istante POSIX da cui l'itinerario e' eseguibile: chi e' pronto prima aspetta."""
    orario_arrivo: int
    cambi: int
    secondi_a_piedi: int


@dataclass(frozen=True)
class Tappa:
    """Una tratta obbligata del viaggio, con il suo dominio e la sua finestra."""

    origine: str
    destinazione: str
    sosta_minima: int
    """Secondi da trascorrere alla partenza di questa tappa prima di poter ripartire.

    Rappresenta cio' per cui la tappa esiste: scendere, fare quello che si e'
    venuti a fare, tornare alla fermata. Per la prima tappa e' zero.
    """
    dominio: tuple[Candidato, ...]
    finestra: tuple[int, int] | None = None
    """Estremi entro cui l'arrivo deve cadere, quando la tappa ne ha una.

    E' a **due** estremi, e l'estremo inferiore non e' decorativo: se devo essere
    in stazione fra le 9:00 e le 9:15, arrivare alle 8:40 e' una violazione e non
    un vantaggio.
    """

    def __post_init__(self) -> None:
        if not self.dominio:
            raise ErroreCSP(f"tappa {self.origine}->{self.destinazione} con dominio vuoto")
        if self.finestra is not None and self.finestra[0] > self.finestra[1]:
            raise ErroreCSP(f"finestra rovesciata su {self.origine}->{self.destinazione}")


@dataclass(frozen=True)
class Istanza:
    """Un viaggio multi-tappa completo, con i due budget che accoppiano le tappe."""

    citta: str
    identificativo: str
    tappe: tuple[Tappa, ...]
    cambi_max: int
    piedi_max: int
    scadenza: int
    """Istante POSIX entro cui l'ultima tappa deve essere arrivata."""

    def __post_init__(self) -> None:
        if len(self.tappe) < 2:
            raise ErroreCSP("un viaggio multi-tappa ha almeno due tappe")


# Un'assegnazione e' una scelta per ogni tappa, nell'ordine delle tappe.
Assegnazione = tuple[Candidato, ...]


def violazioni(istanza: Istanza, assegnazione: Assegnazione) -> tuple[str, ...]:
    """Elenco dei vincoli violati, vuoto se l'assegnazione e' ammissibile.

    Restituisce i nomi invece di un booleano perche' e' cio' che rende i test
    capaci di distinguere *quale* vincolo abbia respinto un'assegnazione: un test
    che verifica solo il rifiuto passerebbe anche se a rifiutare fosse il vincolo
    sbagliato.
    """
    if len(assegnazione) != len(istanza.tappe):
        raise ErroreCSP("assegnazione di lunghezza diversa dal numero di tappe")

    rotti: list[str] = []

    for indice, (tappa, scelto) in enumerate(zip(istanza.tappe, assegnazione)):
        if scelto not in tappa.dominio:
            rotti.append(f"dominio[{indice}]")
        if tappa.finestra is not None:
            inizio, fine = tappa.finestra
            if scelto.orario_arrivo < inizio:
                rotti.append(f"finestra_anticipo[{indice}]")
            elif scelto.orario_arrivo > fine:
                rotti.append(f"finestra_ritardo[{indice}]")

    for indice in range(1, len(assegnazione)):
        precedente = assegnazione[indice - 1]
        corrente = assegnazione[indice]
        if corrente.pronto_da < precedente.orario_arrivo + istanza.tappe[indice].sosta_minima:
            rotti.append(f"precedenza[{indice}]")

    if sum(c.cambi for c in assegnazione) > istanza.cambi_max:
        rotti.append("cambi_max")
    if sum(c.secondi_a_piedi for c in assegnazione) > istanza.piedi_max:
        rotti.append("piedi_max")
    if assegnazione[-1].orario_arrivo > istanza.scadenza:
        rotti.append("scadenza")

    return tuple(rotti)


def ammissibile(istanza: Istanza, assegnazione: Assegnazione) -> bool:
    """Vero se l'assegnazione soddisfa tutti i vincoli."""
    return not violazioni(istanza, assegnazione)


def limiti_inferiori(istanza: Istanza) -> tuple[int, int]:
    """Cambi e secondi a piedi minimi ottenibili guardando ogni tappa da sola.

    Serve a tarare i budget sui dati invece che a occhio: un tetto sotto questo
    limite rende l'istanza infattibile per aritmetica e non per interazione fra le
    tappe, e misurare su istanze cosi' direbbe soltanto che abbiamo scelto male le
    soglie. I budget dell'esperimento sono percio' espressi come questo limite
    piu' un margine.

    Va notato che il limite **non e' raggiungibile in generale**: minimizza ogni
    tappa separatamente ignorando precedenza e finestre, quindi e' un limite
    inferiore vero e proprio e non una soluzione.
    """
    cambi = sum(min(c.cambi for c in tappa.dominio) for tappa in istanza.tappe)
    piedi = sum(min(c.secondi_a_piedi for c in tappa.dominio) for tappa in istanza.tappe)
    return cambi, piedi
