"""
misura_a_secco.py — prova il filtro-pii su una cartella di documenti veri
SENZA mandare nulla a Claude.

Uso:  py misura_a_secco.py            (chiede la cartella con una finestra)
      py misura_a_secco.py <cartella> [--non-aprire]

Legge tutti i documenti della cartella (PDF, TXT, EML, DOCX, XLSX, CSV, MSG),
li passa nel motore con una mappa temporanea (solo in memoria, non salvata)
e scrive un rapporto in %TEMP%\\filtro-pii-misura\\, che apre nel Blocco note.
Il rapporto contiene dati reali (quelli sfuggiti al filtro): lo legge solo
chi lo ha lanciato, poi va cestinato. A video escono soltanto conteggi.
"""
from __future__ import annotations

import os
import re
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from mappa import Mappa, RE_TOKEN  # noqa: E402
from motore import anonimizza, ripristina, carica_nlp, UPPER_BLACKLIST  # noqa: E402

ESCLUSI: list[str] = []  # nomi da non mascherare, come «esclusi» in .filtro-pii.json
MAX_CARATTERI_PER_FILE = 400_000


def scegli_cartella() -> Path | None:
    import tkinter
    from tkinter import filedialog
    radice = tkinter.Tk()
    radice.withdraw()
    radice.attributes("-topmost", True)
    scelta = filedialog.askdirectory(title="Scegli la cartella con i documenti da misurare")
    radice.destroy()
    return Path(scelta) if scelta else None


def testo_di(f: Path) -> str | None:
    """Testo del file, None se il tipo non è gestito. Solleva se la lettura fallisce."""
    est = f.suffix.lower()
    if est in (".txt", ".csv", ".md", ".xml", ".json", ".html", ".htm"):
        return f.read_text(encoding="utf-8", errors="replace")
    if est == ".pdf":
        import fitz
        with fitz.open(f) as doc:
            return "\n".join(p.get_text() for p in doc)
    if est == ".eml":
        import email
        from email import policy
        msg = email.message_from_bytes(f.read_bytes(), policy=policy.default)
        parti = [f"From: {msg.get('From', '')}", f"To: {msg.get('To', '')}", f"Subject: {msg.get('Subject', '')}"]
        corpo = msg.get_body(preferencelist=("plain", "html"))
        if corpo is not None:
            parti.append(corpo.get_content())
        return "\n".join(parti)
    if est == ".docx":
        import docx
        d = docx.Document(str(f))
        righe = [p.text for p in d.paragraphs]
        for t in d.tables:
            for r in t.rows:
                righe.append(" | ".join(c.text for c in r.cells))
        return "\n".join(righe)
    if est in (".xlsx", ".xlsm"):
        import openpyxl
        wb = openpyxl.load_workbook(str(f), read_only=True, data_only=True)
        righe = []
        for ws in wb.worksheets:
            for r in ws.iter_rows(values_only=True):
                righe.append(";".join("" if c is None else str(c) for c in r))
        return "\n".join(righe)
    if est == ".msg":
        import extract_msg
        m = extract_msg.Message(str(f))
        return f"From: {m.sender}\nTo: {m.to}\nSubject: {m.subject}\n{m.body or ''}"
    return None


RE_MAIUSCOLA = re.compile(r"\b[A-ZÀ-Þ][A-Za-zÀ-ÿ']{2,}\b")


