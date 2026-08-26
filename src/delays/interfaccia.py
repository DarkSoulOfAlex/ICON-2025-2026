"""Interfaccia fra la ricerca di itinerari e il modello dei ritardi.

Questo modulo non contiene alcun modello appreso: definisce la **forma** che un
modello dei ritardi deve avere, piu' una implementazione sintetica che serve
soltanto a far girare e collaudare il resto del progetto finche' i dati veri non
sono disponibili.

Perche' l'interfaccia viene fissata adesso. La raccolta dei dati richiede due
settimane, e la Fase 4 dovra' comporre distribuzioni di ritardo lungo una catena
di coincidenze. Se aspettassimo i dati per decidere che forma abbia una
distribuzione, la Fase 2 e la Fase 4 andrebbero riscritte quando arrivano. Fissare
adesso il contratto - una tratta entra, una distribuzione esce - permette di
scrivere e collaudare tutto il resto subito, e alla Fase 3 di sostituire soltanto
l'implementazione.

**La Fase 2 non usa i ritardi.** La ricerca di itinerari lavora sull'orario
programmato: la robustezza probabilistica arriva in Fase 4. Questo modulo esiste
in Fase 2 perche' l'interfaccia va progettata prima di cio' che la consumera',
non perche' la ricerca ne dipenda.

Il presidio contro l'uso accidentale del modello sintetico e' descritto in
:func:`assicura_utilizzabile`, ed e' la parte del modulo che conta di piu': un
risultato sperimentale prodotto senza accorgersene su ritardi inventati sarebbe
peggio di nessun risultato.
"""

from __future__ import annotations

import hashlib
import math
import struct
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Sequence

import numpy as np


class ErroreModelloSintetico(RuntimeError):
    """Un modello sintetico stava per produrre un risultato sperimentale."""


# =============================================================================
# Che cosa si chiede a un modello, e che cosa restituisce
# =============================================================================


@dataclass(frozen=True)
class Tratta:
    """Il contesto minimo su cui un modello puo' fondare una previsione.

    Contiene solo cio' che e' noto **al momento della pianificazione**: linea,
    corsa, fermata, posizione lungo il percorso e orario programmato. Non contiene
    nulla che si sappia soltanto dopo, ed e' voluto: e' la barriera che in Fase 3
    impedira' a una feature di guardare nel futuro. Un modello che volesse usare
    il ritardo osservato alle fermate precedenti lo ricevera' esplicitamente in
    ``ritardo_a_monte``, che chi pianifica puo' davvero conoscere.
    """

    citta: str
    route_id: str
    trip_id: str
    stop_id: str
    stop_sequence: int
    orario_programmato: int
    """Istante POSIX dell'arrivo programmato."""
    ritardo_a_monte: int | None = None
    """Ritardo osservato all'ultima fermata gia' servita, se noto."""


class Distribuzione(ABC):
    """Una distribuzione di probabilita' del ritardo, in secondi.

    Le quattro operazioni non sono arbitrarie: sono esattamente quelle che le fasi
    successive richiedono. La Fase 4 calcola P(arrivo <= T) e quindi ha bisogno
    della funzione di ripartizione; il metodo Monte Carlo ha bisogno di campionare;
    la valutazione della Fase 3 usa i quantili per la pinball loss; la media serve
    ai confronti con le baseline deterministiche.
    """

    @abstractmethod
    def cdf(self, secondi: float) -> float:
        """P(ritardo <= secondi)."""

    @abstractmethod
    def quantile(self, probabilita: float) -> float:
        """Il ritardo non superato con la probabilita' data."""

    @abstractmethod
    def campiona(self, quanti: int, generatore: np.random.Generator) -> np.ndarray:
        """``quanti`` ritardi estratti dalla distribuzione.

        Il generatore e' un parametro e non uno stato globale: e' cio' che rende
        riproducibile un esperimento Monte Carlo.
        """

    @abstractmethod
    def media(self) -> float:
        """Valore atteso del ritardo."""

    def cdf_vettoriale(self, valori: np.ndarray) -> np.ndarray:
        """Funzione di ripartizione su un vettore di valori.

        Esiste perche' la convoluzione numerica della Fase 4 valuta la
        ripartizione su griglie di migliaia di punti, e farlo un valore alla
        volta costerebbe secondi per ogni itinerario. L'implementazione
        predefinita cicla; le sottoclassi che possono fare di meglio la
        sovrascrivono.
        """
        return np.array([self.cdf(float(v)) for v in np.asarray(valori)], dtype=float)


