"""Raccoglitore dei feed GTFS Real-Time.

Perche' questo modulo viene prima di tutto il resto del progetto: un feed GTFS
Real-Time e' una fotografia dell'istante presente, non un archivio. Nessuna
agenzia pubblica lo storico dei ritardi, quindi il dataset su cui si reggono la
Fase 3 (modello probabilistico) e la Fase 5 (backtesting) non esiste finche' non
lo costruiamo noi. Ogni giorno in cui questo processo non gira e' un giorno di
dati perso e non recuperabile.

Da questo vincolo discendono le scelte progettuali del modulo:

* il processo non deve mai morire per un errore transitorio (rete, DNS, 503
  dell'agenzia): qualunque eccezione viene catturata, registrata e il ciclo
  prosegue al tick successivo;
* non tiene stato in memoria che sarebbe doloroso perdere: tutto e' scritto in
  append su disco, quindi un riavvio dopo un'interruzione riprende senza danni;
* registra anche i fallimenti, non solo i successi. La percentuale di
  interrogazioni riuscite (la "copertura") e' un indicatore di qualita' del
  dataset che va riportato nella documentazione: senza il denominatore non e'
  calcolabile a posteriori.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import logging
import logging.handlers
import random
import signal
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone, tzinfo
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import yaml

try:
    from google.transit import gtfs_realtime_pb2
except ImportError as errore:  # pragma: no cover - dipende dall'ambiente, non dalla logica
    raise SystemExit(
        "Manca il pacchetto gtfs-realtime-bindings.\n"
        "Attivare l'ambiente virtuale e installare le dipendenze:\n"
        "    pip install --only-binary=:all: -r requirements.txt"
    ) from errore


log = logging.getLogger("collector")

# I valori non ancora compilati in config.yaml iniziano tutti con questo prefisso.
# Sono riconoscibili a colpo d'occhio sia da un umano sia dal validatore.
PREFISSO_SEGNAPOSTO = "INSERIRE_QUI_"

# Tipi di feed real-time gestiti. trip_updates e' obbligatorio perche' e' l'unica
# fonte dei ritardi; vehicle_positions e' facoltativo e serve da ridondanza.
TIPI_FEED_RT = ("trip_updates", "vehicle_positions")
TIPI_FEED_OBBLIGATORI = ("trip_updates",)

# Colonne del manifest giornaliero. L'ordine e' parte del formato: viene riletto
# in Fase 3 per quantificare la copertura della raccolta.
COLONNE_MANIFEST = (
    "istante_utc",
    "istante_locale",
    "tipo_feed",
    "esito",
    "stato_http",
    "tentativi",
    "byte",
    "timestamp_feed",
    "n_entita",
    "file",
    "dettaglio",
)

ESITO_SALVATO = "salvato"
ESITO_DUPLICATO = "duplicato"
ESITO_ERRORE_RETE = "errore_rete"
ESITO_ERRORE_HTTP = "errore_http"
ESITO_NON_VALIDO = "payload_non_valido"

# Nomi dei file di servizio. Iniziano con "_" (tranne quelli richiesti altrove
# con un nome preciso) per restare in cima all'elenco e non essere scambiati per
# dati raccolti.
NOME_INDICE_GTFS = "index.json"
NOME_BATTITO = "_battito.json"
NOME_GAPS = "gaps.jsonl"

# Cause registrate in gaps.jsonl.
CAUSA_PROCESSO_FERMO = "processo_non_attivo"
CAUSA_ERRORI_RETE = "errori_di_rete_prolungati"


# =============================================================================
# Eccezioni
# =============================================================================


class ErroreConfigurazione(Exception):
    """Configurazione assente, malformata o con segnaposto non sostituiti."""


class FeedNonValido(Exception):
    """Il payload scaricato non e' un GTFS Real-Time riconoscibile."""


# =============================================================================
# Configurazione
# =============================================================================


@dataclass(frozen=True)
class ConfigRaccolta:
    """Parametri globali della raccolta, condivisi da tutte le citta'."""

    intervallo_polling_secondi: int
    timeout_richiesta_secondi: float
    timeout_gtfs_statico_secondi: float
    tentativi_max: int
    backoff_base_secondi: float
    backoff_max_secondi: float
    snapshot_gtfs_statico: bool
    soglia_interruzione_secondi: float
    cartella_rt: Path
    cartella_gtfs: Path
    cartella_log: Path
    user_agent: str


@dataclass(frozen=True)
class ConfigCitta:
    """Una citta' monitorata.

    ``feed_rt`` contiene solo i feed effettivamente configurati: i tipi
    facoltativi lasciati a ``null`` non compaiono affatto, cosi' il ciclo di
    polling non deve verificare a ogni giro se un indirizzo e' assente.
    """

    nome: str
    attiva: bool
    fuso_orario: str
    url_gtfs_statico: str | None
    url_gtfs_statico_md5: str | None
    feed_rt: dict[str, str]
    intestazioni_http: dict[str, str]

    @property
    def indirizzi_in_chiaro(self) -> tuple[str, ...]:
        """Indirizzi serviti in HTTP anziche' HTTPS.

        Non e' un errore di configurazione (GTT pubblica i propri feed solo in
        chiaro, e rifiutarli significherebbe rinunciare a Torino), ma va tenuto
        sotto gli occhi: il traffico e' leggibile e alterabile da chiunque stia
        sul percorso. Vedere anche il controllo che vieta di inviare credenziali
        su un indirizzo non cifrato.
        """
        candidati = [self.url_gtfs_statico, self.url_gtfs_statico_md5, *self.feed_rt.values()]
        return tuple(u for u in candidati if isinstance(u, str) and u.lower().startswith("http://"))


@dataclass(frozen=True)
class Configurazione:
    raccolta: ConfigRaccolta
    citta: tuple[ConfigCitta, ...]


def e_segnaposto(valore: Any) -> bool:
    """Vero se il valore e' un segnaposto di config.yaml mai sostituito.

    Serve a trasformare una dimenticanza in un errore immediato all'avvio invece
    che in tre giorni di raccolta vuota scoperti troppo tardi.
    """
    return isinstance(valore, str) and valore.strip().startswith(PREFISSO_SEGNAPOSTO)


def _url_utilizzabile(valore: Any) -> bool:
    """Vero se il valore sembra un indirizzo http(s) davvero compilato."""
    if not isinstance(valore, str) or e_segnaposto(valore):
        return False
    return valore.strip().lower().startswith(("http://", "https://"))


