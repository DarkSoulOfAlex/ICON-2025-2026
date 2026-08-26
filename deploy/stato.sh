#!/usr/bin/env bash
#
# Fotografia dello stato della raccolta.
#
# Da eseguire SULLA VM:
#     ./deploy/stato.sh
#
# Oppure dal PC, senza collegarsi a mano:
#     ssh vm-icon '~/icon/deploy/stato.sh'
#
# La copertura riportata qui e' quella VERA: tiene conto sia delle
# interrogazioni fallite sia delle finestre in cui il collector non girava
# affatto. La percentuale che si legge nei soli manifest e' un'altra cosa e
# inganna, perche' misura solo i tentativi effettuati: sul PC diceva 100% mentre
# la copertura reale era del 7,2%.

set -euo pipefail

RADICE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${RADICE}"

NOME_SERVIZIO="collector-tpl"
PYTHON="${RADICE}/.venv/bin/python"

titolo() { printf '\n\033[1m== %s\033[0m\n' "$*"; }

# =============================================================================
titolo "Servizio"
# =============================================================================

if command -v systemctl >/dev/null 2>&1 && systemctl list-unit-files "${NOME_SERVIZIO}.service" >/dev/null 2>&1; then
    STATO="$(systemctl is-active "${NOME_SERVIZIO}" 2>/dev/null || true)"
    ABILITATO="$(systemctl is-enabled "${NOME_SERVIZIO}" 2>/dev/null || true)"
    printf '  %-22s %s\n' "stato:" "${STATO}"
    printf '  %-22s %s\n' "avvio automatico:" "${ABILITATO}"
    DA_QUANDO="$(systemctl show -p ActiveEnterTimestamp --value "${NOME_SERVIZIO}" 2>/dev/null || true)"
    [[ -n "${DA_QUANDO}" ]] && printf '  %-22s %s\n' "attivo da:" "${DA_QUANDO}"
    if [[ "${STATO}" != "active" ]]; then
        echo
        echo "  Il servizio NON sta raccogliendo. Ultime righe del log:"
        journalctl -u "${NOME_SERVIZIO}" -n 8 --no-pager 2>/dev/null | sed 's/^/    /' || true
    fi
else
    echo "  unit ${NOME_SERVIZIO} non installata su questa macchina"
fi

# =============================================================================
titolo "Disco"
# =============================================================================

df -h . | awk 'NR==1 {printf "  %s\n", $0} NR==2 {printf "  %s\n", $0}'
printf '  %-22s %s\n' "occupato da data/:" "$(du -sh data 2>/dev/null | cut -f1 || echo '-')"

# =============================================================================
# Il resto e' aritmetica sui manifest e su gaps.jsonl: si appoggia al Python
# dell'ambiente virtuale, cosi' i numeri sono calcolati esattamente come li
# calcola il resto del progetto invece di essere riprodotti in awk.
# =============================================================================

if [[ ! -x "${PYTHON}" ]]; then
    echo
    echo "  Ambiente virtuale assente in ${RADICE}/.venv: eseguire prima ./deploy/install.sh"
    exit 1
fi

"${PYTHON}" - <<'PYTHON'
import csv
import json
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

RT = Path("data/raw/rt")
GIORNI_STORICO = 7


def citta_note() -> list[str]:
    return sorted(p.name for p in RT.iterdir() if p.is_dir()) if RT.is_dir() else []


def esiti(percorso: Path) -> Counter:
    conteggi: Counter = Counter()
    if not percorso.is_file():
        return conteggi
    with percorso.open(encoding="utf-8", newline="") as flusso:
        for riga in csv.DictReader(flusso):
            conteggi[riga.get("esito", "?")] += 1
    return conteggi


def finestre(citta: str) -> list[dict]:
    percorso = RT / citta / "gaps.jsonl"
    if not percorso.is_file():
        return []
    righe = []
    for testo in percorso.read_text(encoding="utf-8").splitlines():
        if testo.strip():
            try:
                righe.append(json.loads(testo))
            except json.JSONDecodeError:
                continue
    return righe


def battito(citta: str) -> datetime | None:
    percorso = RT / citta / "_battito.json"
    if not percorso.is_file():
        return None
    try:
        return datetime.fromisoformat(json.loads(percorso.read_text(encoding="utf-8"))["ultimo_successo"])
    except (json.JSONDecodeError, KeyError, ValueError, OSError):
        return None


