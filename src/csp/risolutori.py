"""Due modi di assegnare un itinerario a ogni tappa, e il controesempio che li separa.

:func:`risolvi_greedy` decide da sinistra a destra e non torna mai indietro: e' la
strategia che risolverebbe il problema se i vincoli fossero soltanto di
precedenza. :func:`risolvi_completo` esplora con ritorno all'indietro ed e'
completo: trova una soluzione ogni volta che esiste.

**La differenza fra i due e' la misura che giustifica l'intero argomento.** Se il
greedy trovasse una soluzione ogni volta che ne esiste una, il viaggio
multi-tappa non sarebbe un problema di soddisfacimento di vincoli ma una
successione di decisioni indipendenti, e andrebbe trattato come tale. La funzione
:func:`controesempio_budget` costruisce un'istanza a tre tappe, verificabile a
mano, su cui il greedy fallisce mentre una soluzione esiste: dimostra che il caso
e' possibile. Quanto sia frequente su istanze reali e' oggetto
dell'esperimento in ``scripts/csp_greedy.py``.

Il greedy implementato qui e' la versione **piu' forte** che non torni indietro:
scarta i candidati che sforerebbero i budget gia' durante il cammino, invece di
accorgersene alla fine. Indebolirlo renderebbe il confronto un fantoccio.
"""

from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter

from src.csp.modello import Assegnazione, Candidato, Istanza, Tappa, ammissibile

MINUTO = 60


@dataclass(frozen=True)
class EsitoRisoluzione:
    """Cosa ha trovato un risolutore, e quanto gli e' costato."""

    assegnazione: Assegnazione | None
    nodi: int
    """Assegnazioni parziali esaminate: il lavoro svolto, non il tempo di orologio."""
    secondi: float

    @property
    def risolta(self) -> bool:
        return self.assegnazione is not None


def _compatibile(
    tappa: Tappa,
    candidato: Candidato,
    arrivo_precedente: int | None,
    cambi_spesi: int,
    piedi_spesi: int,
    istanza: Istanza,
    ultima: bool,
) -> bool:
    """Vincoli verificabili guardando solo il passato dell'assegnazione parziale.

    Sono quelli che entrambi i risolutori possono controllare mentre procedono. Il
    greedy si ferma qui; il risolutore completo aggiunge un limite inferiore sul
    futuro.
    """
    if arrivo_precedente is not None:
        if candidato.pronto_da < arrivo_precedente + tappa.sosta_minima:
            return False
    if tappa.finestra is not None:
        inizio, fine = tappa.finestra
        if not (inizio <= candidato.orario_arrivo <= fine):
            return False
    if cambi_spesi + candidato.cambi > istanza.cambi_max:
        return False
    if piedi_spesi + candidato.secondi_a_piedi > istanza.piedi_max:
        return False
    if ultima and candidato.orario_arrivo > istanza.scadenza:
        return False
    return True


def risolvi_greedy(istanza: Istanza) -> EsitoRisoluzione:
    """Sceglie tappa per tappa l'arrivo piu' precoce fra i candidati compatibili.

    Non torna mai indietro. E' la strategia corretta quando i vincoli sono solo di
    precedenza, perche' allora arrivare prima non puo' mai nuocere: ogni
    prosecuzione disponibile a chi arriva tardi lo e' anche a chi arriva presto.
    Sotto un budget globale quella proprieta' cade, perche' un itinerario che
    arriva prima puo' consumare cambi che serviranno piu' avanti, e il greedy puo'
    dichiarare infattibile un'istanza risolubile.
    """
    avvio = perf_counter()
    scelte: list[Candidato] = []
    arrivo_precedente: int | None = None
    cambi_spesi = 0
    piedi_spesi = 0
    nodi = 0

    for indice, tappa in enumerate(istanza.tappe):
        ultima = indice == len(istanza.tappe) - 1
        ammessi = []
        for candidato in tappa.dominio:
            nodi += 1
            if _compatibile(
                tappa, candidato, arrivo_precedente, cambi_spesi, piedi_spesi, istanza, ultima
            ):
                ammessi.append(candidato)
        if not ammessi:
            return EsitoRisoluzione(None, nodi, perf_counter() - avvio)

        # Arrivo piu' precoce; a parita', meno cambi e poi meno cammino. E' la
        # regola che rende il greedy ottimo in assenza di budget globali.
        scelto = min(ammessi, key=lambda c: (c.orario_arrivo, c.cambi, c.secondi_a_piedi))
        scelte.append(scelto)
        arrivo_precedente = scelto.orario_arrivo
        cambi_spesi += scelto.cambi
        piedi_spesi += scelto.secondi_a_piedi

    return EsitoRisoluzione(tuple(scelte), nodi, perf_counter() - avvio)