def _leggi_citta(grezza: Any, indice: int, problemi: list[str]) -> ConfigCitta | None:
    """Converte una voce della lista ``citta`` accumulando i problemi trovati.

    Accumula invece di sollevare al primo errore perche' chi compila il file per
    la prima volta preferisce vedere tutte le cose da sistemare in una volta.
    """
    etichetta = f"citta[{indice}]"
    if not isinstance(grezza, dict):
        problemi.append(f"{etichetta}: deve essere un blocco di chiave/valore.")
        return None

    nome = grezza.get("nome")
    if not isinstance(nome, str) or not nome.strip():
        problemi.append(f"{etichetta}: manca il campo obbligatorio 'nome'.")
        return None
    nome = nome.strip()
    etichetta = f"citta '{nome}'"

    # Il nome diventa un pezzo di percorso su disco: vietiamo subito i caratteri
    # che romperebbero il filesystem, invece di scoprirlo alla prima scrittura.
    if any(carattere in nome for carattere in '\\/:*?"<>| '):
        problemi.append(
            f"{etichetta}: il nome finisce in un percorso di cartella, "
            "quindi non puo' contenere spazi ne' i caratteri \\ / : * ? \" < > |."
        )

    attiva = bool(grezza.get("attiva", True))

    fuso = grezza.get("fuso_orario")
    if not isinstance(fuso, str) or not fuso.strip():
        problemi.append(f"{etichetta}: manca 'fuso_orario' (esempio: Europe/Rome).")
        fuso = "UTC"

    grezzi_feed = grezza.get("feed_rt") or {}
    if not isinstance(grezzi_feed, dict):
        problemi.append(f"{etichetta}: 'feed_rt' deve essere un blocco di chiave/valore.")
        grezzi_feed = {}

    feed: dict[str, str] = {}
    for tipo in TIPI_FEED_RT:
        valore = grezzi_feed.get(tipo)
        if _url_utilizzabile(valore):
            feed[tipo] = valore.strip()
        elif tipo in TIPI_FEED_OBBLIGATORI and attiva:
            problemi.append(
                f"{etichetta}: 'feed_rt.{tipo}' non e' compilato. "
                "E' l'unica fonte dei ritardi: senza, la citta' non produce dati utili. "
                "Compilarlo, oppure mettere 'attiva: false' per escludere la citta'."
            )
        elif valore is not None and not e_segnaposto(valore):
            problemi.append(f"{etichetta}: 'feed_rt.{tipo}' non e' un indirizzo http(s) valido.")

    grezzo_statico = grezza.get("url_gtfs_statico")
    statico = grezzo_statico.strip() if _url_utilizzabile(grezzo_statico) else None

    grezzo_md5 = grezza.get("url_gtfs_statico_md5")
    md5 = grezzo_md5.strip() if _url_utilizzabile(grezzo_md5) else None
    if md5 is not None and statico is None:
        problemi.append(
            f"{etichetta}: 'url_gtfs_statico_md5' e' configurato ma 'url_gtfs_statico' no. "
            "L'impronta da sola non serve a nulla: senza l'archivio non c'e' cosa verificare."
        )

    intestazioni = grezza.get("intestazioni_http") or {}
    if not isinstance(intestazioni, dict):
        problemi.append(f"{etichetta}: 'intestazioni_http' deve essere un blocco di chiave/valore.")
        intestazioni = {}

    interpretata = ConfigCitta(
        nome=nome,
        attiva=attiva,
        fuso_orario=fuso,
        url_gtfs_statico=statico,
        url_gtfs_statico_md5=md5,
        feed_rt=feed,
        intestazioni_http={str(k): str(v) for k, v in intestazioni.items()},
    )

    # Gli indirizzi in HTTP sono ammessi (senza, Torino sarebbe fuori dal
    # progetto), ma spedirci sopra delle credenziali no: viaggerebbero in chiaro
    # e sarebbero leggibili da chiunque stia sul percorso. Meglio un rifiuto
    # all'avvio che una chiave d'accesso regalata alla rete per settimane.
    if interpretata.intestazioni_http and interpretata.indirizzi_in_chiaro:
        problemi.append(
            f"{etichetta}: 'intestazioni_http' non e' vuoto ma alcuni indirizzi sono in HTTP "
            f"({', '.join(interpretata.indirizzi_in_chiaro)}). Le credenziali viaggerebbero in "
            "chiaro: usare HTTPS, oppure togliere le intestazioni."
        )

    return interpretata


def interpreta_configurazione(grezza: Any, radice: Path) -> Configurazione:
    """Valida la struttura gia' deserializzata dal YAML.

    E' separata da :func:`carica_configurazione` perche' e' pura: prende dati e
    restituisce dati, quindi si presta a essere collaudata senza toccare il
    disco.
    """
    problemi: list[str] = []
    if not isinstance(grezza, dict):
        raise ErroreConfigurazione("Il file di configurazione deve contenere un blocco YAML.")

    sezione = grezza.get("raccolta") or {}
    if not isinstance(sezione, dict):
        raise ErroreConfigurazione("La sezione 'raccolta' deve essere un blocco di chiave/valore.")

    def _numero(chiave: str, predefinito: float, minimo: float) -> float:
        valore = sezione.get(chiave, predefinito)
        try:
            valore = float(valore)
        except (TypeError, ValueError):
            problemi.append(f"raccolta.{chiave}: deve essere un numero.")
            return predefinito
        if valore < minimo:
            problemi.append(f"raccolta.{chiave}: deve essere almeno {minimo:g}.")
            return predefinito
        return valore

    intervallo = int(_numero("intervallo_polling_secondi", 60, 5))
    timeout = _numero("timeout_richiesta_secondi", 20.0, 1.0)
    timeout_statico = _numero("timeout_gtfs_statico_secondi", 300.0, 5.0)
    tentativi = int(_numero("tentativi_max", 3, 1))
    backoff_base = _numero("backoff_base_secondi", 2.0, 0.1)
    backoff_max = _numero("backoff_max_secondi", 20.0, 0.1)
    soglia_interruzione = _numero("soglia_interruzione_secondi", 300.0, 1.0)

    # Un timeout piu' lungo dell'intervallo farebbe accumulare ritardo a ogni
    # tick, snaturando la cadenza di campionamento dichiarata.
    if timeout >= intervallo:
        problemi.append(
            f"raccolta.timeout_richiesta_secondi ({timeout:g}) deve essere minore "
            f"di raccolta.intervallo_polling_secondi ({intervallo})."
        )

    def _cartella(chiave: str, predefinita: str) -> Path:
        valore = sezione.get(chiave, predefinita)
        percorso = Path(str(valore))
        return percorso if percorso.is_absolute() else (radice / percorso)

    raccolta = ConfigRaccolta(
        intervallo_polling_secondi=intervallo,
        timeout_richiesta_secondi=timeout,
        timeout_gtfs_statico_secondi=timeout_statico,
        tentativi_max=tentativi,
        backoff_base_secondi=backoff_base,
        backoff_max_secondi=max(backoff_base, backoff_max),
        snapshot_gtfs_statico=bool(sezione.get("snapshot_gtfs_statico", True)),
        soglia_interruzione_secondi=soglia_interruzione,
        cartella_rt=_cartella("cartella_rt", "data/raw/rt"),
        cartella_gtfs=_cartella("cartella_gtfs", "data/raw/gtfs"),
        cartella_log=_cartella("cartella_log", "logs"),
        user_agent=str(sezione.get("user_agent", "progetto-icon-tpl/0.1")),
    )

    elenco = grezza.get("citta")
    if not isinstance(elenco, list) or not elenco:
        raise ErroreConfigurazione("La sezione 'citta' deve essere una lista non vuota.")

    citta: list[ConfigCitta] = []
    for indice, voce in enumerate(elenco):
        interpretata = _leggi_citta(voce, indice, problemi)
        if interpretata is not None:
            citta.append(interpretata)

    nomi = [c.nome for c in citta]
    duplicati = sorted({n for n in nomi if nomi.count(n) > 1})
    if duplicati:
        problemi.append(f"nomi di citta' duplicati: {', '.join(duplicati)}.")

    if citta and not any(c.attiva for c in citta):
        problemi.append("nessuna citta' e' attiva: non ci sarebbe nulla da raccogliere.")

    if problemi:
        raise ErroreConfigurazione(
            "Configurazione non utilizzabile:\n  - " + "\n  - ".join(problemi)
        )

    return Configurazione(raccolta=raccolta, citta=tuple(citta))


def carica_configurazione(percorso: Path) -> Configurazione:
    """Legge e valida config.yaml. I percorsi relativi sono risolti rispetto al file."""
    percorso = Path(percorso)
    if not percorso.is_file():
        raise ErroreConfigurazione(f"File di configurazione non trovato: {percorso}")
    try:
        grezza = yaml.safe_load(percorso.read_text(encoding="utf-8"))
    except yaml.YAMLError as errore:
        raise ErroreConfigurazione(f"YAML non valido in {percorso}:\n{errore}") from errore
    return interpreta_configurazione(grezza, percorso.resolve().parent)


# =============================================================================
# Logica pura: attese, percorsi, deduplica
# =============================================================================


def ritardo_backoff(
    tentativo: int,
    base_secondi: float,
    massimo_secondi: float,
    frazione_jitter: float = 0.25,
    casuale: float | None = None,
) -> float:
    """Attesa prima di un nuovo tentativo, con crescita esponenziale e jitter.

    Il jitter non e' un vezzo: piu' citta' vengono interrogate dallo stesso
    processo e, in caso di guasto comune (per esempio la rete di casa che cade),
    tutte ritenterebbero nello stesso identico istante. Sfasare le riprese evita
    di bersagliare il server dell'agenzia appena torna disponibile.

    ``casuale`` esiste per rendere la funzione deterministica nei test: e' il
    valore in [0, 1] che altrimenti verrebbe estratto a caso.
    """
    if tentativo < 1:
        raise ValueError("Il numero di tentativo parte da 1.")
    attesa = min(base_secondi * (2 ** (tentativo - 1)), massimo_secondi)
    estratto = random.random() if casuale is None else casuale
    fattore = 1.0 + frazione_jitter * (2.0 * estratto - 1.0)
    return max(0.0, attesa * fattore)


