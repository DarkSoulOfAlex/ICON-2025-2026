"""Test della base di conoscenza.

Collaudano le quattro proprieta' che rendono ``rules.lp`` una base di conoscenza
e non un'interrogazione: l'eredita' difettibile, la non-monotonia, la ricorsione
e i vincoli che rifiutano il modello. Piu' la proprieta' su cui si regge
l'indice spaziale, cioe' che non cambi il risultato.

Tutto gira sul GTFS giocattolo, i cui trasbordi si verificano a mano: cinque
fermate, due delle quali banchine della stessa stazione, una terza a settanta
metri e due lontane chilometri.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.gtfs.loader import carica_archivio
from src.kb.engine import esegui, fermata_centrale, genera_fatti, sottoinsieme_per_prossimita
from tests.test_gtfs import GIOCATTOLO, scrivi_giocattolo

# transfers.txt non esiste in nessuna delle due citta' del progetto, ma la regola
# di livello 1 va collaudata lo stesso: e' quella che rende la gerarchia dei
# tempi una eredita' difettibile invece di due casi indipendenti.
TRANSFERS = "from_stop_id,to_stop_id,transfer_type,min_transfer_time\n"


def _archivio(cartella: Path, **modifiche: str):
    percorso = scrivi_giocattolo(cartella, modifiche=modifiche or None)
    return carica_archivio(percorso, con_stop_times=True)


def _trasbordi(risultato) -> dict[tuple[str, str], int]:
    if risultato.trasbordi.empty:
        return {}
    return {
        (r.from_stop_id, r.to_stop_id): r.min_transfer_time
        for r in risultato.trasbordi.itertuples(index=False)
    }


# =============================================================================
# Derivazione di base, verificabile a mano
# =============================================================================


def test_i_trasbordi_derivati_sono_quelli_attesi(tmp_path: Path) -> None:
    """A1, A2 e B sono a poche decine di metri; C e D sono a chilometri."""
    risultato = esegui(genera_fatti(_archivio(tmp_path)))
    assert risultato.soddisfacibile
    coppie = set(_trasbordi(risultato))
    assert coppie == {
        ("A1", "A2"), ("A2", "A1"),
        ("A1", "B"), ("B", "A1"),
        ("A2", "B"), ("B", "A2"),
    }
    # C e D non compaiono in nessun trasbordo: sono troppo lontane.
    assert not any("C" in c or "D" in c for c in coppie)


def test_il_tempo_dipende_dalla_fermata_non_e_una_costante(tmp_path: Path) -> None:
    """E' il requisito 'tempo minimo dipendente dalla fermata'."""
    risultato = esegui(genera_fatti(_archivio(tmp_path)))
    tempi = _trasbordi(risultato)
    # A1 e A2 sono banchine della stessa stazione: vale la regola di stazione.
    assert tempi[("A1", "A2")] == 180
    # A1-B e' un cammino all'aperto di ~73 m: banda dei 100 m (120 s) piu' il
    # margine di 60 s.
    assert tempi[("A1", "B")] == 180


# =============================================================================
# Eredita' difettibile: la gerarchia dei tempi
# =============================================================================


def test_il_dato_dichiarato_batte_la_regola_di_stazione(tmp_path: Path) -> None:
    """Livello 1 della gerarchia: cio' che dichiara l'azienda vince su tutto."""
    dichiarato = TRANSFERS + "A1,A2,2,600\n"
    risultato = esegui(genera_fatti(_archivio(tmp_path, **{"transfers.txt": dichiarato})))
    tempi = _trasbordi(risultato)
    assert tempi[("A1", "A2")] == 600, "il valore dichiarato deve sovrascrivere i 180 s di stazione"
    # La sovrascrittura e' puntuale: l'altra direzione, non dichiarata, resta
    # governata dalla regola di stazione. E' precisamente cio' che distingue
    # un'eredita' difettibile da un valore memorizzato.
    assert tempi[("A2", "A1")] == 180


def test_la_regola_di_stazione_batte_quella_del_cammino(tmp_path: Path) -> None:
    """Livello 2: A1 e A2 distano 14 m, quindi a piedi sarebbero 60+60=120 s."""
    risultato = esegui(genera_fatti(_archivio(tmp_path)))
    assert _trasbordi(risultato)[("A1", "A2")] == 180


def test_senza_dichiarazioni_ne_stazione_vale_il_cammino(tmp_path: Path) -> None:
    """Livello 3: B non appartiene a nessuna stazione."""
    risultato = esegui(genera_fatti(_archivio(tmp_path)))
    assert _trasbordi(risultato)[("B", "A1")] == 180


# =============================================================================
# Non-monotonia
# =============================================================================


