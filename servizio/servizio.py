"""
servizio.py — servizio HTTP locale del filtro-pii (solo 127.0.0.1).

Avvio:  py servizio.py [--porta 5117] [--senza-spacy]
Ferma:  POST /arresta  (o chiudi il processo)

Endpoint JSON (Content-Type: application/json):
  GET  /stato                         → {ok, modello, progetti:{root:{conteggi}}, uptime_s}
  POST /anonimizza {progetto, testo}  → {testo, n}
  POST /ripristina {progetto, testo}  → {testo, n}
  POST /ricarica   {progetto}         → {ok, config}
  POST /arresta                       → {ok}

«progetto» è la cartella radice del progetto (assoluta). Lì il servizio legge
.filtro-pii.json (esclusi, ecc.) e tiene la mappa cifrata in .filtro-pii\\mappa.json.
Il log non contiene mai il testo trattato, solo dimensioni e tempi.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import threading
import time
from collections import OrderedDict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from logging.handlers import RotatingFileHandler
from pathlib import Path

QUI = Path(__file__).resolve().parent
sys.path.insert(0, str(QUI))
from mappa import Mappa  # noqa: E402
from motore import anonimizza, carica_nlp, ripristina  # noqa: E402

VERSIONE = "0.1.0"
PORTA_PREDEFINITA = 5117
MAX_BODY = 20 * 1024 * 1024
BLOCCO_SPACY = 100_000  # caratteri per blocco passato a spaCy

log = logging.getLogger("filtro-pii")


def _config_log():
    # Fuori dalla cartella della mod: una mod installata sta in una copia che
    # gli aggiornamenti riscrivono.
    base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    cartella = base / "claude-filtro-pii" / "log"
    cartella.mkdir(parents=True, exist_ok=True)
    h = RotatingFileHandler(cartella / "servizio.log", maxBytes=1_000_000, backupCount=1, encoding="utf-8")
    h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    log.addHandler(h)
    log.addHandler(logging.StreamHandler(sys.stderr))
    log.setLevel(logging.INFO)


class Progetto:
    def __init__(self, root: Path):
        self.root = root
        self.lock = threading.RLock()
        self.config: dict = {}
        self.mappa = Mappa(root / ".filtro-pii" / "mappa.json")
        self._noti_visti: dict = {}
        self.ricarica()

    def ricarica(self):
        p = self.root / ".filtro-pii.json"
        try:
            self.config = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
        except Exception as e:  # file rotto: meglio filtrare senza esclusi che non filtrare
            log.warning("config illeggibile in %s: %s", self.root, e)
            self.config = {}
        self.aggiorna_noti()
        gi = self.root / ".gitignore"
        try:
            if not gi.exists() or ".filtro-pii/" not in gi.read_text(encoding="utf-8"):
                with gi.open("a", encoding="utf-8") as f:
                    f.write("\n.filtro-pii/\n")
        except Exception as e:
            log.warning("gitignore non aggiornabile in %s: %s", self.root, e)

    def aggiorna_noti(self):
        """Mette in mappa i nominativi degli elenchi «noti» della configurazione
        (riletti solo se il file è cambiato). Nel log solo conteggi."""
        voci = self.config.get("noti")
        if not voci:
            return
        try:
            from semina import semina_noti
            t = time.time()
            n = semina_noti(self.mappa, self.root, voci, self._noti_visti)
            if n:
                self.mappa.salva()
                log.info("elenco noti: %d persone nuove in %.1f s", n, time.time() - t)
        except Exception as e:  # elenco rotto o aperto in Excel: si filtra lo stesso
            log.warning("elenco noti non caricato in %s: %s", self.root, type(e).__name__)

    @property
    def esclusi(self) -> list[str]:
        return list(self.config.get("esclusi", []))


class Stato:
    def __init__(self, usa_spacy: bool):
        self.avvio = time.time()
        self.progetti: dict[str, Progetto] = {}
        self.lock = threading.Lock()
        self.nlp = None
        self.modello = "regex"
        if usa_spacy:
            t = time.time()
            try:
                self.nlp = carica_nlp()
                self.modello = "spacy:it_core_news_lg"
                log.info("spaCy caricato in %.1f s", time.time() - t)
            except Exception as e:
                log.error("spaCy non disponibile (%s): solo regex", e)
        self.cache: OrderedDict[tuple, tuple[str, int]] = OrderedDict()
        self.server: ThreadingHTTPServer | None = None

    def progetto(self, root: str) -> Progetto:
        chiave = str(Path(root).resolve()).lower()
        with self.lock:
            p = self.progetti.get(chiave)
            if p is None:
                p = Progetto(Path(root).resolve())
                self.progetti[chiave] = p
            return p

    def _in_cache(self, k):
        v = self.cache.get(k)
        if v is not None:
            self.cache.move_to_end(k)
        return v

    def _salva_cache(self, k, v):
        self.cache[k] = v
        while len(self.cache) > 256:
            self.cache.popitem(last=False)

    def anonimizza(self, root: str, testo: str) -> tuple[str, int]:
        p = self.progetto(root)
        with p.lock:
            p.aggiorna_noti()
            k = ("a", p.root, p.mappa._versione, hash(testo), len(testo))
            v = self._in_cache(k)
            if v is not None:
                return v
            t = time.time()
            if len(testo) <= BLOCCO_SPACY:
                out, n = anonimizza(testo, p.mappa, self.nlp, p.esclusi)
            else:
                pezzi, n = [], 0
                for blocco in _blocchi(testo, BLOCCO_SPACY):
                    b, k2 = anonimizza(blocco, p.mappa, self.nlp, p.esclusi)
                    pezzi.append(b)
                    n += k2
                out = "".join(pezzi)
            p.mappa.salva()
            k = ("a", p.root, p.mappa._versione, hash(testo), len(testo))
            self._salva_cache(k, (out, n))
            log.info("anonimizza %d car. → %d sostituzioni in %.2f s", len(testo), n, time.time() - t)
            return out, n

    def ripristina(self, root: str, testo: str) -> tuple[str, int]:
        p = self.progetto(root)
        with p.lock:
            out, n = ripristina(testo, p.mappa)
            if n:
                log.info("ripristina %d car. → %d token", len(testo), n)
            return out, n


def _blocchi(testo: str, dim: int):
    """Spezza un testo lungo a fine riga, in blocchi di circa `dim` caratteri."""
    pos = 0
    while pos < len(testo):
        fine = min(len(testo), pos + dim)
        if fine < len(testo):
            a_capo = testo.rfind("\n", pos + dim // 2, fine)
            if a_capo != -1:
                fine = a_capo + 1
        yield testo[pos:fine]
        pos = fine


STATO: Stato


class Gestore(BaseHTTPRequestHandler):
    server_version = f"filtro-pii/{VERSIONE}"
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):  # niente log di default (conterrebbe gli URL)
        pass

    def _json(self, codice: int, corpo: dict):
        dati = json.dumps(corpo, ensure_ascii=False).encode("utf-8")
        self.send_response(codice)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(dati)))
        self.end_headers()
        self.wfile.write(dati)

    def _leggi(self) -> dict:
        n = int(self.headers.get("Content-Length") or 0)
        if n > MAX_BODY:
            raise ValueError("corpo troppo grande")
        if n == 0:
            return {}
        return json.loads(self.rfile.read(n).decode("utf-8"))

    def do_GET(self):
        if self.path == "/stato":
            return self._json(200, {
                "ok": True, "versione": VERSIONE, "modello": STATO.modello,
                "uptime_s": round(time.time() - STATO.avvio),
                "progetti": {str(p.root): p.mappa.conteggi() for p in STATO.progetti.values()},
            })
        self._json(404, {"errore": "sconosciuto"})

    def do_POST(self):
        try:
            corpo = self._leggi()
        except Exception as e:
            return self._json(400, {"errore": f"richiesta non valida: {e}"})
        try:
            if self.path == "/anonimizza":
                testo, n = STATO.anonimizza(corpo["progetto"], corpo.get("testo", ""))
                return self._json(200, {"testo": testo, "n": n})
            if self.path == "/ripristina":
                testo, n = STATO.ripristina(corpo["progetto"], corpo.get("testo", ""))
                return self._json(200, {"testo": testo, "n": n})
            if self.path == "/ricarica":
                p = STATO.progetto(corpo["progetto"])
                with p.lock:
                    p.ricarica()
                return self._json(200, {"ok": True, "config": p.config})
            if self.path == "/arresta":
                self._json(200, {"ok": True})
                threading.Thread(target=STATO.server.shutdown, daemon=True).start()
                return
            self._json(404, {"errore": "sconosciuto"})
        except KeyError as e:
            self._json(400, {"errore": f"manca il campo {e}"})
        except Exception as e:
            log.exception("errore in %s", self.path)
            self._json(500, {"errore": str(e)})


def main():
    global STATO
    ap = argparse.ArgumentParser()
    ap.add_argument("--porta", type=int, default=PORTA_PREDEFINITA)
    ap.add_argument("--senza-spacy", action="store_true")
    a = ap.parse_args()
    _config_log()
    STATO = Stato(usa_spacy=not a.senza_spacy)
    srv = ThreadingHTTPServer(("127.0.0.1", a.porta), Gestore)
    srv.daemon_threads = True
    STATO.server = srv
    log.info("in ascolto su 127.0.0.1:%d (%s)", a.porta, STATO.modello)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        for p in STATO.progetti.values():
            p.mappa.salva()
        log.info("fermato")


if __name__ == "__main__":
    main()
