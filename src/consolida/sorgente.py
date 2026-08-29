"""I dump di una giornata, letti dalla cartella sciolta o dall'archivio compresso.

Il consolidamento notturno comprime i ``.pb`` del giorno in ``grezzi.tar.gz`` e
rimuove la forma sciolta, che occupa molto piu' spazio. La conseguenza e' che
qualunque elaborazione su un giorno **passato** non trova piu' la cartella: vale
per la diagnosi, e vale soprattutto per la rigenerazione dei parquet, che senza
questa lettura non potrebbe nemmeno partire.

Non si estrae nulla su disco. Un giorno di dump sciolti pesa oltre un gigabyte, e
la macchina di raccolta ha spazio contato: estrarre per rileggere significherebbe
raddoppiare l'occupazione proprio mentre si rigenera.

L'accesso all'archivio e' **sequenziale** di proposito. Su un ``.tar.gz`` non
esiste accesso casuale: leggere un membro a meta' costringe a decomprimere tutto
cio' che lo precede, e su un giorno intero il costo diventerebbe quadratico.
"""

from __future__ import annotations

import tarfile
from pathlib import Path
from typing import Iterable, Iterator

class ErroreSorgente(Exception):
    """I dump non sono leggibili nella forma attesa."""


NOME_ARCHIVIO = "grezzi.tar.gz"
SOTTOCARTELLA = "trip_updates"


class SorgenteDump:
    """I dump di ``trip_updates`` di una giornata, comunque siano conservati."""

    def __init__(self, cartella_giorno: Path, sottocartella: str = SOTTOCARTELLA) -> None:
        self.sottocartella = sottocartella
        self.cartella = cartella_giorno / sottocartella
        self.archivio = cartella_giorno / NOME_ARCHIVIO
        self._da_tar = not self.cartella.is_dir() and self.archivio.is_file()
        self._nomi: list[str] = []
        self._byte: dict[str, int] = {}

    @property
    def origine(self) -> str:
        if self.cartella.is_dir():
            return f"cartella {self.sottocartella}"
        if self._da_tar:
            return f"archivio {NOME_ARCHIVIO}"
        return "assente"

    @property
    def compressa(self) -> bool:
        return self._da_tar

    def disponibile(self) -> bool:
        return self.cartella.is_dir() or self._da_tar

    def nomi(self) -> list[str]:
        """Nomi dei dump, ordinati per orario, che nel nome e' ``HHMMSS``."""
        if self._nomi:
            return self._nomi
        if self.cartella.is_dir():
            trovati = sorted(p.name for p in self.cartella.glob("*.pb"))
            self._byte = {n: (self.cartella / n).stat().st_size for n in trovati}
            self._nomi = trovati
        elif self._da_tar:
            with tarfile.open(self.archivio, "r:gz") as tar:
                for membro in tar:
                    if self._e_nostro(membro.name) and membro.isfile():
                        self._byte[Path(membro.name).name] = membro.size
            self._nomi = sorted(self._byte)
        return self._nomi

    def byte_totali(self) -> int:
        """Dimensione complessiva dei dump, non compressi.

        E' la grandezza confrontabile fra le due forme di conservazione: quella
        dell'archivio direbbe quanto pesa il file, non quanti dati contiene.
        """
        self.nomi()
        return sum(self._byte.values())

    def _e_nostro(self, nome: str) -> bool:
        """Vero per i membri della sottocartella giusta.

        Il controllo sulla sottocartella non e' pignoleria: dentro l'archivio i
        ``vehicle_positions`` hanno gli **stessi nomi di file** dei
        ``trip_updates``, perche' vengono dallo stesso giro di raccolta, e senza
        questo filtro si leggerebbero gli uni per gli altri.
        """
        return nome.endswith(".pb") and f"{self.sottocartella}/" in nome.replace("\\", "/")

    def leggi(self, voluti: Iterable[str] | None = None) -> Iterator[tuple[str, bytes]]:
        """Contenuto dei dump richiesti, in ordine di nome; tutti se ``voluti`` e' assente."""
        insieme = set(voluti) if voluti is not None else set(self.nomi())
        if self.cartella.is_dir():
            for nome in sorted(insieme):
                percorso = self.cartella / nome
                if percorso.is_file():
                    yield nome, percorso.read_bytes()
            return
        if not self._da_tar:
            return
        # Si restituisce mentre si scorre, senza accumulare: un giorno intero di
        # dump sciolti supera il gigabyte, e tenerlo tutto in memoria per poi
        # riordinarlo sarebbe uno spreco evitabile. L'ordine dell'archivio e'
        # gia' quello dei nomi, perche' ``archivia_grezzi`` aggiunge una cartella
        # e ``tarfile`` ne ordina il contenuto; poiche' pero' e' un dettaglio
        # implementativo e non una garanzia, lo si verifica invece di fidarsene.
        precedente = ""
        with tarfile.open(self.archivio, "r|gz") as tar:
            for membro in tar:
                if not membro.isfile() or not self._e_nostro(membro.name):
                    continue
                nome = Path(membro.name).name
                if nome not in insieme:
                    continue
                if nome < precedente:
                    raise ErroreSorgente(
                        f"{self.archivio.name}: i dump non sono in ordine di nome "
                        f"({nome} dopo {precedente}). La deduplica registra i CAMBI, "
                        f"quindi leggerli fuori ordine produrrebbe righe sbagliate."
                    )
                precedente = nome
                estratto = tar.extractfile(membro)
                if estratto is not None:
                    yield nome, estratto.read()