class ModelloRitardo(ABC):
    """Contratto di un modello dei ritardi."""

    #: Vero se il modello inventa i ritardi invece di averli appresi dai dati.
    sintetico: bool = True

    #: Nome che finisce nei CSV dei risultati, perche' sia sempre ricostruibile
    #: quale modello li abbia prodotti.
    nome: str = "astratto"

    @abstractmethod
    def distribuzione(self, tratta: Tratta) -> Distribuzione:
        """La distribuzione del ritardo previsto per una tratta."""


# =============================================================================
# Il presidio
# =============================================================================


def assicura_utilizzabile(modello: ModelloRitardo, sintetico_ammesso: bool = False) -> None:
    """Impedisce a un modello sintetico di produrre risultati sperimentali.

    Va chiamata da ogni script che scriva in ``results/``. La ragione e' che un
    modello sintetico e' indistinguibile da uno vero dal punto di vista
    dell'interfaccia: e' quello il suo scopo. Proprio per questo, senza un
    controllo esplicito, basterebbe una dimenticanza per pubblicare nel documento
    numeri calcolati su ritardi inventati, e nulla nell'output lo segnalerebbe.

    Il controllo non e' l'unica difesa: i CSV portano una colonna con il nome del
    modello, cosi' l'origine di un risultato resta leggibile anche a distanza di
    mesi.
    """
    if modello.sintetico and not sintetico_ammesso:
        raise ErroreModelloSintetico(
            f"Il modello '{modello.nome}' e' SINTETICO: i ritardi che produce sono inventati "
            "e non possono comparire in alcun risultato sperimentale.\n"
            "Se stai sviluppando e vuoi comunque procedere, passa --sintetico-ammesso: "
            "i file prodotti resteranno marcati come tali dalla colonna 'modello_ritardo'."
        )


# =============================================================================
# Implementazioni
# =============================================================================


class LogNormaleTraslata(Distribuzione):
    """Log-normale spostata, la forma tipica di un ritardo del trasporto pubblico.

    La scelta della famiglia non e' innocente e va motivata, anche se qui i
    parametri sono inventati. Un ritardo non e' simmetrico: c'e' un limite a
    quanto un mezzo possa arrivare in anticipo, perche' non parte prima
    dell'orario, mentre non c'e' limite superiore a quanto possa ritardare. La
    log-normale ha esattamente questa asimmetria, coda destra lunga e supporto
    inferiormente limitato. Lo spostamento ammette un anticipo moderato, che nei
    dati raccolti e' tutt'altro che raro: sul primo giorno consolidato la mediana
    del ritardo e' risultata negativa in entrambe le citta'.

    Resta un'ipotesi da verificare in Fase 3 sui dati veri, non una conclusione.
    """

    def __init__(self, mu: float, sigma: float, spostamento: float = 0.0) -> None:
        if sigma <= 0:
            raise ValueError("sigma deve essere positivo")
        self.mu = float(mu)
        self.sigma = float(sigma)
        self.spostamento = float(spostamento)

    def cdf(self, secondi: float) -> float:
        scarto = secondi - self.spostamento
        if scarto <= 0:
            return 0.0
        return 0.5 * (1.0 + math.erf((math.log(scarto) - self.mu) / (self.sigma * math.sqrt(2.0))))

    def quantile(self, probabilita: float) -> float:
        if not 0.0 < probabilita < 1.0:
            raise ValueError("la probabilita' deve stare in (0, 1)")
        # Inversa della normale standard tramite la funzione errore inversa.
        normale = math.sqrt(2.0) * _erfinv(2.0 * probabilita - 1.0)
        return self.spostamento + math.exp(self.mu + self.sigma * normale)

    def campiona(self, quanti: int, generatore: np.random.Generator) -> np.ndarray:
        return self.spostamento + generatore.lognormal(self.mu, self.sigma, size=quanti)

    def media(self) -> float:
        return self.spostamento + math.exp(self.mu + self.sigma**2 / 2.0)

    def cdf_vettoriale(self, valori: np.ndarray) -> np.ndarray:
        """Versione vettorializzata, con ripiego se scipy non e' disponibile.

        L'importazione e' locale e protetta perche' questo modulo deve restare
        importabile anche sulla VM di raccolta, dove scipy non e' installato:
        li' non serve la convoluzione, ma serve l'interfaccia.
        """
        scarti = np.asarray(valori, dtype=float) - self.spostamento
        risultato = np.zeros_like(scarti)
        positivi = scarti > 0
        if not positivi.any():
            return risultato
        z = (np.log(scarti[positivi]) - self.mu) / self.sigma
        try:
            from scipy.special import ndtr

            risultato[positivi] = ndtr(z)
        except ImportError:  # pragma: no cover - dipende dall'ambiente
            risultato[positivi] = [0.5 * (1.0 + math.erf(v / math.sqrt(2.0))) for v in z]
        return risultato


