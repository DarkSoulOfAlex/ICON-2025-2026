#!/usr/bin/env bash
#
# Installa la raccolta GTFS Real-Time su una VM Ubuntu.
#
# Da eseguire SULLA VM, dalla radice del repository clonato:
#     ./deploy/install.sh
#
# E' idempotente: rieseguirlo aggiorna le dipendenze e la unit systemd senza
# rompere nulla. Se il servizio era gia' in esecuzione lo riavvia; se non lo era,
# NON lo avvia, perche' i dati gia' raccolti vanno copiati prima (vedi
# README_DEPLOY.md). Avviare la raccolta prima della copia produrrebbe manifest
# e registro delle interruzioni incoerenti.

set -euo pipefail

NOME_SERVIZIO="collector-tpl"
UNIT_INSTALLATA="/etc/systemd/system/${NOME_SERVIZIO}.service"
PYTHON_MINIMO="3.11"

RADICE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# Il collector si esegue con 'python -m src.collector...', che richiede la radice
# del repository come cartella di lavoro: senza questo spostamento l'import
# fallirebbe a seconda di dove lo script e' stato lanciato.
cd "${RADICE}"
MODELLO_UNIT="${RADICE}/deploy/collector.service"
REQUISITI="${RADICE}/deploy/requirements-collector.txt"
VENV="${RADICE}/.venv"
UTENTE="$(id -un)"

rosso() { printf '\033[31m%s\033[0m\n' "$*" >&2; }
verde() { printf '\033[32m%s\033[0m\n' "$*"; }
titolo() { printf '\n\033[1m== %s\033[0m\n' "$*"; }

errore() {
    rosso "ERRORE: $*"
    exit 1
}

# I comandi che toccano systemd hanno bisogno dei privilegi di amministratore.
# Si usa sudo solo se non si e' gia' root, cosi' lo script funziona in entrambi i
# casi senza duplicare i rami.
if [[ "$(id -u)" -eq 0 ]]; then
    COME_ROOT=()
else
    command -v sudo >/dev/null 2>&1 || errore "servono i privilegi di amministratore, ma 'sudo' non e' disponibile."
    COME_ROOT=(sudo)
fi

# =============================================================================
titolo "Controlli preliminari"
# =============================================================================

[[ -f "${REQUISITI}" ]] || errore "non trovo ${REQUISITI}. Lo script va eseguito dal repository clonato."
[[ -f "${MODELLO_UNIT}" ]] || errore "non trovo ${MODELLO_UNIT}."
[[ -f "${RADICE}/config.yaml" ]] || errore "non trovo ${RADICE}/config.yaml."

command -v systemctl >/dev/null 2>&1 || errore "systemctl non disponibile: questa macchina non usa systemd."

if ! command -v python3 >/dev/null 2>&1; then
    errore "python3 non installato. Rimediare con:  sudo apt install -y python3 python3-venv"
fi

VERSIONE_PY="$(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
if ! python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)'; then
    errore "serve Python ${PYTHON_MINIMO} o superiore, trovato ${VERSIONE_PY}."
fi
echo "  python3 ${VERSIONE_PY} su $(uname -m)"

# Il modulo venv su Ubuntu sta in un pacchetto separato, e la sua assenza
# produce un errore poco chiaro al momento della creazione dell'ambiente.
if ! python3 -c 'import venv' >/dev/null 2>&1; then
    errore "il modulo venv non e' disponibile. Rimediare con:  sudo apt install -y python3-venv"
fi

# =============================================================================
titolo "Ambiente virtuale e dipendenze"
# =============================================================================

if [[ -d "${VENV}" ]]; then
    echo "  ambiente gia' presente in ${VENV}, lo riuso"
else
    echo "  creo ${VENV}"
    python3 -m venv "${VENV}"
fi

"${VENV}/bin/python" -m pip install --quiet --upgrade pip
echo "  installo le dipendenze (solo wheel precompilate)"
"${VENV}/bin/python" -m pip install --only-binary=:all: --requirement "${REQUISITI}"

# =============================================================================
titolo "Verifica funzionale"
# =============================================================================

