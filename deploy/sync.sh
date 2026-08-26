#!/usr/bin/env bash
#
# Scarica dalla VM cio' che NON e' rigenerabile.
#
# Da eseguire SUL PC di analisi, da Git Bash, nella radice del repository:
#     ./deploy/sync.sh              # solo il non rigenerabile (pochi MB)
#     ./deploy/sync.sh --grezzi     # anche i dump .pb e i loro archivi
#
# Che cosa scarica di norma: archivi statici GTFS e index.json, i manifest
# giornalieri, i registri delle interruzioni, i battiti, i parquet consolidati e
# results/. Sono i dati che, se persi, non si possono ricostruire in alcun modo.
# I dump grezzi restano sulla VM, dove c'e' spazio, e si scaricano solo con
# --grezzi.
#
# rsync non e' necessario. Git Bash non lo include, quindi lo script lo usa se lo
# trova nel PATH e altrimenti ripiega su tar attraverso ssh, che ci sono sempre.
# L'incrementalita' resta comunque garantita: il payload leggero pesa pochi MB e
# si trasferisce per intero in pochi secondi, mentre i grezzi, dopo il
# consolidamento notturno, sono archivi giornalieri IMMUTABILI, quindi basta
# scaricare quelli che non si hanno gia'.

set -euo pipefail

ALIAS="${VM_HOST:-vm-icon}"
REMOTO="${VM_PATH:-icon}"

RADICE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${RADICE}"

GREZZI=0
for argomento in "$@"; do
    case "${argomento}" in
        --grezzi) GREZZI=1 ;;
        -h | --help) sed -n '2,25p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) echo "Argomento non riconosciuto: ${argomento}" >&2; exit 2 ;;
    esac
done

rosso() { printf '\033[31m%s\033[0m\n' "$*" >&2; }
titolo() { printf '\n\033[1m== %s\033[0m\n' "$*"; }

# =============================================================================
# L'alias ssh deve essere configurato, altrimenti ci si connetterebbe al nulla
# =============================================================================

if ! ssh -G "${ALIAS}" 2>/dev/null | grep -qi "^hostname " ; then
    rosso "Non riesco a interrogare la configurazione ssh per '${ALIAS}'."
    exit 3
fi

OSPITE="$(ssh -G "${ALIAS}" 2>/dev/null | awk '/^hostname /{print $2; exit}')"
if [[ -z "${OSPITE}" || "${OSPITE}" == "${ALIAS}" ]]; then
    rosso "L'alias ssh '${ALIAS}' non e' configurato."
    cat <<ISTRUZIONI >&2

Aggiungi questo blocco in fondo a ~/.ssh/config, sostituendo l'indirizzo:

    Host ${ALIAS}
        HostName <IP_DELLA_VM>
        User ubuntu
        IdentityFile ~/.ssh/vm-icon.key
        IdentitiesOnly yes
        ServerAliveInterval 30

Poi verifica con:  ssh ${ALIAS} 'echo ok'
In alternativa, per una sola esecuzione:  VM_HOST=altro-alias ./deploy/sync.sh

ISTRUZIONI
    exit 3
fi

echo "VM: ${ALIAS} (${OSPITE}), repository remoto ~/${REMOTO}"

if ! ssh -o BatchMode=yes -o ConnectTimeout=15 "${ALIAS}" true 2>/dev/null; then
    rosso "Non riesco a connettermi a '${ALIAS}'. Controlla che la VM sia accesa,"
    rosso "che la porta 22 sia aperta nelle regole di rete e che la chiave sia quella giusta."
    exit 3
fi

# =============================================================================
# Elenco remoto dei file da portare a casa
# =============================================================================

# Il find gira sulla VM: e' l'unico posto che sa quali giorni esistano. I nomi
# arrivano uno per riga, relativi alla radice del repository remoto.
FILTRO_LEGGERO='\( -name "*.zip" -o -name "index.json" -o -name "_manifest.csv" -o -name "gaps.jsonl" -o -name "_battito.json" -o -name "*.parquet" \)'
FILTRO_GREZZI='\( -name "grezzi.tar.gz" -o -name "*.pb" -o -name "*.bin" \)'