def risolvi_completo(istanza: Istanza) -> EsitoRisoluzione:
    """Esplorazione con ritorno all'indietro: trova una soluzione se esiste.

    La potatura usa un limite inferiore sul consumo residuo: se i cambi gia' spesi
    piu' il minimo che le tappe rimanenti richiederanno superano il tetto, il ramo
    e' morto e nessuna scelta futura puo' salvarlo. E' un limite valido perche'
    minimizza ogni tappa rimanente separatamente, quindi non puo' sovrastimare il
    consumo reale e non taglia mai una soluzione.

    Fra le soluzioni ammissibili restituisce quella con l'arrivo finale piu'
    precoce, che e' la lettura naturale di "il viaggio migliore" una volta che i
    vincoli sono soddisfatti.
    """
    avvio = perf_counter()
    n = len(istanza.tappe)

    # Consumo minimo residuo, per la potatura. La coda vale zero: dopo l'ultima
    # tappa non resta nulla da spendere.
    minimo_cambi = [0] * (n + 1)
    minimo_piedi = [0] * (n + 1)
    for indice in range(n - 1, -1, -1):
        dominio = istanza.tappe[indice].dominio
        minimo_cambi[indice] = minimo_cambi[indice + 1] + min(c.cambi for c in dominio)
        minimo_piedi[indice] = minimo_piedi[indice + 1] + min(c.secondi_a_piedi for c in dominio)

    migliore: Assegnazione | None = None
    nodi = 0

    def esplora(
        indice: int,
        parziale: list[Candidato],
        arrivo_precedente: int | None,
        cambi_spesi: int,
        piedi_spesi: int,
    ) -> None:
        nonlocal migliore, nodi
        if indice == n:
            candidata = tuple(parziale)
            if migliore is None or candidata[-1].orario_arrivo < migliore[-1].orario_arrivo:
                migliore = candidata
            return

        tappa = istanza.tappe[indice]
        ultima = indice == n - 1
        for candidato in tappa.dominio:
            nodi += 1
            if not _compatibile(
                tappa, candidato, arrivo_precedente, cambi_spesi, piedi_spesi, istanza, ultima
            ):
                continue
            cambi = cambi_spesi + candidato.cambi
            piedi = piedi_spesi + candidato.secondi_a_piedi
            if cambi + minimo_cambi[indice + 1] > istanza.cambi_max:
                continue
            if piedi + minimo_piedi[indice + 1] > istanza.piedi_max:
                continue
            parziale.append(candidato)
            esplora(indice + 1, parziale, candidato.orario_arrivo, cambi, piedi)
            parziale.pop()

    esplora(0, [], None, 0, 0)
    return EsitoRisoluzione(migliore, nodi, perf_counter() - avvio)


def controesempio_budget(base: int = 1_800_000_000) -> Istanza:
    """L'istanza a tre tappe su cui il greedy fallisce e una soluzione esiste.

    E' costruita a mano perche' sia verificabile a mano, e i suoi numeri sono
    quelli riportati nel documento. ``base`` rappresenta le 09:00; il viaggio
    parte un'ora prima e il tetto globale e' di **quattro cambi**.

    Prima tappa, finestra 09:00-09:15: ``X1`` arriva alle 09:05 con tre cambi,
    ``X2`` alle 09:12 con un cambio. Seconda tappa: ``Y1`` esige di essere pronti
    alle 09:10 e costa un cambio, ``Y2`` alle 09:20 e ne costa due. Terza tappa:
    un solo itinerario, che esige di essere pronti alle 09:55 e costa un cambio.
    La sosta minima e' di cinque minuti.

    Il greedy sceglie ``X1`` perche' arriva prima, poi ``Y1``: ha speso quattro
    cambi e alla terza tappa ne servirebbe un quinto, quindi dichiara l'istanza
    infattibile. Scegliendo ``X2``, che arriva **sette minuti piu' tardi**, la
    sosta impone ``Y2``, e il totale e' 1 + 2 + 1 = quattro cambi esatti: la
    soluzione esiste. Arrivare prima sulla prima tappa e' la mossa che perde.
    """
    ore = 3600
    x1 = Candidato(pronto_da=base - ore, orario_arrivo=base + 5 * MINUTO, cambi=3, secondi_a_piedi=0)
    x2 = Candidato(pronto_da=base - ore, orario_arrivo=base + 12 * MINUTO, cambi=1, secondi_a_piedi=0)
    y1 = Candidato(
        pronto_da=base + 10 * MINUTO, orario_arrivo=base + 40 * MINUTO, cambi=1, secondi_a_piedi=0
    )
    y2 = Candidato(
        pronto_da=base + 20 * MINUTO, orario_arrivo=base + 50 * MINUTO, cambi=2, secondi_a_piedi=0
    )
    z = Candidato(
        pronto_da=base + 55 * MINUTO, orario_arrivo=base + 80 * MINUTO, cambi=1, secondi_a_piedi=0
    )

    return Istanza(
        citta="costruita",
        identificativo="controesempio_budget",
        tappe=(
            Tappa("A", "B", sosta_minima=0, dominio=(x1, x2),
                  finestra=(base, base + 15 * MINUTO)),
            Tappa("B", "C", sosta_minima=5 * MINUTO, dominio=(y1, y2)),
            Tappa("C", "D", sosta_minima=5 * MINUTO, dominio=(z,)),
        ),
        cambi_max=4,
        piedi_max=3600,
        scadenza=base + 90 * MINUTO,
    )


def concordano(istanza: Istanza) -> bool:
    """Vero se greedy e risolutore completo danno lo stesso verdetto di fattibilita'.

    E' la grandezza misurata dall'esperimento: la sua frequenza di falsita' dice
    se il problema sia davvero un CSP o una ricerca sequenziale travestita.
    """
    greedy = risolvi_greedy(istanza)
    completo = risolvi_completo(istanza)
    if greedy.risolta:
        # Un greedy che risolve deve produrre un'assegnazione valida: se non lo
        # facesse, il difetto sarebbe nel filtro e non nella strategia.
        assert ammissibile(istanza, greedy.assegnazione)
    return greedy.risolta == completo.risolta