def risolvi_fuso(nome: str) -> tzinfo:
    """Restituisce il fuso IANA richiesto, con ripiego sul fuso di sistema.

    Windows non include il database IANA: se per qualsiasi motivo ``tzdata`` non
    fosse installato preferiamo continuare a raccogliere usando l'ora locale
    della macchina, segnalandolo, piuttosto che interrompere la raccolta.
    Perdere dati e' un danno permanente; una data di servizio calcolata con il
    fuso sbagliato e' un problema correggibile a posteriori.
    """
    try:
        return ZoneInfo(nome)
    except (ZoneInfoNotFoundError, ValueError, KeyError):
        log.warning(
            "Fuso orario '%s' non disponibile (manca il pacchetto tzdata?): "
            "uso il fuso locale della macchina.",
            nome,
        )
        locale = datetime.now().astimezone().tzinfo
        return locale if locale is not None else timezone.utc


def percorso_dump(
    cartella_rt: Path,
    citta: str,
    tipo_feed: str,
    momento_locale: datetime,
    esiste: Callable[[Path], bool] | None = None,
) -> Path:
    """Percorso del file in cui salvare un dump, evitando le collisioni.

    Il raggruppamento e' per data LOCALE della citta', non per data UTC, perche'
    la ``service_date`` del GTFS e' un concetto in ora locale: cosi' la cartella
    di un giorno contiene esattamente le osservazioni di quel giorno di servizio
    e il join della Fase 3 non deve ricostruire nulla.

    Il tipo di feed e' una sottocartella e non un suffisso nel nome perche' la
    Fase 3 legge solo i trip_updates: una cartella dedicata rende la selezione
    una questione di percorso invece che di filtro sul nome del file.

    Nel giorno in cui finisce l'ora legale l'ora locale si ripete: senza il
    suffisso progressivo il secondo passaggio sovrascriverebbe il primo,
    cancellando dati veri.
    """
    esiste = (lambda p: p.exists()) if esiste is None else esiste
    cartella = cartella_rt / citta / momento_locale.strftime("%Y-%m-%d") / tipo_feed
    base = momento_locale.strftime("%H%M%S")
    candidato = cartella / f"{base}.pb"
    contatore = 1
    while esiste(candidato):
        candidato = cartella / f"{base}_{contatore}.pb"
        contatore += 1
    return candidato


def deve_salvare(timestamp_corrente: int | None, timestamp_precedente: int | None) -> bool:
    """Decide se il dump appena scaricato porta informazione nuova.

    Le agenzie rigenerano il feed con una loro cadenza (tipicamente 30-120 s) che
    non e' sincronizzata con la nostra: interrogando ogni 60 s capita spesso di
    riottenere byte per byte la fotografia precedente. Riconoscerlo dal campo
    ``header.timestamp`` e scartare il duplicato non serve solo a risparmiare
    disco: conservando i duplicati, la Fase 3 conterebbe piu' volte la stessa
    osservazione e gonfierebbe artificialmente la numerosita' campionaria su cui
    si calcolano medie e deviazioni standard.

    Un feed che non valorizza ``header.timestamp`` (valore assente o zero) non
    permette questo confronto: in quel caso conserviamo tutto, perche' scartare
    per errore un'osservazione vera costa piu' che tenere un duplicato.
    """
    if not timestamp_corrente:
        return True
    return timestamp_corrente != timestamp_precedente


# =============================================================================
# Analisi del payload
# =============================================================================


@dataclass(frozen=True)
class RiepilogoFeed:
    """Cosa contiene davvero un feed, al di la' del fatto che sia ben formato."""

    versione: str
    timestamp_feed: int
    n_entita: int
    n_trip_update: int
    n_vehicle: int
    n_alert: int
    n_stop_time_update: int
    n_con_ritardo: int
    n_con_orario_assoluto: int
    relazioni_orario: dict[str, int] = field(default_factory=dict)


def _nome_relazione_orario(valore: int) -> str:
    """Nome leggibile dell'enumerativo ScheduleRelationship, con ripiego numerico."""
    try:
        return gtfs_realtime_pb2.TripDescriptor.ScheduleRelationship.Name(valore)
    except Exception:
        return f"SCONOSCIUTO_{valore}"


def analizza_feed(dati: bytes) -> RiepilogoFeed:
    """Verifica che i byte siano un GTFS Real-Time e ne riassume il contenuto.

    La validazione non puo' fermarsi al ``ParseFromString``: il formato protobuf
    e' volutamente permissivo e accetta senza protestare sequenze di byte che non
    sono un feed, per esempio una pagina HTML di errore o una redirezione a una
    schermata di accesso. Un feed autentico dichiara sempre la propria versione
    nell'intestazione, quindi usiamo quel campo come discriminante e scartiamo a
    monte i payload che iniziano come un documento di markup.

    Senza questo controllo il rischio concreto e' accumulare settimane di file
    ``.pb`` che in Fase 3 si rivelano pagine di errore, quando non c'e' piu' modo
    di rimediare.
    """
    if not dati:
        raise FeedNonValido("payload vuoto")
    if dati.lstrip()[:1] in (b"<", b"{"):
        raise FeedNonValido("il payload sembra HTML/JSON, non un protobuf")

    messaggio = gtfs_realtime_pb2.FeedMessage()
    try:
        messaggio.ParseFromString(dati)
    except Exception as errore:  # protobuf solleva tipi diversi a seconda del caso
        raise FeedNonValido(f"protobuf illeggibile: {errore}") from errore

    if not messaggio.header.gtfs_realtime_version:
        raise FeedNonValido("manca header.gtfs_realtime_version: non e' un feed GTFS-RT")

    n_trip = n_veicoli = n_avvisi = 0
    n_stu = n_ritardo = n_assoluto = 0
    relazioni: dict[str, int] = {}

    for entita in messaggio.entity:
        if entita.HasField("trip_update"):
            n_trip += 1
            aggiornamento = entita.trip_update
            nome_relazione = _nome_relazione_orario(aggiornamento.trip.schedule_relationship)
            relazioni[nome_relazione] = relazioni.get(nome_relazione, 0) + 1
            for tappa in aggiornamento.stop_time_update:
                n_stu += 1
                # Si guarda l'arrivo e, solo se assente, la partenza: e' l'arrivo
                # a determinare se una coincidenza si prende o si perde.
                for evento in ("arrival", "departure"):
                    if tappa.HasField(evento):
                        dettaglio = getattr(tappa, evento)
                        if dettaglio.HasField("delay"):
                            n_ritardo += 1
                        if dettaglio.HasField("time"):
                            n_assoluto += 1
                        break
        if entita.HasField("vehicle"):
            n_veicoli += 1
        if entita.HasField("alert"):
            n_avvisi += 1

    return RiepilogoFeed(
        versione=messaggio.header.gtfs_realtime_version,
        timestamp_feed=int(messaggio.header.timestamp),
        n_entita=len(messaggio.entity),
        n_trip_update=n_trip,
        n_vehicle=n_veicoli,
        n_alert=n_avvisi,
        n_stop_time_update=n_stu,
        n_con_ritardo=n_ritardo,
        n_con_orario_assoluto=n_assoluto,
        relazioni_orario=relazioni,
    )


# =============================================================================
# Rete
# =============================================================================


@dataclass(frozen=True)
class RisultatoDownload:
    ok: bool
    dati: bytes | None
    stato_http: int | None
    tentativi: int
    esito: str
    dettaglio: str


def scarica(
    url: str,
    intestazioni: dict[str, str],
    timeout: float,
    tentativi_max: int,
    backoff_base: float,
    backoff_max: float,
    dormi: Callable[[float], None] = time.sleep,
    apri: Callable[..., Any] | None = None,
) -> RisultatoDownload:
    """Scarica un indirizzo con ritentativi, senza mai propagare eccezioni.

    Il chiamante e' un ciclo che deve girare per settimane: qualunque errore di
    rete deve tradursi in un valore di ritorno da registrare, mai in un'eccezione
    che possa terminare il processo.

    Gli errori 4xx non vengono ritentati: un 401 o un 404 non si risolvono
    riprovando fra due secondi, e insistere significherebbe solo martellare il
    server dell'agenzia con richieste che sappiamo destinate a fallire.

    ``dormi`` e ``apri`` sono iniettabili per permettere ai test di verificare la
    sequenza dei ritentativi senza rete e senza attese reali. ``apri`` viene
    risolto qui e non come valore predefinito del parametro perche' un default
    valutato alla definizione catturerebbe per sempre la funzione originale,
    rendendo impossibile sostituirla dall'esterno.
    """
    apri = urllib.request.urlopen if apri is None else apri
    ultimo_dettaglio = "nessun tentativo eseguito"
    ultimo_esito = ESITO_ERRORE_RETE
    ultimo_stato: int | None = None
    tentativi_eseguiti = 0

    for tentativo in range(1, tentativi_max + 1):
        tentativi_eseguiti = tentativo
        richiesta = urllib.request.Request(url, headers=dict(intestazioni), method="GET")
        try:
            with apri(richiesta, timeout=timeout) as risposta:
                dati = risposta.read()
                return RisultatoDownload(
                    ok=True,
                    dati=dati,
                    stato_http=getattr(risposta, "status", 200),
                    tentativi=tentativo,
                    esito=ESITO_SALVATO,
                    dettaglio="",
                )
        except urllib.error.HTTPError as errore:
            ultimo_stato = errore.code
            ultimo_esito = ESITO_ERRORE_HTTP
            ultimo_dettaglio = f"HTTP {errore.code} {errore.reason}"
            if 400 <= errore.code < 500:
                break
        except urllib.error.URLError as errore:
            ultimo_esito = ESITO_ERRORE_RETE
            ultimo_dettaglio = f"rete: {errore.reason}"
        except Exception as errore:  # timeout del socket, DNS, TLS, decompressione...
            ultimo_esito = ESITO_ERRORE_RETE
            ultimo_dettaglio = f"{type(errore).__name__}: {errore}"

        if tentativo < tentativi_max:
            dormi(ritardo_backoff(tentativo, backoff_base, backoff_max))

    return RisultatoDownload(
        ok=False,
        dati=None,
        stato_http=ultimo_stato,
        tentativi=tentativi_eseguiti,
        esito=ultimo_esito,
        dettaglio=ultimo_dettaglio,
    )