titolo "Elenco dei file sulla VM"
LISTA_REMOTA="$(mktemp)"
trap 'rm -f "${LISTA_REMOTA}" "${LISTA_DA_PRENDERE:-}"' EXIT

COMANDO_FIND="cd ~/${REMOTO} && find data results -type f ${FILTRO_LEGGERO} 2>/dev/null | sort"
if [[ "${GREZZI}" -eq 1 ]]; then
    COMANDO_FIND="cd ~/${REMOTO} && find data results -type f \\( ${FILTRO_LEGGERO} -o ${FILTRO_GREZZI} \\) 2>/dev/null | sort"
fi
# shellcheck disable=SC2029  # la sostituzione deve avvenire qui, non sulla VM
ssh "${ALIAS}" "${COMANDO_FIND}" > "${LISTA_REMOTA}"
echo "  $(wc -l < "${LISTA_REMOTA}") file disponibili sulla VM"

# =============================================================================
# Trasferimento
# =============================================================================

if command -v rsync >/dev/null 2>&1; then
    titolo "Trasferimento con rsync"
    rsync -az --info=progress2 --files-from="${LISTA_REMOTA}" "${ALIAS}:${REMOTO}/" .
else
    titolo "Trasferimento con tar (rsync non disponibile in questo shell)"
    # Il payload leggero si prende per intero: pesa pochi MB, e distinguere il
    # gia'-presente costerebbe piu' del trasferimento stesso.
    LISTA_DA_PRENDERE="$(mktemp)"
    if [[ "${GREZZI}" -eq 1 ]]; then
        # I grezzi invece sono grandi e immutabili: si prendono solo i mancanti.
        # E' qui che nasce l'incrementalita' senza rsync.
        LOCALI="$(mktemp)"
        find data results -type f \( -name "grezzi.tar.gz" -o -name "*.pb" -o -name "*.bin" \) 2>/dev/null | sort > "${LOCALI}"
        grep -E '(grezzi\.tar\.gz|\.pb|\.bin)$' "${LISTA_REMOTA}" | sort | comm -23 - "${LOCALI}" > "${LISTA_DA_PRENDERE}"
        grep -vE '(grezzi\.tar\.gz|\.pb|\.bin)$' "${LISTA_REMOTA}" >> "${LISTA_DA_PRENDERE}"
        rm -f "${LOCALI}"
        echo "  $(wc -l < "${LISTA_DA_PRENDERE}") file da scaricare (i grezzi gia' presenti vengono saltati)"
    else
        cp "${LISTA_REMOTA}" "${LISTA_DA_PRENDERE}"
    fi

    if [[ ! -s "${LISTA_DA_PRENDERE}" ]]; then
        echo "  niente da scaricare: e' gia' tutto qui"
        exit 0
    fi

    # ssh inoltra il proprio stdin al comando remoto: la lista arriva a tar sulla
    # VM, e il flusso compresso torna indietro sullo stdout.
    # shellcheck disable=SC2029
    ssh "${ALIAS}" "cd ~/${REMOTO} && tar czf - --files-from=- --ignore-failed-read" \
        < "${LISTA_DA_PRENDERE}" | tar xzf - -C .
fi

# =============================================================================
titolo "Esito"
# =============================================================================

echo "  archivi statici : $(find data/raw/gtfs -name '*.zip' 2>/dev/null | wc -l)"
echo "  manifest        : $(find data/raw/rt -name '_manifest.csv' 2>/dev/null | wc -l)"
echo "  parquet          : $(find data/processed -name '*.parquet' 2>/dev/null | wc -l)"
if [[ "${GREZZI}" -eq 1 ]]; then
    echo "  archivi grezzi  : $(find data/raw/rt -name 'grezzi.tar.gz' 2>/dev/null | wc -l)"
    echo "  dump sciolti    : $(find data/raw/rt -name '*.pb' 2>/dev/null | wc -l)"
fi
echo "  occupazione     : $(du -sh data 2>/dev/null | cut -f1)"