def main() -> int:
    argomenti = [a for a in sys.argv[1:] if not a.startswith("--")]
    apri = "--non-aprire" not in sys.argv
    cartella = Path(argomenti[0]) if argomenti else scegli_cartella()
    if cartella is None or not cartella.is_dir():
        print("Nessuna cartella scelta: non ho fatto nulla.")
        return 1

    print("Carico il motore (15-20 secondi)…")
    nlp = carica_nlp()
    mappa = Mappa()  # solo in memoria
    uscita = Path(os.environ.get("TEMP", ".")) / "filtro-pii-misura"
    uscita.mkdir(parents=True, exist_ok=True)
    rapporto = uscita / f"misura_{time.strftime('%Y%m%d_%H%M%S')}.txt"

    letti = saltati = errori = senza_testo = giro_fallito = 0
    sostituzioni = caratteri = 0
    tipi_saltati: Counter[str] = Counter()
    rimaste: Counter[str] = Counter()
    blocchi: list[str] = []
    inizio = time.time()

    for f in sorted(p for p in cartella.rglob("*") if p.is_file()):
        relativo = str(f.relative_to(cartella))
        nome_mascherato, n_nome = anonimizza(relativo, mappa, nlp=nlp, esclusi=ESCLUSI)
        sostituzioni += n_nome
        try:
            testo = testo_di(f)
        except Exception as e:
            errori += 1
            blocchi.append(f"\n===== {nome_mascherato} =====\n[non letto: {type(e).__name__}]\n")
            continue
        if testo is None:
            saltati += 1
            tipi_saltati[f.suffix.lower() or "(senza estensione)"] += 1
            continue
        if not testo.strip():
            senza_testo += 1
            blocchi.append(f"\n===== {nome_mascherato} =====\n[nessun testo: probabile scansione]\n")
            continue
        letti += 1
        testo = testo[:MAX_CARATTERI_PER_FILE]
        caratteri += len(testo)
        mascherato, n = anonimizza(testo, mappa, nlp=nlp, esclusi=ESCLUSI)
        sostituzioni += n
        if ripristina(mascherato, mappa)[0] != testo:
            giro_fallito += 1
            blocchi.append(f"\n[ATTENZIONE: il ripristino di {nome_mascherato} non restituisce il testo originale]\n")
        for m in RE_MAIUSCOLA.finditer(RE_TOKEN.sub(" ", mascherato)):
            p = m.group(0)
            if p.upper() not in UPPER_BLACKLIST:
                rimaste[p] += 1
        blocchi.append(f"\n===== {nome_mascherato} ({n} sostituzioni) =====\n{mascherato}\n")

    conteggi = mappa.conteggi()
    testa = [
        "MISURA A SECCO DEL FILTRO-PII — contiene dati reali sfuggiti al filtro: leggere e poi cestinare",
        f"Data: {time.strftime('%d/%m/%Y %H:%M')}",
        f"File letti: {letti} | senza testo (scansioni): {senza_testo} | non gestiti: {saltati} "
        f"{dict(tipi_saltati)} | errori di lettura: {errori}",
        f"Caratteri esaminati: {caratteri} | sostituzioni: {sostituzioni} | entità distinte: {conteggi}",
        "",
        "COME LEGGERLO",
        "1) Scorri l'elenco qui sotto: sono le parole con l'iniziale maiuscola rimaste in chiaro,",
        "   dalle più frequenti. Cerca cognomi e nomi di persone: sono le fughe.",
        "2) Per capire dove sta una fuga, cerca la parola (Ctrl+F) nel testo mascherato più sotto.",
        "3) Nel testo mascherato cerca anche nomi scritti tutti in minuscolo, indirizzi, telefoni fissi.",
        "",
        "PAROLE CON LA MAIUSCOLA RIMASTE IN CHIARO (parola: volte)",
    ]
    elenco = [f"  {p}: {n}" for p, n in sorted(rimaste.items(), key=lambda x: (-x[1], x[0]))]
    rapporto.write_text("\n".join(testa + elenco) + "\n\nTESTO MASCHERATO\n" + "".join(blocchi), encoding="utf-8")

    print(f"File letti: {letti}; senza testo: {senza_testo}; non gestiti: {saltati}; errori: {errori}")
    print(f"Sostituzioni: {sostituzioni}; entita distinte per tipo: {conteggi}")
    print(f"Parole con la maiuscola rimaste in chiaro: {len(rimaste)} diverse")
    print(f"Documenti in cui il ripristino non restituisce l'originale: {giro_fallito}")
    print(f"Tempo: {round(time.time() - inizio)} secondi")
    print("Rapporto scritto nella cartella temporanea filtro-pii-misura (si apre nel Blocco note).")
    if apri:
        os.startfile(str(rapporto))  # noqa: S606
    return 0


if __name__ == "__main__":
    sys.exit(main())