elenco = citta_note()
if not elenco:
    print("\n  Nessun dato raccolto ancora.")
    raise SystemExit(0)

oggi = date.today()
adesso = datetime.now(timezone.utc)

print("\n\033[1m== Dump di oggi\033[0m")
for citta in elenco:
    cartella = RT / citta / oggi.isoformat()
    dump = len(list(cartella.rglob("*.pb"))) if cartella.is_dir() else 0
    archivi = len(list(cartella.glob("grezzi.tar.gz"))) if cartella.is_dir() else 0
    ultimo = battito(citta)
    eta = f"{(adesso - ultimo).total_seconds() / 60:.0f} min fa" if ultimo else "mai"
    print(f"  {citta:<10} {dump:>6} dump  |  ultima raccolta riuscita: {eta}"
          + ("  |  grezzi gia' archiviati" if archivi else ""))

print("\n\033[1m== Copertura\033[0m")
print("  La colonna 'reale' toglie dalle ore di calendario quelle coperte da")
print("  finestre di interruzione: e' il numero da dichiarare nella documentazione.")
print(f"  {'citta':<10} {'giorno':<12} {'interrog.':>10} {'riuscite':>9} {'manifest':>9} {'reale':>8}")

for citta in elenco:
    aperte = finestre(citta)
    for scarto in range(GIORNI_STORICO, -1, -1):
        giorno = oggi - timedelta(days=scarto)
        percorso = RT / citta / giorno.isoformat() / "_manifest.csv"
        if not percorso.is_file():
            continue
        conteggi = esiti(percorso)
        totale = sum(conteggi.values())
        riuscite = conteggi.get("salvato", 0) + conteggi.get("duplicato", 0)
        # Ogni giro interroga tutti i feed configurati: il numero di giri e' il
        # totale diviso per i feed distinti visti nel manifest.
        with percorso.open(encoding="utf-8", newline="") as flusso:
            feed = {r.get("tipo_feed", "?") for r in csv.DictReader(flusso)}
        giri = riuscite / max(1, len(feed))

        inizio = datetime.combine(giorno, datetime.min.time(), tzinfo=timezone.utc)
        fine = min(inizio + timedelta(days=1), adesso)
        minuti_calendario = max(1.0, (fine - inizio).total_seconds() / 60)
        quota_manifest = riuscite / totale if totale else 0.0
        quota_reale = min(1.0, giri / minuti_calendario)
        print(f"  {citta:<10} {giorno.isoformat():<12} {totale:>10,} {riuscite:>9,} "
              f"{quota_manifest:>8.1%} {quota_reale:>8.1%}")

    ore_perse = sum(f.get("durata_secondi", 0) for f in aperte) / 3600
    if aperte:
        print(f"  {citta:<10} interruzioni registrate: {len(aperte)}, per {ore_perse:.1f} ore complessive")
        for f in aperte[-3:]:
            print(f"      {f.get('inizio', '?')} -> {f.get('fine', '?')}  "
                  f"({f.get('durata_secondi', 0) / 60:.0f} min, {f.get('causa', '?')})")
    else:
        print(f"  {citta:<10} nessuna interruzione registrata")

print("\n\033[1m== Orario statico\033[0m")
for citta in elenco:
    percorso = Path("data/raw/gtfs") / citta / "index.json"
    if not percorso.is_file():
        print(f"  {citta:<10} nessun index.json")
        continue
    indice = json.loads(percorso.read_text(encoding="utf-8"))
    giorni = indice.get("giorni", {})
    versioni = indice.get("versioni", {})
    ultimo = max(giorni) if giorni else "-"
    print(f"  {citta:<10} {len(versioni)} revisioni distinte, {len(giorni)} giorni mappati, "
          f"ultimo controllo {ultimo}")

print("\n\033[1m== Osservazioni consolidate\033[0m")
consolidate = sorted(Path("data/processed/osservazioni").rglob("*.parquet")) if Path("data/processed/osservazioni").is_dir() else []
if not consolidate:
    print("  nessun giorno consolidato (il timer notturno gira alle 04:00)")
else:
    peso = sum(p.stat().st_size for p in consolidate) / 1_048_576
    print(f"  {len(consolidate)} giorni consolidati, {peso:.0f} MB complessivi")
    print(f"  piu' recente: {consolidate[-1].parent.name}/{consolidate[-1].name}")
PYTHON