def test_aggiungere_un_fatto_toglie_conclusioni(tmp_path: Path) -> None:
    """La proprieta' che nessuna interrogazione relazionale possiede.

    In algebra relazionale aggiungere tuple non puo' mai ridurre il risultato di
    una query positiva. Qui dichiarare un ascensore fuori servizio rimuove
    trasbordi che erano stati derivati come accessibili.
    """
    archivio = _archivio(tmp_path)

    prima = esegui(genera_fatti(archivio))
    dopo = esegui(genera_fatti(archivio, ascensori_fuori_servizio=["A1"]))

    def accessibili(risultato) -> set[tuple[str, str]]:
        tabella = risultato.trasbordi
        return {
            (r.from_stop_id, r.to_stop_id)
            for r in tabella[tabella["accessibile"]].itertuples(index=False)
        }

    rimosse = accessibili(prima) - accessibili(dopo)
    assert rimosse == {("A1", "A2"), ("A1", "B"), ("A2", "A1"), ("B", "A1")}
    assert accessibili(dopo) - accessibili(prima) == set(), "nessuna conclusione nuova"

    # I trasbordi restano: e' solo la loro accessibilita' a cadere.
    assert set(_trasbordi(prima)) == set(_trasbordi(dopo))


def test_una_fermata_non_accessibile_non_genera_trasbordi_accessibili(tmp_path: Path) -> None:
    """C ha wheelchair_boarding = 2, ma e' lontana: si verifica sulla regola."""
    vicina = GIOCATTOLO["stops.txt"].replace(
        "C,Via Lontana,45.090000,7.720000,0,,2",
        "C,Via Vicina,45.070600,7.680700,0,,2",
    )
    risultato = esegui(genera_fatti(_archivio(tmp_path, **{"stops.txt": vicina})))
    tabella = risultato.trasbordi
    con_c = tabella[(tabella["from_stop_id"] == "C") | (tabella["to_stop_id"] == "C")]
    assert not con_c.empty, "C ora e' vicina, quindi i trasbordi devono esistere"
    assert not con_c["accessibile"].any()


# =============================================================================
# Ricorsione: chiusura transitiva
# =============================================================================


def test_la_raggiungibilita_e_la_chiusura_transitiva(tmp_path: Path) -> None:
    """Nessun trasbordo diretto C-D, e nessuna catena che li colleghi."""
    risultato = esegui(genera_fatti(_archivio(tmp_path)), mostra_raggiungibile=True)
    raggiungibili = risultato.raggiungibili

    # Il blocco connesso e' chiuso: tutte le coppie fra A1, A2 e B.
    for partenza in ("A1", "A2", "B"):
        for arrivo in ("A1", "A2", "B"):
            assert (partenza, arrivo) in raggiungibili, (partenza, arrivo)

    # Riflessiva anche sulle fermate isolate.
    assert ("C", "C") in raggiungibili
    assert ("D", "D") in raggiungibili
    # Ma nessun ponte verso di loro.
    assert ("A1", "C") not in raggiungibili
    assert ("C", "D") not in raggiungibili


def test_la_chiusura_attraversa_piu_di_un_salto(tmp_path: Path) -> None:
    """Una catena a tre anelli senza scorciatoie: se il collegamento A1-E esiste,
    puo' venire solo dalla ricorsione applicata due volte.

    Le fermate sono disposte in fila a 200 m l'una dall'altra: ciascuna raggiunge
    solo la successiva e la precedente, mai la terza, perche' la soglia e' 250 m.
    """
    fila = (
        "stop_id,stop_name,stop_lat,stop_lon,location_type,parent_station,wheelchair_boarding\n"
        "P1,Uno,45.070000,7.680000,0,,1\n"
        "P2,Due,45.071800,7.680000,0,,1\n"
        "P3,Tre,45.073600,7.680000,0,,1\n"
        "P4,Quattro,45.075400,7.680000,0,,1\n"
    )
    orari = (
        "trip_id,stop_id,stop_sequence,arrival_time,departure_time\n"
        "T1,P1,1,08:00:00,08:00:00\n"
        "T1,P4,2,08:20:00,08:20:00\n"
    )
    corse = "route_id,service_id,trip_id,direction_id,wheelchair_accessible\nL1,FERIALE,T1,0,1\n"
    risultato = esegui(
        genera_fatti(_archivio(tmp_path, **{"stops.txt": fila, "stop_times.txt": orari, "trips.txt": corse})),
        mostra_raggiungibile=True,
    )
    diretti = set(_trasbordi(risultato))
    assert ("P1", "P3") not in diretti, "P1 e P3 distano 400 m: nessun trasbordo diretto"
    assert ("P1", "P4") not in diretti
    # Ma la chiusura transitiva li collega comunque.
    assert ("P1", "P3") in risultato.raggiungibili
    assert ("P1", "P4") in risultato.raggiungibili


# =============================================================================
# Vincoli di integrita': devono poter scattare davvero
# =============================================================================