# =============================================================================
# Manifest giornaliero
# =============================================================================


def scrivi_riga_manifest(percorso: Path, riga: dict[str, Any]) -> None:
    """Aggiunge una riga al manifest del giorno, creandolo con l'intestazione.

    Il file viene aperto e chiuso a ogni riga invece di essere tenuto aperto: al
    ritmo di poche scritture al minuto il costo e' irrilevante, mentre la
    garanzia che nulla resti in un buffer non scritto in caso di spegnimento
    improvviso vale molto di piu'.
    """
    percorso.parent.mkdir(parents=True, exist_ok=True)
    nuovo = not percorso.exists()
    with percorso.open("a", encoding="utf-8", newline="") as flusso:
        scrittore = csv.DictWriter(flusso, fieldnames=list(COLONNE_MANIFEST))
        if nuovo:
            scrittore.writeheader()
        scrittore.writerow({colonna: riga.get(colonna, "") for colonna in COLONNE_MANIFEST})


# =============================================================================
# Archiviazione dell'orario statico
# =============================================================================


def _md5(dati: bytes) -> str:
    """Impronta MD5 dell'archivio.

    La scelta non e' crittografica ma di interoperabilita': MD5 e' l'impronta che
    le agenzie pubblicano accanto allo zip (Roma Mobilita' espone un file .md5
    affiancato all'archivio), e usare la stessa funzione permette di accorgersi
    che l'orario e' cambiato scaricando cinquanta byte invece di decine di MB.
    """
    return hashlib.md5(dati).hexdigest()


def interpreta_md5(dati: bytes) -> str | None:
    """Estrae l'impronta da un file .md5 nel formato prodotto da ``md5sum``.

    Il formato realmente pubblicato da Roma Mobilita', verificato scaricandolo,
    e' ``e328ed0e82a9294dc6a20b7117200375  rsm/rome_static_gtfs.zip``: impronta,
    spazi, percorso. Prendiamo il primo campo e lo accettiamo solo se e' davvero
    esadecimale di 32 caratteri, perche' una pagina di errore restituita con
    stato 200 supererebbe qualunque controllo piu' permissivo e ci convincerebbe
    che l'orario e' cambiato tutti i giorni.
    """
    try:
        testo = dati.decode("ascii", errors="strict").strip()
    except UnicodeDecodeError:
        return None
    if not testo:
        return None
    primo = testo.split()[0].lower()
    if len(primo) == 32 and all(carattere in "0123456789abcdef" for carattere in primo):
        return primo
    return None


@dataclass(frozen=True)
class EsitoOrarioStatico:
    """Cosa e' successo al controllo giornaliero dell'orario statico."""

    origine: str  # "scaricato" | "invariato" | "fallito"
    md5: str | None
    file: str | None


def indice_vuoto(citta: str) -> dict[str, Any]:
    """Struttura iniziale di index.json.

    ``giorni`` mappa ogni data alla versione dell'orario valida quel giorno;
    ``versioni`` raccoglie le revisioni distinte, cosi' una revisione che ritorna
    identica non produce un secondo archivio.
    """
    return {"citta": citta, "aggiornato": None, "giorni": {}, "versioni": {}}


