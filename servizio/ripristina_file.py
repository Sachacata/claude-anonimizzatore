"""
ripristina_file.py — strumento di riserva: rimette i dati reali al posto dei
token in un file già scritto (txt, md, csv, json, docx, xlsx, pdf), usando la
mappa cifrata del progetto. Serve se un file è stato prodotto fuori dal filtro
(es. da uno script che ha stampato token in un file).

Uso:
  py ripristina_file.py <cartella_progetto> <file> [<file> ...] [--anonimizza]

Con --anonimizza fa il contrario (dati reali → token), per controllare a mano
cosa vedrebbe il modello. L'output è scritto accanto al file: nome_reale.ext
(o nome_anon.ext). Il file originale non viene toccato.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

QUI = Path(__file__).resolve().parent
sys.path.insert(0, str(QUI))
from mappa import Mappa, RE_TOKEN  # noqa: E402
from motore import anonimizza, carica_nlp, ripristina  # noqa: E402


def _trasforma(testo: str, mappa: Mappa, verso_token: bool, nlp) -> tuple[str, int]:
    if verso_token:
        return anonimizza(testo, mappa, nlp)
    return ripristina(testo, mappa)


def _testo(src: Path, dst: Path, mappa, verso_token, nlp) -> int:
    t = src.read_text(encoding="utf-8", errors="replace")
    out, n = _trasforma(t, mappa, verso_token, nlp)
    dst.write_text(out, encoding="utf-8")
    return n


def _docx(src: Path, dst: Path, mappa, verso_token, nlp) -> int:
    from docx import Document
    doc = Document(str(src))
    n = 0

    def paragrafi():
        yield from doc.paragraphs
        for t in doc.tables:
            for r in t.rows:
                for c in r.cells:
                    yield from c.paragraphs
        for s in doc.sections:
            for parte in (s.header, s.footer):
                yield from parte.paragraphs

    for p in paragrafi():
        if not p.runs:
            continue
        testo = p.text
        out, k = _trasforma(testo, mappa, verso_token, nlp)
        if k == 0:
            continue
        n += k
        # Riscrive nel primo run (perde la formattazione dei run successivi).
        p.runs[0].text = out
        for r in p.runs[1:]:
            r.text = ""
    doc.save(str(dst))
    return n


def _xlsx(src: Path, dst: Path, mappa, verso_token, nlp) -> int:
    import openpyxl
    wb = openpyxl.load_workbook(str(src))
    n = 0
    for ws in wb.worksheets:
        for riga in ws.iter_rows():
            for cella in riga:
                if isinstance(cella.value, str):
                    out, k = _trasforma(cella.value, mappa, verso_token, nlp)
                    if k:
                        cella.value = out
                        n += k
    wb.save(str(dst))
    return n


def _pdf(src: Path, dst: Path, mappa, verso_token, nlp) -> int:
    import fitz
    doc = fitz.open(str(src))
    n = 0
    for pagina in doc:
        testo = pagina.get_text()
        if verso_token:
            _, trovati = anonimizza(testo, mappa, nlp), None
            coppie = []
            # Ricava le coppie originale→token confrontando le entità note.
            for ent in mappa.dati["entita"].values():
                for sup in ent["varianti"].values():
                    if sup in testo:
                        coppie.append((sup, mappa.token(ent["tipo"], sup)))
        else:
            coppie = []
            for m in RE_TOKEN.finditer(testo):
                sup = mappa.superficie(m.group(1), int(m.group(2)), (m.group(3) or ""))
                if sup:
                    coppie.append((m.group(0), sup))
        for vecchio, nuovo in sorted(set(coppie), key=lambda c: -len(c[0])):
            for rett in pagina.search_for(vecchio):
                pagina.add_redact_annot(rett, text=nuovo, fontsize=8, fill=(1, 1, 1))
                n += 1
        if n:
            pagina.apply_redactions()
    doc.save(str(dst))
    return n


GESTORI = {".txt": _testo, ".md": _testo, ".csv": _testo, ".json": _testo, ".eml": _testo,
           ".py": _testo, ".html": _testo, ".docx": _docx, ".xlsx": _xlsx, ".pdf": _pdf}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("progetto")
    ap.add_argument("file", nargs="+")
    ap.add_argument("--anonimizza", action="store_true", help="dati reali → token (per controllo)")
    a = ap.parse_args()
    root = Path(a.progetto).resolve()
    mappa = Mappa(root / ".filtro-pii" / "mappa.json")
    nlp = carica_nlp() if a.anonimizza else None
    suffisso = "_anon" if a.anonimizza else "_reale"
    for f in a.file:
        src = Path(f)
        g = GESTORI.get(src.suffix.lower())
        if g is None:
            print(f"salto {src.name}: formato non gestito")
            continue
        dst = src.with_name(src.stem + suffisso + src.suffix)
        n = g(src, dst, mappa, a.anonimizza, nlp)
        print(f"{src.name} → {dst.name}: {n} sostituzioni")
    mappa.salva()


if __name__ == "__main__":
    main()