class Empirica(Distribuzione):
    """Distribuzione definita da un campione di ritardi osservati.

    E' la forma che assumeranno i modelli della Fase 3: una baseline empirica per
    (linea, fascia oraria) non e' altro che l'insieme dei ritardi gia' visti in
    quella combinazione. Esiste gia' adesso perche' il resto del progetto possa
    essere scritto contro di essa.
    """

    def __init__(self, campione: Sequence[float]) -> None:
        valori = np.asarray(sorted(float(v) for v in campione), dtype=float)
        if valori.size == 0:
            raise ValueError("un campione vuoto non definisce una distribuzione")
        self.valori = valori

    def cdf(self, secondi: float) -> float:
        return float(np.searchsorted(self.valori, secondi, side="right") / self.valori.size)

    def quantile(self, probabilita: float) -> float:
        return float(np.quantile(self.valori, probabilita))

    def campiona(self, quanti: int, generatore: np.random.Generator) -> np.ndarray:
        return generatore.choice(self.valori, size=quanti, replace=True)

    def media(self) -> float:
        return float(self.valori.mean())


class ModelloSintetico(ModelloRitardo):
    """Modello parametrico per lo sviluppo. NON produce risultati sperimentali.

    I ritardi dipendono in modo deterministico dalla linea e dalla fascia oraria,
    con le ore di punta piu' variabili di quelle di morbida, e crescono lungo il
    percorso perche' un ritardo accumulato non si riassorbe da solo. E' un
    comportamento plausibile, ma **inventato**: serve a verificare che il codice a
    valle funzioni, non a dire qualcosa sul trasporto pubblico di Roma o di
    Torino.

    La dipendenza dalla linea passa da un hash dell'identificativo, cosi' due
    esecuzioni diverse producono la stessa distribuzione per la stessa linea senza
    dover memorizzare nulla.
    """

    sintetico = True
    nome = "sintetico"

    def __init__(
        self,
        seme: int = 20260826,
        intensita: float = 1.0,
        correlazione: float = 0.7,
    ) -> None:
        """``correlazione`` governa quanto il ritardo a monte si trasmette a valle.

        E' un **parametro** e non una costante cablata, per due ragioni. La prima
        e' che in Fase 3 il modello appreso avra' la correlazione che i dati
        mostrano, che potrebbe essere molto diversa da quella che inventiamo
        adesso: cablarla qui significherebbe scrivere il resto del progetto
        attorno a un numero senza fondamento. La seconda e' che questa e' la leva
        con cui si controlla quanto due itinerari diversi si distinguano fra loro:
        a correlazione nulla i ritardi si azzerano a ogni fermata e ogni
        itinerario si somiglia, a correlazione unitaria un ritardo iniziale si
        trascina per l'intera corsa.

        ``intensita`` scala la dispersione: e' l'altra leva, quella che decide
        quanto conti la varianza rispetto alla media nella scelta dell'itinerario.
        """
        if not 0.0 <= correlazione <= 1.0:
            raise ValueError("la correlazione deve stare in [0, 1]")
        self.seme = int(seme)
        self.intensita = float(intensita)
        self.correlazione = float(correlazione)

    def _ora_locale(self, orario_programmato: int) -> int:
        # Ora del giorno in UTC: basta a distinguere punta e morbida, e non
        # introduce una dipendenza da zoneinfo in un modello inventato.
        return (orario_programmato // 3600) % 24

    def distribuzione(self, tratta: Tratta) -> LogNormaleTraslata:
        ora = self._ora_locale(tratta.orario_programmato)
        di_punta = ora in (7, 8, 9, 17, 18, 19)

        impronta = _impronta_stabile(self.seme, tratta.route_id)

        mu = math.log(60.0 + 120.0 * impronta) + (0.4 if di_punta else 0.0)
        sigma = (0.5 + 0.4 * impronta + (0.3 if di_punta else 0.0)) * self.intensita
        # Il ritardo si accumula lungo la corsa: piu' avanti si e', peggio va.
        mu += 0.02 * min(tratta.stop_sequence, 40)
        # L'anticipo possibile e' limitato: un mezzo non parte prima dell'orario.
        spostamento = -90.0

        # Correlazione lungo la corsa. Un mezzo gia' in ritardo a monte tende a
        # restarlo: la quota `correlazione` del ritardo osservato viene
        # trasferita nella posizione della distribuzione a valle, e la
        # dispersione residua si riduce di conseguenza, perche' sapere dove si
        # trova il mezzo riduce l'incertezza su dove sara'.
        if tratta.ritardo_a_monte is not None and self.correlazione > 0.0:
            trasferito = self.correlazione * float(tratta.ritardo_a_monte)
            spostamento += trasferito
            sigma *= max(1e-3, math.sqrt(1.0 - self.correlazione**2))

        return LogNormaleTraslata(mu=mu, sigma=sigma, spostamento=spostamento)


class ModelloNullo(ModelloRitardo):
    """Nessun ritardo: la distribuzione e' concentrata in zero.

    Serve alle baseline deterministiche della Fase 4 e ai test in cui il ritardo
    non deve influire. E' comunque marcato come sintetico, perche' "nessun
    ritardo" e' un'affermazione sul mondo altrettanto inventata delle altre.
    """

    sintetico = True
    nome = "nullo"

    def distribuzione(self, tratta: Tratta) -> Empirica:
        return Empirica([0.0])


# =============================================================================
# Utilita'
# =============================================================================


def _impronta_stabile(seme: int, chiave: str) -> float:
    """Un numero in [0, 1) derivato da una stringa, stabile fra esecuzioni.

    NON si usa la ``hash`` incorporata: Python randomizza l'hash delle stringhe a
    ogni processo, quindi lo stesso identificativo di linea produrrebbe parametri
    diversi a ogni esecuzione. Il modello sintetico si dichiara deterministico dato
    un seme, e con la hash incorporata non lo sarebbe: gli esperimenti non
    sarebbero riproducibili, e il difetto si manifesterebbe solo come risultati
    che cambiano senza motivo apparente fra un'esecuzione e l'altra.
    """
    digesto = hashlib.blake2b(
        f"{seme}:{chiave}".encode("utf-8"), digest_size=4
    ).digest()
    return struct.unpack("<I", digesto)[0] / 0x1_0000_0000


def _erfinv(x: float) -> float:
    """Inversa della funzione errore, con il metodo di Newton su math.erf.

    Si evita di dipendere da scipy per una sola funzione: il modulo deve poter
    essere importato anche dove scipy non e' installato, per esempio sulla VM di
    raccolta.
    """
    if not -1.0 < x < 1.0:
        raise ValueError("erfinv e' definita in (-1, 1)")
    # Approssimazione iniziale di Winitzki, poi due passi di Newton.
    a = 0.147
    ln = math.log(1.0 - x * x)
    primo = 2.0 / (math.pi * a) + ln / 2.0
    stima = math.copysign(math.sqrt(math.sqrt(primo * primo - ln / a) - primo), x)
    for _ in range(2):
        errore = math.erf(stima) - x
        derivata = 2.0 / math.sqrt(math.pi) * math.exp(-stima * stima)
        stima -= errore / derivata
    return stima