def carica_indice(percorso: Path, citta: str) -> dict[str, Any]:
    """Legge index.json, ripartendo da vuoto se e' illeggibile.

    Un indice corrotto non deve impedire la raccolta del real-time, che e'
    l'unico dato irripetibile: al peggio si riscarica l'orario statico, che e'
    sempre recuperabile.
    """
    if not percorso.is_file():
        return indice_vuoto(citta)
    try:
        indice = json.loads(percorso.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        log.warning("[%s] index.json illeggibile: ne creo uno nuovo.", citta)
        return indice_vuoto(citta)
    if not isinstance(indice, dict) or "giorni" not in indice:
        return indice_vuoto(citta)
    indice.setdefault("citta", citta)
    indice.setdefault("versioni", {})
    return indice


def salva_indice(percorso: Path, indice: dict[str, Any]) -> None:
    percorso.parent.mkdir(parents=True, exist_ok=True)
    percorso.write_text(
        json.dumps(indice, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8"
    )


def versione_valida(indice: dict[str, Any], data_locale: str) -> dict[str, Any] | None:
    """Versione dell'orario statico in vigore in una certa data di servizio.

    Se per quella data non c'e' una voce esplicita (per esempio perche' il
    collector era fermo), si ripiega sulla data precedente piu' vicina: l'orario
    in vigore resta quello finche' l'agenzia non ne pubblica uno nuovo. E' la
    funzione che la Fase 3 usera' per sapere con quale archivio interpretare i
    ``trip_id`` di un certo giorno.
    """
    giorni = indice.get("giorni") or {}
    if data_locale in giorni:
        return giorni[data_locale]
    precedenti = [data for data in giorni if data < data_locale]
    if not precedenti:
        return None
    return giorni[max(precedenti)]


def forse_archivia_orario(
    citta: ConfigCitta,
    raccolta: ConfigRaccolta,
    data_locale: str,
    momento_utc: datetime | None = None,
) -> EsitoOrarioStatico | None:
    """Controlla una volta al giorno l'orario statico e ne archivia le revisioni.

    Perche' questo controllo vive dentro il collector e non in uno script a
    parte: gli identificativi di corsa del feed real-time hanno senso solo
    rispetto alla versione dell'orario statico in vigore quel giorno. L'orario di
    Roma cambia quasi ogni giorno e i ``trip_id`` non sono stabili nel tempo; se
    scaricassimo il GTFS statico una volta sola a fine campagna, i dump gia'
    raccolti diventerebbero impossibili da interpretare e l'intero dataset
    sarebbe inutilizzabile in backtesting.

    Il confronto passa dal file ``.md5`` quando l'agenzia lo pubblica: costa una
    cinquantina di byte al giorno invece di decine di MB, e permette di
    accorgersi che nulla e' cambiato senza scaricare nulla. Quando il ``.md5``
    manca o non e' raggiungibile si ripiega sullo scaricamento dell'archivio e
    sul confronto della sua impronta, che porta allo stesso risultato pagando
    banda.

    Nei giorni senza modifiche non viene scritto un nuovo archivio ma solo un
    marcatore in ``index.json`` che punta alla versione precedente: e' cio' che
    permette alla Fase 3 di risalire, per ogni data, all'orario giusto.
    """
    if not raccolta.snapshot_gtfs_statico or not citta.url_gtfs_statico:
        return None

    momento_utc = datetime.now(timezone.utc) if momento_utc is None else momento_utc
    cartella = raccolta.cartella_gtfs / citta.nome
    cartella.mkdir(parents=True, exist_ok=True)
    percorso_indice = cartella / NOME_INDICE_GTFS
    indice = carica_indice(percorso_indice, citta.nome)

    # Gia' controllato oggi: non ha senso ripetere il giro a ogni tick.
    if data_locale in (indice.get("giorni") or {}):
        return None

    intestazioni = {"User-Agent": raccolta.user_agent, **citta.intestazioni_http}
    precedente = versione_valida(indice, data_locale)
    md5_dichiarato: str | None = None

    if citta.url_gtfs_statico_md5:
        esito_md5 = scarica(
            citta.url_gtfs_statico_md5,
            intestazioni,
            raccolta.timeout_richiesta_secondi,
            tentativi_max=2,
            backoff_base=raccolta.backoff_base_secondi,
            backoff_max=raccolta.backoff_max_secondi,
        )
        if esito_md5.ok and esito_md5.dati is not None:
            md5_dichiarato = interpreta_md5(esito_md5.dati)
            if md5_dichiarato is None:
                log.warning(
                    "[%s] il file .md5 non contiene un'impronta riconoscibile: "
                    "ripiego sullo scaricamento dell'archivio.",
                    citta.nome,
                )
        else:
            log.warning(
                "[%s] .md5 non raggiungibile (%s): ripiego sullo scaricamento dell'archivio.",
                citta.nome,
                esito_md5.dettaglio,
            )

    # Caso migliore: l'agenzia dichiara la stessa impronta di ieri, quindi non
    # scarichiamo proprio nulla e registriamo solo il marcatore.
    if md5_dichiarato and precedente and md5_dichiarato == precedente.get("md5"):
        _registra_giorno(indice, data_locale, precedente["file"], md5_dichiarato, "invariato")
        indice["aggiornato"] = momento_utc.isoformat(timespec="seconds")
        salva_indice(percorso_indice, indice)
        log.info("[%s] orario statico invariato (%s).", citta.nome, md5_dichiarato[:8])
        return EsitoOrarioStatico("invariato", md5_dichiarato, precedente["file"])

    log.info("[%s] scarico l'orario statico (%s).", citta.nome, data_locale)
    risultato = scarica(
        citta.url_gtfs_statico,
        intestazioni,
        raccolta.timeout_gtfs_statico_secondi,
        tentativi_max=2,
        backoff_base=raccolta.backoff_base_secondi,
        backoff_max=raccolta.backoff_max_secondi,
    )
    if not risultato.ok or risultato.dati is None:
        # L'indice non viene toccato: cosi' il tentativo si ripete al ciclo
        # successivo invece di essere rimandato al giorno dopo.
        log.warning("[%s] orario statico non scaricato: %s", citta.nome, risultato.dettaglio)
        return EsitoOrarioStatico("fallito", None, None)

    if not risultato.dati.startswith(b"PK\x03\x04"):
        log.warning(
            "[%s] l'orario statico scaricato non e' un archivio zip (%d byte): ignorato.",
            citta.nome,
            len(risultato.dati),
        )
        return EsitoOrarioStatico("fallito", None, None)

    md5_reale = _md5(risultato.dati)
    if md5_dichiarato and md5_dichiarato != md5_reale:
        # Non e' necessariamente un errore: su un orario che cambia quasi ogni
        # giorno, l'agenzia puo' aver ripubblicato l'archivio fra la lettura del
        # .md5 e lo scaricamento. Fa fede l'impronta dei byte che abbiamo in mano.
        log.info(
            "[%s] il .md5 dichiarava %s ma l'archivio scaricato e' %s: "
            "l'orario e' probabilmente cambiato durante lo scaricamento.",
            citta.nome,
            md5_dichiarato[:8],
            md5_reale[:8],
        )

    versioni = indice.setdefault("versioni", {})
    if md5_reale in versioni:
        # Stessa revisione gia' archiviata (per esempio un rientro su una
        # versione precedente): riusiamo il file invece di duplicarlo.
        nome_file = versioni[md5_reale]["file"]
        origine = "invariato"
        log.info("[%s] orario statico gia' archiviato come %s.", citta.nome, nome_file)
    else:
        nome_file = f"{data_locale}.zip"
        (cartella / nome_file).write_bytes(risultato.dati)
        versioni[md5_reale] = {
            "file": nome_file,
            "prima_data": data_locale,
            "byte": len(risultato.dati),
        }
        origine = "scaricato"
        log.info(
            "[%s] nuova revisione dell'orario statico archiviata: %s (%.1f MB, md5 %s).",
            citta.nome,
            nome_file,
            len(risultato.dati) / 1_048_576,
            md5_reale[:8],
        )

    _registra_giorno(indice, data_locale, nome_file, md5_reale, origine)
    indice["aggiornato"] = momento_utc.isoformat(timespec="seconds")
    salva_indice(percorso_indice, indice)
    return EsitoOrarioStatico(origine, md5_reale, nome_file)


def _registra_giorno(
    indice: dict[str, Any], data_locale: str, file: str, md5: str, origine: str
) -> None:
    indice.setdefault("giorni", {})[data_locale] = {
        "file": file,
        "md5": md5,
        "origine": origine,
    }


# =============================================================================
# Registro delle interruzioni
# =============================================================================


def scrivi_gap(
    percorso: Path,
    citta: str,
    inizio: datetime,
    fine: datetime,
    causa: str,
    dettaglio: str = "",
) -> None:
    """Aggiunge una riga a gaps.jsonl per una finestra senza raccolta.

    Serve a due cose che senza questo file sarebbero impossibili: escludere dal
    backtesting le finestre in cui non abbiamo osservato nulla (altrimenti una
    coincidenza "persa" potrebbe essere solo una coincidenza non osservata), e
    dichiarare onestamente la copertura nella documentazione. Il formato e'
    JSONL perche' e' append-only: una riga per volta, senza rileggere il file.
    """
    percorso.parent.mkdir(parents=True, exist_ok=True)
    riga = {
        "citta": citta,
        "inizio": inizio.isoformat(timespec="seconds"),
        "fine": fine.isoformat(timespec="seconds"),
        "durata_secondi": round((fine - inizio).total_seconds()),
        "causa": causa,
        "dettaglio": dettaglio,
    }
    with percorso.open("a", encoding="utf-8") as flusso:
        flusso.write(json.dumps(riga, ensure_ascii=False) + "\n")


def leggi_battito(percorso: Path) -> datetime | None:
    """Istante dell'ultima raccolta riuscita registrata dal processo precedente.

    E' cio' che permette, al riavvio, di sapere da quando il collector non
    raccoglieva e quindi di chiudere la finestra di interruzione con l'istante
    giusto invece che con quello dell'avvio.
    """
    if not percorso.is_file():
        return None
    try:
        dati = json.loads(percorso.read_text(encoding="utf-8"))
        return datetime.fromisoformat(dati["ultimo_successo"])
    except (json.JSONDecodeError, OSError, KeyError, ValueError, TypeError):
        return None


def scrivi_battito(percorso: Path, momento: datetime) -> None:
    percorso.parent.mkdir(parents=True, exist_ok=True)
    percorso.write_text(
        json.dumps({"ultimo_successo": momento.isoformat(timespec="seconds")}, ensure_ascii=False),
        encoding="utf-8",
    )


def e_interruzione(inizio: datetime, fine: datetime, soglia_secondi: float) -> bool:
    """Vero se la finestra e' abbastanza lunga da valere come interruzione.

    La soglia esiste per non trasformare ogni singolo errore isolato in una
    riga di gaps.jsonl: con un polling a 60 s, un tick perso e recuperato subito
    non e' un buco nei dati, e' rumore.
    """
    return (fine - inizio).total_seconds() >= soglia_secondi


# =============================================================================
# Ciclo di raccolta
# =============================================================================


@dataclass
class Contatori:
    """Statistiche cumulate, azzerate a ogni riepilogo orario."""

    salvati: int = 0
    duplicati: int = 0
    errori_rete: int = 0
    errori_http: int = 0
    non_validi: int = 0
    byte: int = 0

    @property
    def interrogazioni(self) -> int:
        return self.salvati + self.duplicati + self.errori_rete + self.errori_http + self.non_validi

    @property
    def copertura(self) -> float:
        """Quota di interrogazioni che hanno restituito un feed valido.

        I duplicati contano come successi: un duplicato significa che il feed ha
        risposto correttamente, solo che non era cambiato. E' il feed ad avere
        una cadenza piu' lenta della nostra, non la raccolta ad aver fallito.
        """
        totale = self.interrogazioni
        return 0.0 if totale == 0 else (self.salvati + self.duplicati) / totale

    def azzera(self) -> None:
        self.salvati = self.duplicati = self.errori_rete = self.errori_http = 0
        self.non_validi = 0
        self.byte = 0


@dataclass
class StatoCitta:
    """Stato volatile di una citta' fra un tick e il successivo."""

    ultimo_timestamp_feed: dict[str, int | None] = field(default_factory=dict)
    contatori: Contatori = field(default_factory=Contatori)
    totali: Contatori = field(default_factory=Contatori)
    # Istante dell'ultima raccolta riuscita e inizio della finestra di errori
    # attualmente aperta: insieme bastano a ricostruire ogni interruzione senza
    # tenere in memoria la storia completa.
    ultimo_successo: datetime | None = None
    interruzione_aperta: datetime | None = None


def _registra(contatori: Iterable[Contatori], esito: str, byte: int) -> None:
    for singolo in contatori:
        if esito == ESITO_SALVATO:
            singolo.salvati += 1
            singolo.byte += byte
        elif esito == ESITO_DUPLICATO:
            singolo.duplicati += 1
        elif esito == ESITO_ERRORE_HTTP:
            singolo.errori_http += 1
        elif esito == ESITO_NON_VALIDO:
            singolo.non_validi += 1
        else:
            singolo.errori_rete += 1


def _aggiorna_interruzioni(
    citta: ConfigCitta,
    raccolta: ConfigRaccolta,
    stato: StatoCitta,
    esiti: Sequence[str],
    momento_utc: datetime,
) -> None:
    """Apre e chiude le finestre di interruzione al termine di ogni giro.

    Una finestra si considera aperta solo quando la distanza dall'ultima
    raccolta riuscita supera la soglia configurata, e viene scritta su disco solo
    quando si richiude, perche' prima di allora non se ne conosce la fine. Se il
    processo muore mentre una finestra e' aperta, il battito su disco resta
    fermo all'ultimo successo e sara' l'avvio successivo a registrarla: e' il
    motivo per cui il battito viene aggiornato solo sui giri riusciti.

    Un giro conta come riuscito se almeno un feed ha risposto, duplicato
    compreso: un duplicato significa che il feed e' raggiungibile e sta
    funzionando, solo che non e' cambiato.
    """
    percorso_gaps = raccolta.cartella_rt / citta.nome / NOME_GAPS
    percorso_battito = raccolta.cartella_rt / citta.nome / NOME_BATTITO
    riuscito = any(esito in (ESITO_SALVATO, ESITO_DUPLICATO) for esito in esiti)

    if riuscito:
        if stato.interruzione_aperta is not None:
            scrivi_gap(
                percorso_gaps,
                citta.nome,
                stato.interruzione_aperta,
                momento_utc,
                CAUSA_ERRORI_RETE,
                "nessun feed raggiungibile per piu' della soglia configurata",
            )
            log.warning(
                "[%s] interruzione chiusa: %.0f minuti senza raccolta.",
                citta.nome,
                (momento_utc - stato.interruzione_aperta).total_seconds() / 60,
            )
            stato.interruzione_aperta = None
        stato.ultimo_successo = momento_utc
        scrivi_battito(percorso_battito, momento_utc)
        return

    riferimento = stato.ultimo_successo
    if riferimento is None or stato.interruzione_aperta is not None:
        return
    if e_interruzione(riferimento, momento_utc, raccolta.soglia_interruzione_secondi):
        stato.interruzione_aperta = riferimento
        log.warning(
            "[%s] nessuna raccolta riuscita da %s: interruzione in corso.",
            citta.nome,
            riferimento.isoformat(timespec="seconds"),
        )


def raccogli_feed(
    citta: ConfigCitta,
    tipo_feed: str,
    url: str,
    raccolta: ConfigRaccolta,
    stato: StatoCitta,
    momento_utc: datetime,
    momento_locale: datetime,
) -> str:
    """Esegue una singola interrogazione, ne registra l'esito e lo restituisce.

    Ogni cammino di uscita scrive una riga di manifest, compresi i fallimenti:
    e' cio' che rende calcolabile a posteriori la copertura della raccolta.
    L'esito torna al chiamante perche' e' il ciclo, non la singola
    interrogazione, a decidere se una serie di fallimenti costituisce
    un'interruzione da registrare in gaps.jsonl.
    """
    cartella_giorno = raccolta.cartella_rt / citta.nome / momento_locale.strftime("%Y-%m-%d")
    percorso_manifest = cartella_giorno / "_manifest.csv"

    riga: dict[str, Any] = {
        "istante_utc": momento_utc.isoformat(timespec="seconds"),
        "istante_locale": momento_locale.isoformat(timespec="seconds"),
        "tipo_feed": tipo_feed,
    }

    intestazioni = {"User-Agent": raccolta.user_agent, **citta.intestazioni_http}
    risultato = scarica(
        url,
        intestazioni,
        raccolta.timeout_richiesta_secondi,
        raccolta.tentativi_max,
        raccolta.backoff_base_secondi,
        raccolta.backoff_max_secondi,
    )
    riga["stato_http"] = risultato.stato_http if risultato.stato_http is not None else ""
    riga["tentativi"] = risultato.tentativi

    if not risultato.ok or risultato.dati is None:
        riga["esito"] = risultato.esito
        riga["dettaglio"] = risultato.dettaglio
        _registra((stato.contatori, stato.totali), risultato.esito, 0)
        scrivi_riga_manifest(percorso_manifest, riga)
        log.warning("[%s/%s] %s", citta.nome, tipo_feed, risultato.dettaglio)
        return risultato.esito

    dati = risultato.dati
    riga["byte"] = len(dati)

    try:
        riepilogo = analizza_feed(dati)
    except FeedNonValido as errore:
        # Il payload viene comunque conservato, in una cartella separata: se un
        # giorno il feed cambia formato vogliamo poter capire cosa e' arrivato,
        # non solo sapere che era illeggibile.
        cartella_scarti = cartella_giorno / "_scarti" / tipo_feed
        cartella_scarti.mkdir(parents=True, exist_ok=True)
        destinazione = cartella_scarti / f"{momento_locale.strftime('%H%M%S')}.bin"
        destinazione.write_bytes(dati)
        riga["esito"] = ESITO_NON_VALIDO
        riga["dettaglio"] = str(errore)
        riga["file"] = str(destinazione.relative_to(raccolta.cartella_rt))
        _registra((stato.contatori, stato.totali), ESITO_NON_VALIDO, 0)
        scrivi_riga_manifest(percorso_manifest, riga)
        log.warning("[%s/%s] payload non valido: %s", citta.nome, tipo_feed, errore)
        return ESITO_NON_VALIDO

    riga["timestamp_feed"] = riepilogo.timestamp_feed
    riga["n_entita"] = riepilogo.n_entita

    precedente = stato.ultimo_timestamp_feed.get(tipo_feed)
    if not deve_salvare(riepilogo.timestamp_feed, precedente):
        riga["esito"] = ESITO_DUPLICATO
        riga["dettaglio"] = "header.timestamp invariato"
        _registra((stato.contatori, stato.totali), ESITO_DUPLICATO, 0)
        scrivi_riga_manifest(percorso_manifest, riga)
        return ESITO_DUPLICATO

    destinazione = percorso_dump(raccolta.cartella_rt, citta.nome, tipo_feed, momento_locale)
    destinazione.parent.mkdir(parents=True, exist_ok=True)
    destinazione.write_bytes(dati)
    stato.ultimo_timestamp_feed[tipo_feed] = riepilogo.timestamp_feed
    riga["esito"] = ESITO_SALVATO
    riga["file"] = str(destinazione.relative_to(raccolta.cartella_rt))
    _registra((stato.contatori, stato.totali), ESITO_SALVATO, len(dati))
    scrivi_riga_manifest(percorso_manifest, riga)
    log.debug(
        "[%s/%s] salvato %s (%d entita', %d byte).",
        citta.nome,
        tipo_feed,
        destinazione.name,
        riepilogo.n_entita,
        len(dati),
    )
    return ESITO_SALVATO


def riga_riepilogo(nome: str, contatori: Contatori, etichetta: str) -> str:
    """Riga di riepilogo periodico: e' il modo per accorgersi che qualcosa non va."""
    errori = contatori.errori_rete + contatori.errori_http + contatori.non_validi
    return (
        f"[{nome}] {etichetta}: {contatori.salvati} salvati, "
        f"{contatori.duplicati} duplicati, {errori} errori "
        f"(rete {contatori.errori_rete}, http {contatori.errori_http}, "
        f"non validi {contatori.non_validi}), "
        f"{contatori.byte / 1_048_576:.1f} MB, copertura {contatori.copertura:.1%}"
    )


class _Interruttore:
    """Traduce i segnali di terminazione in una richiesta di uscita ordinata.

    Una terminazione brutale a meta' scrittura lascerebbe un file .pb troncato
    che in Fase 3 verrebbe scambiato per un feed corrotto. Intercettando il
    segnale usciamo fra un tick e l'altro, quando su disco non c'e' nulla a
    meta'.
    """

    def __init__(self) -> None:
        self.uscita_richiesta = False
        for segnale in (signal.SIGINT, signal.SIGTERM):
            try:
                signal.signal(segnale, self._gestisci)
            except (ValueError, OSError, AttributeError):
                # Alcuni segnali non sono disponibili su Windows o fuori dal
                # thread principale: non e' un motivo per non partire.
                pass

    def _gestisci(self, *_: Any) -> None:
        if self.uscita_richiesta:
            raise KeyboardInterrupt("secondo segnale ricevuto: uscita immediata")
        self.uscita_richiesta = True
        log.info("Segnale di terminazione ricevuto: esco al termine di questo giro.")


def esegui(
    config: Configurazione,
    solo_citta: Sequence[str] | None = None,
    cicli_max: int | None = None,
    dormi: Callable[[float], None] = time.sleep,
) -> int:
    """Ciclo principale di raccolta. Restituisce il codice di uscita del processo."""
    attive = [c for c in config.citta if c.attiva]
    if solo_citta:
        richieste = {n.strip() for n in solo_citta}
        sconosciute = richieste - {c.nome for c in config.citta}
        if sconosciute:
            log.error("Citta' non presenti in configurazione: %s", ", ".join(sorted(sconosciute)))
            return 2
        attive = [c for c in attive if c.nome in richieste]
    if not attive:
        log.error("Nessuna citta' attiva da raccogliere.")
        return 2

    raccolta = config.raccolta
    stati = {c.nome: StatoCitta() for c in attive}
    interruttore = _Interruttore()
    avvio_utc = datetime.now(timezone.utc)

    log.info(
        "Avvio della raccolta: %s | intervallo %d s.",
        "; ".join(f"{c.nome} [{', '.join(sorted(c.feed_rt))}]" for c in attive),
        raccolta.intervallo_polling_secondi,
    )

    for citta in attive:
        if citta.indirizzi_in_chiaro:
            log.warning(
                "[%s] %d indirizzi serviti in HTTP e non in HTTPS: %s. "
                "Il traffico e' leggibile e alterabile lungo il percorso; "
                "nessuna credenziale viene inviata su questi indirizzi.",
                citta.nome,
                len(citta.indirizzi_in_chiaro),
                ", ".join(citta.indirizzi_in_chiaro),
            )
        if not citta.url_gtfs_statico:
            log.warning(
                "[%s] MANCA l'orario statico: i dump real-time vengono raccolti ma NON "
                "saranno interpretabili in Fase 3, perche' non si potra' risalire agli "
                "orari programmati. Compilare 'url_gtfs_statico' in config.yaml.",
                citta.nome,
            )

        # Un riavvio lascia una finestra scoperta fra l'ultima raccolta riuscita
        # del processo precedente e questo avvio: va registrata adesso, perche'
        # nessun altro momento ha entrambi gli estremi.
        percorso_battito = raccolta.cartella_rt / citta.nome / NOME_BATTITO
        ultimo = leggi_battito(percorso_battito)
        if ultimo is None:
            log.info("[%s] prima esecuzione: nessuna interruzione pregressa da registrare.", citta.nome)
        elif e_interruzione(ultimo, avvio_utc, raccolta.soglia_interruzione_secondi):
            scrivi_gap(
                raccolta.cartella_rt / citta.nome / NOME_GAPS,
                citta.nome,
                ultimo,
                avvio_utc,
                CAUSA_PROCESSO_FERMO,
                "finestra fra l'ultima raccolta riuscita e il riavvio del collector",
            )
            log.warning(
                "[%s] interruzione registrata: %s -> %s (%.0f minuti senza raccolta).",
                citta.nome,
                ultimo.isoformat(timespec="seconds"),
                avvio_utc.isoformat(timespec="seconds"),
                (avvio_utc - ultimo).total_seconds() / 60,
            )
            # La finestra pregressa e' gia' stata registrata: il riferimento per
            # le interruzioni successive riparte da adesso, altrimenti la
            # prossima verrebbe scritta sovrapposta a questa.
            ultimo = avvio_utc
        stati[citta.nome].ultimo_successo = ultimo if ultimo is not None else avvio_utc

    prossimo_tick = time.monotonic()
    ora_riepilogo = datetime.now(timezone.utc).hour
    ciclo = 0

    while not interruttore.uscita_richiesta:
        ciclo += 1
        momento_utc = datetime.now(timezone.utc)

        for citta in attive:
            fuso = risolvi_fuso(citta.fuso_orario)
            momento_locale = momento_utc.astimezone(fuso)
            stato = stati[citta.nome]
            try:
                forse_archivia_orario(
                    citta, raccolta, momento_locale.strftime("%Y-%m-%d"), momento_utc
                )
            except Exception:
                # L'archiviazione dell'orario e' importante ma non deve mai
                # impedire la raccolta del real-time, che e' l'unico dato
                # irripetibile.
                log.exception("[%s] errore imprevisto nell'archiviazione dell'orario.", citta.nome)

            esiti: list[str] = []
            for tipo_feed, url in sorted(citta.feed_rt.items()):
                try:
                    esiti.append(
                        raccogli_feed(
                            citta, tipo_feed, url, raccolta, stato, momento_utc, momento_locale
                        )
                    )
                except Exception:
                    # Ultima rete di sicurezza: nemmeno un bug nostro deve poter
                    # fermare una raccolta che deve durare settimane.
                    stato.contatori.errori_rete += 1
                    stato.totali.errori_rete += 1
                    esiti.append(ESITO_ERRORE_RETE)
                    log.exception("[%s/%s] errore imprevisto.", citta.nome, tipo_feed)

            _aggiorna_interruzioni(citta, raccolta, stato, esiti, momento_utc)

        ora_corrente = datetime.now(timezone.utc).hour
        if ora_corrente != ora_riepilogo:
            for citta in attive:
                stato = stati[citta.nome]
                log.info(riga_riepilogo(citta.nome, stato.contatori, "ultima ora"))
                stato.contatori.azzera()
            ora_riepilogo = ora_corrente

        if cicli_max is not None and ciclo >= cicli_max:
            break
        if interruttore.uscita_richiesta:
            break

        # Cadenza a tick fissi invece di "dormi 60 secondi dopo il lavoro": la
        # seconda forma accumulerebbe la durata di ogni scaricamento, facendo
        # scivolare l'istante di campionamento di parecchi minuti nell'arco di
        # una giornata.
        prossimo_tick += raccolta.intervallo_polling_secondi
        attesa = prossimo_tick - time.monotonic()
        if attesa < 0:
            saltati = int(-attesa // raccolta.intervallo_polling_secondi) + 1
            prossimo_tick += saltati * raccolta.intervallo_polling_secondi
            log.warning(
                "Giro piu' lento dell'intervallo di polling: salto %d tick per riallinearmi.",
                saltati,
            )
        else:
            dormi(attesa)

    for citta in attive:
        log.info(riga_riepilogo(citta.nome, stati[citta.nome].totali, "totale di sessione"))
    log.info("Raccolta terminata dopo %d giri.", ciclo)
    return 0


# =============================================================================
# Diagnostica
# =============================================================================


def descrivi_feed(riepilogo: RiepilogoFeed, momento_utc: datetime) -> list[str]:
    """Traduce un riepilogo in un giudizio di utilizzabilita' per il progetto.

    Serve a rispondere prima di iniziare, e non dopo tre settimane, all'unica
    domanda che conta davvero su un feed: contiene i ritardi?
    """
    righe = [
        f"  versione GTFS-RT      : {riepilogo.versione}",
        f"  entita' totali        : {riepilogo.n_entita}",
        f"    trip_update         : {riepilogo.n_trip_update}",
        f"    vehicle_position    : {riepilogo.n_vehicle}",
        f"    alert               : {riepilogo.n_alert}",
    ]
    if riepilogo.timestamp_feed:
        istante = datetime.fromtimestamp(riepilogo.timestamp_feed, tz=timezone.utc)
        scarto = (momento_utc - istante).total_seconds()
        righe.append(
            f"  timestamp del feed    : {istante.isoformat(timespec='seconds')} "
            f"({scarto:.0f} s fa)"
        )
        if abs(scarto) > 600:
            righe.append(
                "    ATTENZIONE: il feed e' vecchio di oltre 10 minuti. Puo' essere "
                "fermo, oppure pubblicare il timestamp in un fuso diverso da UTC."
            )
    else:
        righe.append(
            "  timestamp del feed    : ASSENTE -> la deduplica non potra' funzionare "
            "e ogni interrogazione verra' salvata."
        )

    if riepilogo.n_trip_update:
        righe.append(f"  stop_time_update      : {riepilogo.n_stop_time_update}")
        righe.append(f"    con campo 'delay'   : {riepilogo.n_con_ritardo}")
        righe.append(f"    con orario assoluto : {riepilogo.n_con_orario_assoluto}")
        if riepilogo.relazioni_orario:
            dettaglio = ", ".join(f"{k}={v}" for k, v in sorted(riepilogo.relazioni_orario.items()))
            righe.append(f"    relazione con orario: {dettaglio}")

    righe.append("")
    if riepilogo.n_trip_update == 0:
        righe.append(
            "  GIUDIZIO: NON utilizzabile come fonte dei ritardi. "
            "Il feed non contiene TripUpdate."
        )
    elif riepilogo.n_con_ritardo == 0 and riepilogo.n_con_orario_assoluto == 0:
        righe.append(
            "  GIUDIZIO: NON utilizzabile. Ci sono TripUpdate ma nessuno porta "
            "ne' un ritardo ne' un orario osservato: non c'e' nulla da misurare."
        )
    else:
        base = (
            "dall'orario assoluto" if riepilogo.n_con_orario_assoluto else "dal campo delay"
        )
        quanti = max(riepilogo.n_con_ritardo, riepilogo.n_con_orario_assoluto)
        righe.append(
            f"  GIUDIZIO: utilizzabile. I ritardi sono ricavabili {base} "
            f"su {quanti} passaggi."
        )
    return righe


def diagnostica(url: str, intestazioni: dict[str, str], timeout: float) -> int:
    """Scarica una volta sola un indirizzo e ne stampa il contenuto reale."""
    print(f"\nInterrogo: {url}")
    risultato = scarica(
        url, intestazioni, timeout, tentativi_max=2, backoff_base=1.0, backoff_max=4.0
    )
    if not risultato.ok or risultato.dati is None:
        print(f"  FALLITO ({risultato.esito}): {risultato.dettaglio}")
        return 1
    print(f"  HTTP {risultato.stato_http}, {len(risultato.dati)} byte scaricati")
    try:
        riepilogo = analizza_feed(risultato.dati)
    except FeedNonValido as errore:
        anteprima = risultato.dati[:120].decode("utf-8", errors="replace").replace("\n", " ")
        print(f"  NON e' un feed GTFS Real-Time valido: {errore}")
        print(f"  primi byte: {anteprima!r}")
        return 1
    for riga in descrivi_feed(riepilogo, datetime.now(timezone.utc)):
        print(riga)
    return 0


# =============================================================================
# Avvio
# =============================================================================


def configura_log(cartella: Path, verboso: bool) -> None:
    """Log su console e su file ruotato.

    La rotazione non e' pedanteria: a settimane di esecuzione un file unico
    crescerebbe senza limite, e il log e' anche il posto dove si va a capire
    perche' un certo giorno la copertura e' crollata.
    """
    cartella.mkdir(parents=True, exist_ok=True)
    log.setLevel(logging.DEBUG if verboso else logging.INFO)
    log.handlers.clear()

    formato = logging.Formatter(
        "%(asctime)s %(levelname)-7s %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )

    # Sotto pythonw.exe (l'interprete senza finestra, quello che si usa per far
    # girare la raccolta in background su Windows) lo standard output non esiste:
    # aggiungere comunque il gestore su console farebbe fallire ogni scrittura di
    # log. In quel caso resta il solo file, che e' esattamente cio' che serve.
    if sys.stdout is not None:
        consolle = logging.StreamHandler(stream=sys.stdout)
        consolle.setLevel(logging.DEBUG if verboso else logging.INFO)
        consolle.setFormatter(formato)
        log.addHandler(consolle)

    su_file = logging.handlers.RotatingFileHandler(
        cartella / "collector.log", maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    su_file.setLevel(logging.DEBUG)
    su_file.setFormatter(formato)
    log.addHandler(su_file)


def _argomenti(argv: Sequence[str] | None = None) -> argparse.Namespace:
    analizzatore = argparse.ArgumentParser(
        prog="python -m src.collector.poll_realtime",
        description="Raccoglie in continuo i feed GTFS Real-Time configurati in config.yaml.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Esempi:\n"
            "  python -m src.collector.poll_realtime --verifica-config\n"
            "  python -m src.collector.poll_realtime --diagnostica https://.../tripupdates\n"
            "  python -m src.collector.poll_realtime --diagnostica-citta citta_a\n"
            "  python -m src.collector.poll_realtime\n"
        ),
    )
    analizzatore.add_argument(
        "--config", type=Path, default=Path("config.yaml"), help="percorso di config.yaml"
    )
    analizzatore.add_argument(
        "--citta",
        action="append",
        metavar="NOME",
        help="raccogli solo questa citta' (ripetibile)",
    )
    analizzatore.add_argument(
        "--cicli", type=int, metavar="N", help="esegui solo N giri e termina (utile per una prova)"
    )
    analizzatore.add_argument("--una-volta", action="store_true", help="equivale a --cicli 1")
    analizzatore.add_argument(
        "--verifica-config",
        action="store_true",
        help="valida config.yaml e termina, senza toccare la rete",
    )
    analizzatore.add_argument(
        "--diagnostica",
        metavar="URL",
        help="scarica un indirizzo una volta sola e dice cosa contiene",
    )
    analizzatore.add_argument(
        "--diagnostica-citta",
        metavar="NOME",
        help="esegue la diagnostica su tutti i feed configurati per una citta'",
    )
    analizzatore.add_argument("--verboso", action="store_true", help="log di livello DEBUG")
    return analizzatore.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    argomenti = _argomenti(argv)

    # La diagnostica su un indirizzo libero deve funzionare anche prima che
    # config.yaml sia compilato: e' esattamente lo strumento che serve per
    # decidere se un feed vale la pena di essere messo in configurazione.
    if argomenti.diagnostica and not argomenti.diagnostica_citta:
        configura_log(Path("logs"), argomenti.verboso)
        return diagnostica(
            argomenti.diagnostica,
            {"User-Agent": "progetto-icon-tpl/0.1 (diagnostica)"},
            timeout=30.0,
        )

    try:
        config = carica_configurazione(argomenti.config)
    except ErroreConfigurazione as errore:
        print(f"\n{errore}\n", file=sys.stderr)
        return 2

    configura_log(config.raccolta.cartella_log, argomenti.verboso)

    if argomenti.verifica_config:
        print("Configurazione valida.")
        for citta in config.citta:
            stato = "attiva" if citta.attiva else "disattivata"
            feed = ", ".join(sorted(citta.feed_rt)) or "nessun feed"
            print(f"  - {citta.nome} ({stato}, {citta.fuso_orario}): {feed}")
            if citta.url_gtfs_statico:
                con_md5 = " con .md5" if citta.url_gtfs_statico_md5 else " senza .md5 (si scarica l'archivio ogni giorno)"
                print(f"      orario statico:{con_md5}")
            else:
                print(
                    "      ATTENZIONE: manca l'orario statico. I dump real-time verranno "
                    "raccolti\n"
                    "      ma NON saranno interpretabili in Fase 3, perche' non si potra' "
                    "risalire\n"
                    "      agli orari programmati."
                )
            if citta.indirizzi_in_chiaro:
                print(
                    f"      ATTENZIONE: {len(citta.indirizzi_in_chiaro)} indirizzi in HTTP "
                    "(non cifrati):"
                )
                for indirizzo in citta.indirizzi_in_chiaro:
                    print(f"        {indirizzo}")
        return 0

    if argomenti.diagnostica_citta:
        scelte = [c for c in config.citta if c.nome == argomenti.diagnostica_citta]
        if not scelte:
            print(
                f"Citta' '{argomenti.diagnostica_citta}' non presente in configurazione.",
                file=sys.stderr,
            )
            return 2
        citta = scelte[0]
        intestazioni = {"User-Agent": config.raccolta.user_agent, **citta.intestazioni_http}
        esiti = [
            diagnostica(url, intestazioni, config.raccolta.timeout_richiesta_secondi)
            for _, url in sorted(citta.feed_rt.items())
        ]
        return 0 if esiti and all(e == 0 for e in esiti) else 1

    cicli = 1 if argomenti.una_volta else argomenti.cicli
    try:
        return esegui(config, solo_citta=argomenti.citta, cicli_max=cicli)
    except KeyboardInterrupt:
        log.info("Interrotto da tastiera.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