def test_un_tempo_dichiarato_piu_breve_del_cammino_rifiuta_il_modello(tmp_path: Path) -> None:
    """V2. Trenta secondi per un tratto che a piedi ne richiede sessanta."""
    dichiarato = TRANSFERS + "A1,B,2,30\n"
    fatti = genera_fatti(_archivio(tmp_path, **{"transfers.txt": dichiarato}))
    assert not esegui(fatti).soddisfacibile
    # Disattivando i vincoli il modello esiste: e' la prova che a rifiutarlo e'
    # stato il vincolo e non un errore nelle regole.
    assert esegui(fatti, con_vincoli=False).soddisfacibile


def test_un_tempo_di_trasbordo_nullo_rifiuta_il_modello(tmp_path: Path) -> None:
    """V4. Diverse aziende pubblicano 0 per dire 'coincidenza garantita'."""
    dichiarato = TRANSFERS + "A1,A2,2,0\n"
    fatti = genera_fatti(_archivio(tmp_path, **{"transfers.txt": dichiarato}))
    assert not esegui(fatti).soddisfacibile
    assert esegui(fatti, con_vincoli=False).soddisfacibile


def test_una_banchina_accessibile_in_una_stazione_inaccessibile_rifiuta_il_modello(
    tmp_path: Path,
) -> None:
    """V3. Incoerenza reale: i due campi li compilano persone diverse."""
    incoerente = GIOCATTOLO["stops.txt"].replace(
        "STAZ,Stazione Centrale,45.070000,7.680000,1,,1",
        "STAZ,Stazione Centrale,45.070000,7.680000,1,,2",
    )
    fatti = genera_fatti(_archivio(tmp_path, **{"stops.txt": incoerente}))
    assert not esegui(fatti).soddisfacibile
    assert esegui(fatti, con_vincoli=False).soddisfacibile


def test_un_grado_implausibile_rifiuta_il_modello(tmp_path: Path) -> None:
    """V1. Le fermate senza coordinate finiscono tutte nello stesso punto."""
    righe = ["stop_id,stop_name,stop_lat,stop_lon,location_type,parent_station,wheelchair_boarding"]
    # Cinquanta fermate sovrapposte: oltre la soglia di grado plausibile (40).
    righe += [f"Z{i},Senza coordinate {i},45.070000,7.680000,0,,1" for i in range(50)]
    ammassate = "\n".join(righe) + "\n"
    orari = (
        "trip_id,stop_id,stop_sequence,arrival_time,departure_time\n"
        "T1,Z0,1,08:00:00,08:00:00\n"
        "T1,Z1,2,08:10:00,08:10:00\n"
    )
    corse = "route_id,service_id,trip_id,direction_id,wheelchair_accessible\nL1,FERIALE,T1,0,1\n"
    fatti = genera_fatti(
        _archivio(tmp_path, **{"stops.txt": ammassate, "stop_times.txt": orari, "trips.txt": corse})
    )
    assert not esegui(fatti).soddisfacibile
    assert esegui(fatti, con_vincoli=False).soddisfacibile


# =============================================================================
# L'indice spaziale non cambia il risultato
# =============================================================================


def test_l_indice_spaziale_non_altera_i_trasbordi_derivati(tmp_path: Path) -> None:
    """E' l'affermazione che il documento fa: va verificata, non asserita.

    L'indice restringe il confronto alle celle adiacenti; poiche' il lato della
    cella e' pari alla soglia di cammino, nessuna coppia entro la soglia puo'
    sfuggirgli. Qui si controlla che l'insieme derivato sia identico.
    """
    fatti = genera_fatti(_archivio(tmp_path))
    con = esegui(fatti, con_indice=True)
    senza = esegui(fatti, con_indice=False)

    assert con.soddisfacibile and senza.soddisfacibile
    assert _trasbordi(con) == _trasbordi(senza)
    # L'indice deve pero' costare meno: e' la ragione per cui esiste.
    assert con.atomi < senza.atomi


# =============================================================================
# Campionamento per prossimita'
# =============================================================================


def test_il_centro_del_campionamento_deriva_dai_dati(tmp_path: Path) -> None:
    """Deve essere riproducibile e dichiarabile, non scelto a occhio."""
    archivio = _archivio(tmp_path)
    centro = fermata_centrale(archivio.stops)
    assert centro == fermata_centrale(archivio.stops), "deve essere deterministico"
    assert centro in set(archivio.stops["stop_id"])


def test_il_campione_per_prossimita_cresce_per_inclusione(tmp_path: Path) -> None:
    """Un campione piu' grande deve contenere quello piu' piccolo.

    Se non fosse cosi', i punti della curva di complessita' non sarebbero
    confrontabili fra loro: misurerebbero reti diverse, non la stessa rete a
    dimensioni diverse.
    """
    from src.gtfs.loader import fermate_fisiche

    fermate = fermate_fisiche(_archivio(tmp_path).stops)
    piccolo = set(sottoinsieme_per_prossimita(fermate, 2)["stop_id"])
    grande = set(sottoinsieme_per_prossimita(fermate, 4)["stop_id"])
    assert piccolo < grande
