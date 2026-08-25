"""Configurazione comune dei test.

Il progetto non e' un pacchetto installabile e non vogliamo che lo diventi: e' un
insieme di script eseguiti con ``python -m src....`` dalla radice. Per farli
importare anche quando pytest viene lanciato da una sottocartella, aggiungiamo la
radice del repository al percorso di ricerca dei moduli.
"""

from __future__ import annotations

import sys
from pathlib import Path

RADICE = Path(__file__).resolve().parent.parent
if str(RADICE) not in sys.path:
    sys.path.insert(0, str(RADICE))