# Non basta che pip abbia scritto i file: si controlla che i tre pezzi da cui
# dipende la raccolta funzionino davvero su questa architettura. Meglio
# accorgersene adesso che dal primo giro fallito fra un'ora.
"${VENV}/bin/python" - <<'PYTHON'
import sys

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import yaml  # noqa: F401
from google.transit import gtfs_realtime_pb2

messaggio = gtfs_realtime_pb2.FeedMessage()
messaggio.header.gtfs_realtime_version = "2.0"
messaggio.header.timestamp = 1_700_000_000
entita = messaggio.entity.add()
entita.id = "1"
entita.trip_update.trip.trip_id = "T1"
tappa = entita.trip_update.stop_time_update.add()
tappa.stop_id = "S1"
tappa.arrival.delay = 120

riletto = gtfs_realtime_pb2.FeedMessage()
riletto.ParseFromString(messaggio.SerializeToString())
assert riletto.entity[0].trip_update.stop_time_update[0].arrival.delay == 120

adesso = datetime.now(timezone.utc).astimezone(ZoneInfo("Europe/Rome"))
print(f"  protobuf ok, PyYAML ok, zoneinfo Europe/Rome ok ({adesso:%Y-%m-%d %H:%M %Z})")
print(f"  interprete: {sys.version.split()[0]}")
PYTHON

echo "  valido config.yaml"
"${VENV}/bin/python" -m src.collector.poll_realtime --verifica-config --config "${RADICE}/config.yaml"

# =============================================================================
titolo "Unit systemd"
# =============================================================================

# La unit viene generata dal modello sostituendo utente e percorso reali: il
# repository puo' essere clonato ovunque, e percorsi fissi dentro il file
# fallirebbero in un modo poco leggibile.
TEMPORANEA="$(mktemp)"
trap 'rm -f "${TEMPORANEA}"' EXIT
sed -e "s|@RADICE@|${RADICE}|g" -e "s|@UTENTE@|${UTENTE}|g" "${MODELLO_UNIT}" > "${TEMPORANEA}"

if [[ -f "${UNIT_INSTALLATA}" ]] && "${COME_ROOT[@]}" cmp -s "${TEMPORANEA}" "${UNIT_INSTALLATA}"; then
    echo "  unit gia' aggiornata, non la riscrivo"
else
    echo "  scrivo ${UNIT_INSTALLATA} (utente ${UTENTE}, radice ${RADICE})"
    "${COME_ROOT[@]}" install -m 0644 "${TEMPORANEA}" "${UNIT_INSTALLATA}"
fi

"${COME_ROOT[@]}" systemctl daemon-reload
"${COME_ROOT[@]}" systemctl enable "${NOME_SERVIZIO}" >/dev/null
echo "  servizio abilitato all'avvio della macchina"

# =============================================================================
titolo "Esito"
# =============================================================================

if "${COME_ROOT[@]}" systemctl is-active --quiet "${NOME_SERVIZIO}"; then
    echo "  il servizio era gia' attivo: lo riavvio per applicare gli aggiornamenti"
    "${COME_ROOT[@]}" systemctl restart "${NOME_SERVIZIO}"
    verde "Installazione aggiornata e servizio riavviato."
    echo "  controlla con:  systemctl status ${NOME_SERVIZIO}"
else
    verde "Installazione completata. Il servizio NON e' stato avviato."
    cat <<ISTRUZIONI

  Non e' un errore: i dump gia' raccolti sulla macchina di analisi vanno copiati
  PRIMA di avviare la raccolta qui, altrimenti manifest, index.json e gaps.jsonl
  risulterebbero incoerenti.

  Prossimi passi, nell'ordine (vedi deploy/README_DEPLOY.md):
    1. dal PC:   copia di data/raw verso questa VM
    2. qui:      sudo systemctl start ${NOME_SERVIZIO}
    3. qui:      journalctl -u ${NOME_SERVIZIO} -f

  Se non hai dati da copiare, puoi avviare subito con il passo 2.
ISTRUZIONI
fi
