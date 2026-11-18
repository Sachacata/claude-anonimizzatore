"""
semina.py — elenco delle persone già note di un progetto.

Un cognome scritto da solo in mezzo a una frase non ha nulla che lo distingua
da una parola qualsiasi: il filtro lo riconosce solo se quella persona è già
nella mappa. Questo modulo riempie la mappa in anticipo con i nominativi di un
elenco del progetto (per esempio un registro Excel delle pratiche), così le
note e i log che citano persone già trattate vengono mascherati fin dalla
prima riga.

Si attiva dal file .filtro-pii.json del progetto:

  "noti": [{"file": "registro_sentenze_lavorate.xlsx",
            "persone": [["Cognome", "Nome"], ["Avvocato"]]}]

«file» è relativo alla radice del progetto (o assoluto); «persone» elenca i
gruppi di colonne (per intestazione) che insieme fanno un nominativo; «fogli»
(facoltativo, predefinito 1) dice quanti fogli leggere. Il file viene riletto
solo quando cambia. Nel log finiscono soltanto conteggi, mai nomi.
"""
from __future__ import annotations

import re
from pathlib import Path

from motore import UPPER_BLACKLIST
from nomi_battesimo import PAROLE_COMUNI, PARTICELLE

_RE_TITOLO = re.compile(r"(?i)^(?:avv(?:ocato)?|dott|prof|sig|ing)\.?[ \t]*(?:ti|ssa|ra)?\.?[ \t]+")
_RE_SEPARA = re.compile(r"\s*[/;,]\s*|\s+-\s+|\s+e\s+")
RIGHE_INTESTAZIONE = 15


def _pulisci(v) -> str:
    s = re.sub(r"\s+", " ", str(v)).strip()
    while True:
        t = _RE_TITOLO.sub("", s)
        if t == s:
            return s
        s = t


def _valido(s: str) -> bool:
    parole = s.split()
    if not 1 <= len(parole) <= 5 or len(s.replace(" ", "")) < 4 or re.search(r"[\d@/\\_]", s):
        return False
    if any(p.strip("'.").upper() in UPPER_BLACKLIST for p in parole):
        return False
    return not all(p.lower() in PAROLE_COMUNI or p.lower() in PARTICELLE for p in parole)


def semina_noti(mappa, root: Path, voci, visti: dict) -> int:
    """Aggiunge alla mappa i nominativi degli elenchi indicati. `visti` ricorda
    la data di modifica dei file già letti. Ritorna quante persone nuove."""
    nuove = 0
    for voce in voci or []:
        f = Path(voce["file"])
        if not f.is_absolute():
            f = Path(root) / f
        if not f.exists():
            continue
        modifica = f.stat().st_mtime
        if visti.get(str(f)) == modifica:
            continue
        gruppi = [[c.strip().lower() for c in g] for g in voce.get("persone", [])]
        if not gruppi:
            continue
        import openpyxl
        prima = mappa.conteggi().get("PERS", 0)
        wb = openpyxl.load_workbook(str(f), read_only=True, data_only=True)
        try:
            for ws in wb.worksheets[: int(voce.get("fogli", 1))]:
                colonne = None
                for n_riga, riga in enumerate(ws.iter_rows(values_only=True)):
                    if colonne is None:
                        nomi: dict[str, int] = {}
                        for i, c in enumerate(riga):
                            if c is not None:
                                nomi.setdefault(str(c).strip().lower(), i)
                        if all(c in nomi for g in gruppi for c in g):
                            colonne = nomi
                        elif n_riga >= RIGHE_INTESTAZIONE:
                            break
                        continue
                    for g in gruppi:
                        parti = [_pulisci(riga[colonne[c]]) for c in g
                                 if colonne[c] < len(riga) and riga[colonne[c]] not in (None, "")]
                        if len(parti) != len(g):
                            continue
                        candidati = [" ".join(parti)] if len(g) > 1 else _RE_SEPARA.split(parti[0])
                        for s in candidati:
                            s = _pulisci(s)
                            if _valido(s):
                                mappa.token("PERS", s)
        finally:
            wb.close()
        visti[str(f)] = modifica
        nuove += mappa.conteggi().get("PERS", 0) - prima
    return nuove
