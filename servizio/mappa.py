"""
mappa.py — mappatura token ↔ dati reali del filtro-pii, una per progetto.

File: <progetto>\\.filtro-pii\\mappa.json, cifrato con Fernet. La chiave sta in
%APPDATA%\\claude-filtro-pii\\chiave.key (fuori dall'albero dei progetti, mai in
git); viene creata al primo uso.

Struttura in chiaro:
{
  "v": 1,
  "contatori": {"PERS": 3, "CF": 1},
  "entita": {"PERS_0001": {"tipo": "PERS", "varianti": {"": "Ginevra Quarzenti", "b": "GINEVRA QUARZENTI"}}},
  "indice": {"PERS|mario rossi": "PERS_0001"}
}
"""
from __future__ import annotations

import json
import os
import re
import threading
from pathlib import Path

TIPI = ("PERS", "CF", "IBAN", "EMAIL", "TEL", "IND", "NASC", "CARTA")
# Tipo maiuscolo e underscore facoltativo (PERS_0001, PERS_1, PERS_0001b);
# volutamente NON case-insensitive né con spazio: «tel 333…» non è un token.
# Lookaround invece di \b: il token può stare dentro un nome di file
# (Sentenza_101_PERS_0001c.pdf), dove «_» è carattere di parola.
RE_TOKEN = re.compile(
    r"(?<![A-Za-z])(" + "|".join(TIPI) + r")_?0*(\d{1,4})([a-z]{1,2})?(?![A-Za-z0-9])"
)
_RE_PUNT = re.compile(r"['\",;.()\[\]]")


def chiave_predefinita() -> Path:
    base = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
    return base / "claude-filtro-pii" / "chiave.key"


def carica_chiave(percorso: Path | None = None) -> bytes:
    """Legge la chiave Fernet; se manca la crea (solo utente corrente)."""
    from cryptography.fernet import Fernet
    p = percorso or chiave_predefinita()
    if p.exists():
        return p.read_bytes().strip()
    p.parent.mkdir(parents=True, exist_ok=True)
    k = Fernet.generate_key()
    p.write_bytes(k)
    return k


def normalizza(tipo: str, superficie: str) -> str:
    """Chiave d'indice: stessa persona con grafie diverse → stessa chiave."""
    s = superficie.strip()
    if tipo == "PERS":
        parole = [_RE_PUNT.sub("", p).lower() for p in re.split(r"[\s_]+", s) if p]
        parole = [p for p in parole if p]
        return " ".join(sorted(parole))
    if tipo in ("IBAN", "CF", "TEL", "CARTA"):
        return re.sub(r"[\s.\-]", "", s).upper()
    if tipo == "EMAIL":
        return s.lower()
    return re.sub(r"\s+", " ", s).lower()


def _suffisso(i: int) -> str:
    """Indice variante → suffisso: 0 → '', 1 → 'b' … 25 → 'z', 26 → 'aa', 27 → 'ab' …"""
    if i == 0:
        return ""
    if i <= 25:
        return chr(ord("a") + i)
    j = i - 26
    return chr(ord("a") + j // 26) + chr(ord("a") + j % 26)


class Mappa:
    def __init__(self, percorso: Path | None = None, chiave: bytes | None = None):
        self.percorso = Path(percorso) if percorso else None
        self._chiave = chiave
        self._lock = threading.RLock()
        self._sporca = False
        self._rx_noti = None
        self._rx_versione = -1
        self._versione = 0
        self.dati = {"v": 1, "contatori": {}, "entita": {}, "indice": {}}
        if self.percorso and self.percorso.exists():
            self._carica()

    # ── persistenza ──────────────────────────────────────────────────────────
    def _fernet(self):
        from cryptography.fernet import Fernet
        if self._chiave is None:
            self._chiave = carica_chiave()
        return Fernet(self._chiave)

    def _carica(self):
        raw = json.loads(self.percorso.read_text(encoding="utf-8"))
        if "cifrato" in raw:
            chiaro = self._fernet().decrypt(raw["cifrato"].encode()).decode("utf-8")
            self.dati = json.loads(chiaro)
        else:  # mappa in chiaro (solo per test)
            self.dati = raw
        self.dati.setdefault("contatori", {})
        self.dati.setdefault("entita", {})
        self.dati.setdefault("indice", {})
        self._versione += 1

    def salva(self, in_chiaro: bool = False):
        if not self.percorso or not self._sporca:
            return
        with self._lock:
            self.percorso.parent.mkdir(parents=True, exist_ok=True)
            if in_chiaro:
                contenuto = json.dumps(self.dati, ensure_ascii=False, indent=1)
            else:
                chiaro = json.dumps(self.dati, ensure_ascii=False).encode("utf-8")
                contenuto = json.dumps({"v": 1, "cifrato": self._fernet().encrypt(chiaro).decode()})
            tmp = self.percorso.with_suffix(".tmp")
            tmp.write_text(contenuto, encoding="utf-8")
            os.replace(tmp, self.percorso)
            self._sporca = False

    # ── interrogazione ───────────────────────────────────────────────────────
    def vuota(self) -> bool:
        return not self.dati["entita"]

    def conteggi(self) -> dict[str, int]:
        return dict(self.dati["contatori"])

    def superficie(self, tipo: str, numero: int, variante: str = "") -> str | None:
        ent = self.dati["entita"].get(f"{tipo}_{numero:04d}")
        if not ent:
            return None
        return ent["varianti"].get(variante)

    def tipo_di_superficie(self, superficie: str) -> str | None:
        if self.risolvi_pers(superficie):
            return "PERS"
        for tipo in TIPI:
            if tipo != "PERS" and f"{tipo}|{normalizza(tipo, superficie)}" in self.dati["indice"]:
                return tipo
        return None

    def _parole_pers(self) -> dict[str, set[str]]:
        """parola → id delle persone che la contengono (cache per versione)."""
        if getattr(self, "_parole_versione", -1) != self._versione:
            idx: dict[str, set[str]] = {}
            for chiave, ident in self.dati["indice"].items():
                if chiave.startswith("PERS|"):
                    for p in chiave[5:].split():
                        idx.setdefault(p, set()).add(ident)
            self._parole = idx
            self._parole_versione = self._versione
        return self._parole

    def risolvi_pers(self, superficie: str) -> str | None:
        """Id della persona per una grafia: chiave esatta, oppure una sola parola
        (cognome o nome) che appartiene a UNA sola persona nota."""
        chiave = normalizza("PERS", superficie)
        ident = self.dati["indice"].get(f"PERS|{chiave}")
        if ident:
            return ident
        parole = chiave.split()
        if len(parole) == 1 and len(parole[0]) >= 4:
            ids = self._parole_pers().get(parole[0], set())
            if len(ids) == 1:
                return next(iter(ids))
        if len(parole) >= 2:
            # Più parole che stanno tutte nella stessa (unica) persona nota:
            # «Carlo Zanfardin» per «ZANFARDIN CARLO ENRICO».
            idx = self._parole_pers()
            comuni = None
            for p in parole:
                ids = idx.get(p)
                if not ids:
                    return None
                comuni = set(ids) if comuni is None else comuni & ids
                if not comuni:
                    return None
            if len(comuni) == 1:
                return next(iter(comuni))
        return None

    def regex_noti(self):
        """Alternanza di tutte le grafie note (case-insensitive), per ritrovare
        entità già viste anche dove le regex e spaCy non le prendono."""
        if self._rx_versione == self._versione:
            return self._rx_noti
        from itertools import permutations
        pezzi: list[str] = []
        for ent in self.dati["entita"].values():
            if ent["tipo"] == "PERS":
                # Tutte le permutazioni delle parole (Ginevra Quarzenti / ROSSI_MARIO),
                # separate da spazi o underscore.
                parole = sorted({p for v in ent["varianti"].values()
                                 for p in re.split(r"[\s_]+", _RE_PUNT.sub("", v).strip()) if p},
                                key=str.lower)
                if not parole or sum(map(len, parole)) < 4:
                    continue
                # Le parole si confrontano senza badare a maiuscole/minuscole:
                # la stessa persona vista in Title Case e in MAIUSCOLO ha due
                # parole, non quattro (altrimenti la grafia tutta minuscola
                # non veniva più ritrovata).
                tutte: dict[str, str] = {}
                gruppi: dict[tuple[str, ...], list[str]] = {}
                for v in ent["varianti"].values():
                    pv: dict[str, str] = {}
                    for p in re.split(r"[\s_]+", re.sub(r"['\",;.()\[\]]", "", v).strip()):
                        if p:
                            pv.setdefault(p.lower(), p)
                            tutte.setdefault(p.lower(), p)
                    if 2 <= len(pv) <= 4:
                        gruppi[tuple(sorted(pv))] = list(pv.values())
                if len(tutte) <= 4:
                    gruppi.setdefault(tuple(sorted(tutte)), list(tutte.values()))
                parole = sorted(tutte.values(), key=str.lower)
                # Ogni grafia già vista (e l'unione delle parole) in tutti gli ordini.
                for gruppo in gruppi.values():
                    for perm in permutations(gruppo):
                        pezzi.append(r"[\s_]+".join(re.escape(p) for p in perm))
                # Parola singola (cognome o nome ≥ 5 lettere), solo Capitalizzata
                # o MAIUSCOLA: «Bertolazzi», «BERTOLAZZI», non «bertolazzi».
                for p in parole:
                    if len(p) >= 5 and p.isalpha():
                        pezzi.append(f"(?-i:{re.escape(p.capitalize())}|{re.escape(p.upper())})")
            elif ent["tipo"] in ("EMAIL", "CF", "IBAN", "IND"):
                for v in ent["varianti"].values():
                    if len(v) >= 4:
                        pezzi.append(re.escape(v))
        if not pezzi:
            self._rx_noti = None
        else:
            alt = "|".join(sorted(set(pezzi), key=len, reverse=True))
            self._rx_noti = re.compile(r"(?<![\w])(?:" + alt + r")(?![\w])", re.IGNORECASE)
        self._rx_versione = self._versione
        return self._rx_noti

    # ── creazione token ──────────────────────────────────────────────────────
    def token(self, tipo: str, superficie: str, noto: str | None = None) -> str:
        if tipo not in TIPI:
            raise ValueError(f"tipo sconosciuto: {tipo}")
        with self._lock:
            chiave = f"{tipo}|{normalizza(tipo, superficie)}"
            ident = self.risolvi_pers(superficie) if tipo == "PERS" else self.dati["indice"].get(chiave)
            if ident is None and tipo == "PERS" and noto and noto in self.dati["entita"]:
                ident = noto  # due parole di una persona nota a tre parole, ecc.
            if ident is not None and chiave not in self.dati["indice"]:
                self.dati["indice"][chiave] = ident  # cognome solo → stessa persona
                self._sporca = True
                self._versione += 1
            if ident is None:
                n = self.dati["contatori"].get(tipo, 0) + 1
                self.dati["contatori"][tipo] = n
                ident = f"{tipo}_{n:04d}"
                self.dati["entita"][ident] = {"tipo": tipo, "varianti": {"": superficie}}
                self.dati["indice"][chiave] = ident
                self._sporca = True
                self._versione += 1
                return ident
            varianti = self.dati["entita"][ident]["varianti"]
            for lett, sup in varianti.items():
                if sup == superficie:
                    return ident + lett
            lett = _suffisso(len(varianti))
            varianti[lett] = superficie
            self._sporca = True
            self._versione += 1
            return ident + lett
