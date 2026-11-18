"""Genera l'infografica in italiano e in inglese (SVG, nessuna libreria).

Uso:  py docs\\genera_infografica.py
Scrive docs\\infografica.it.svg e docs\\infographic.en.svg.

I segnaposto d'esempio sono composti a pezzi (funzione seg): chi modifica
questo file da una sessione protetta dal filtro non deve mai scriverli interi,
altrimenti verrebbero rimessi in chiaro con un dato reale.
"""
from pathlib import Path
from xml.sax.saxutils import escape

QUI = Path(__file__).resolve().parent
W, H = 1200, 1535

BLU, VERDE, AMBRA, ROSSO = "#1d4ed8", "#15803d", "#b45309", "#b91c1c"
NAVY, TESTO, GRIGIO, BORDO = "#14213d", "#1b2430", "#475569", "#cbd5e1"
SANS = "Segoe UI, Helvetica Neue, Helvetica, Arial, sans-serif"
MONO = "Consolas, Menlo, DejaVu Sans Mono, monospace"


def seg(tipo: str, n: int = 1) -> str:
    return tipo + "_" + f"{n:04d}"


TESTI = {
    "it": {
        "file": "infografica.it.svg",
        "titolo": "Come funziona il filtro che nasconde i dati personali a Claude Code",
        "s1": "In entrata: i dati personali diventano segnaposto",
        "pc": "IL TUO COMPUTER", "filtro": "FILTRO LOCALE", "cloud": "CLAUDE (CLOUD)",
        "pc1": "Documento con i dati veri", "cloud1": "Il modello vede solo segnaposto",
        "f1": ["servizio su 127.0.0.1", "regole + spaCy (italiano)", "mappa cifrata sul tuo PC"],
        "pill1": "dati veri  →  segnaposto",
        "veri": ["Ricorrente: Mario Rossi", "C.F. RSSMRA80A01H501U", "IBAN IT60 X054 2811 1010…",
                 "mario.rossi@example.com", "Cell. 333 1234567"],
        "finti": [("Ricorrente: ", seg("PERS")), ("C.F. ", seg("CF")), ("IBAN ", seg("IBAN")),
                  ("", seg("EMAIL")), ("Cell. ", seg("TEL"))],
        "s2": "In uscita: i segnaposto tornano dati veri, ma solo sul tuo computer",
        "cloud2": "Chiede di scrivere un file:", "pc2": "File salvato su disco:",
        "lettera": "Lettera per ", "nome": "Mario Rossi",
        "f2": ["solo negli strumenti locali:", "Write, Edit, Bash, PowerShell…"],
        "pill2": "segnaposto  →  dati veri",
        "fuori": "Verso web, posta e connettori esterni i segnaposto restano segnaposto: i dati veri non escono.",
        "s3": "Tre regole di sicurezza",
        "regole": [("Tutto in locale", "Il servizio ascolta solo su 127.0.0.1", "e non fa chiamate di rete."),
                   ("Filtro fermo? Non passa nulla", "Prompt bloccato, risultati trattenuti:", "mai testo in chiaro."),
                   ("PDF, Office e immagini bloccati", "Niente lettura diretta: il testo si", "estrae in locale e passa dal filtro.")],
        "s4": "Cosa riconosce",
        "tipi": [("PERS", "nomi e cognomi"), ("CF", "codice fiscale"), ("IBAN", "conto corrente"), ("EMAIL", "posta elettronica"),
                 ("TEL", "cellulare"), ("IND", "indirizzo"), ("NASC", "data di nascita"), ("CARTA", "numero di carta")],
        "s5": "Limiti da conoscere",
        "limiti": [("Qualcosa può sfuggire", "cognomi isolati, nomi rari:", "prova prima sui tuoi documenti"),
                   ("Le immagini non sono filtrate", "screenshot e scansioni arrivano", "al modello così come sono"),
                   ("Solo Windows, solo italiano", "riduce i dati che escono, non è", "una garanzia di conformità al GDPR")],
        "s6": "Lo stato, sempre visibile sotto il prompt",
        "stati": [("Protetta", "progetto protetto, servizio attivo"),
                  ("Filtro fermo", "servizio fermo: tutto trattenuto"),
                  ("Filtro spento", "un clic, o /filtro acceso, lo accende")],
        "piede": "Licenza MIT  ·  tutti i dati d'esempio sono inventati",
    },
    "en": {
        "file": "infographic.en.svg",
        "titolo": "How the filter that hides personal data from Claude Code works",
        "s1": "Inbound: personal data becomes placeholders",
        "pc": "YOUR COMPUTER", "filtro": "LOCAL FILTER", "cloud": "CLAUDE (CLOUD)",
        "pc1": "Document with the real data", "cloud1": "The model only sees placeholders",
        "f1": ["service on 127.0.0.1", "rules + spaCy (Italian)", "encrypted map on your PC"],
        "pill1": "real data  →  placeholders",
        "veri": ["Claimant: Mario Rossi", "Tax code RSSMRA80A01H501U", "IBAN IT60 X054 2811 1010…",
                 "mario.rossi@example.com", "Mobile 333 1234567"],
        "finti": [("Claimant: ", seg("PERS")), ("Tax code ", seg("CF")), ("IBAN ", seg("IBAN")),
                  ("", seg("EMAIL")), ("Mobile ", seg("TEL"))],
        "s2": "Outbound: placeholders become real data again, but only on your computer",
        "cloud2": "Asks to write a file:", "pc2": "File saved on disk:",
        "lettera": "Letter to ", "nome": "Mario Rossi",
        "f2": ["only in local tools:", "Write, Edit, Bash, PowerShell…"],
        "pill2": "placeholders  →  real data",
        "fuori": "Towards the web, email and external connectors placeholders stay placeholders: real data never leaves.",
        "s3": "Three safety rules",
        "regole": [("Everything stays local", "The service listens on 127.0.0.1 only", "and makes no network calls."),
                   ("Filter down? Nothing gets through", "Prompt blocked, tool results withheld:", "never plain text."),
                   ("PDF, Office and images blocked", "No direct reading: text is extracted", "locally and goes through the filter.")],
        "s4": "What it recognises",
        "tipi": [("PERS", "first and last names"), ("CF", "Italian tax code"), ("IBAN", "bank account"), ("EMAIL", "email address"),
                 ("TEL", "mobile number"), ("IND", "street address"), ("NASC", "date of birth"), ("CARTA", "card number")],
        "s5": "Limits you should know",
        "limiti": [("Something may slip through", "lone surnames, rare names:", "measure it on your own documents"),
                   ("Images are not filtered", "screenshots and scans reach", "the model as they are"),
                   ("Windows only, Italian only", "it reduces what leaves your PC; it is", "not a GDPR compliance guarantee")],
        "s6": "Status, always visible below the prompt",
        "stati": [("Protetta", "project protected, service running"),
                  ("Filtro fermo", "service down: everything withheld"),
                  ("Filtro spento", "one click, or /filtro acceso, turns it on")],
        "piede": "MIT licence  ·  all sample data is made up",
    },
}


class Svg:
    def __init__(self):
        self.p = []

    def rect(self, x, y, w, h, fill="#ffffff", stroke=BORDO, rx=14, sw=1.5):
        s = f' stroke="{stroke}" stroke-width="{sw}"' if stroke else ""
        self.p.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="{fill}"{s}/>')

    def text(self, x, y, s, size=16, fill=TESTO, weight=400, anchor="start", mono=False, spacing=None):
        fam = MONO if mono else SANS
        sp = f' letter-spacing="{spacing}"' if spacing else ""
        self.p.append(f'<text x="{x}" y="{y}" font-family="{fam}" font-size="{size}" font-weight="{weight}" '
                      f'fill="{fill}" text-anchor="{anchor}"{sp}>{escape(s)}</text>')

    def due(self, x, y, a, b, size=15, colore=BLU):
        """Riga a spaziatura fissa: parte normale + segnaposto evidenziato."""
        self.p.append(f'<text x="{x}" y="{y}" font-family="{MONO}" font-size="{size}" fill="{TESTO}" xml:space="preserve">'
                      f'{escape(a)}<tspan fill="{colore}" font-weight="700">{escape(b)}</tspan></text>')

    def freccia(self, x1, y1, x2, y2, colore, nome):
        self.p.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{colore}" stroke-width="4" '
                      f'stroke-linecap="round" marker-end="url(#{nome})"/>')

    def scudo(self, cx, cy, colore=VERDE, scala=1.0):
        self.p.append(f'<g transform="translate({cx},{cy}) scale({scala})">'
                      f'<path d="M0,-24 L20,-15 L20,3 C20,17 9,26 0,30 C-9,26 -20,17 -20,3 L-20,-15 Z" fill="{colore}"/>'
                      f'<path d="M-9,2 L-2,10 L11,-7" fill="none" stroke="#ffffff" stroke-width="4.5" '
                      f'stroke-linecap="round" stroke-linejoin="round"/></g>')

    def sezione(self, n, y, titolo):
        self.p.append(f'<circle cx="58" cy="{y - 6}" r="16" fill="{NAVY}"/>')
        self.text(58, y, str(n), 17, "#ffffff", 700, "middle")
        self.text(86, y, titolo, 21, NAVY, 700)

    def fine(self):
        testa = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img">\n'
                 '<defs>\n'
                 + "".join(f'<marker id="{n}" viewBox="0 0 10 10" refX="7" refY="5" markerWidth="5" markerHeight="5" '
                           f'orient="auto"><path d="M0,0 L10,5 L0,10 Z" fill="{c}"/></marker>\n'
                           for n, c in (("fb", BLU), ("fv", VERDE)))
                 + '</defs>\n')
        return testa + "\n".join(self.p) + "\n</svg>\n"


def disegna(t: dict) -> str:
    s = Svg()
    s.rect(0, 0, W, H, "#f6f8fb", None, 0)
    s.rect(0, 0, W, 118, NAVY, None, 0)
    s.scudo(72, 56, "#22c55e", 1.25)
    s.text(118, 56, "scudo-privacy", 36, "#ffffff", 700)
    s.text(118, 90, t["titolo"], 18, "#cbd5e1")
    s.text(1160, 46, "github.com/Sachacata/claude-anonimizzatore", 14, "#94a3b8", 400, "end")

    # 1 · in entrata
    s.sezione(1, 170, t["s1"])
    y = 192
    s.rect(40, y, 340, 258)
    s.text(60, y + 30, t["pc"], 13, GRIGIO, 700, spacing="1.2")
    s.text(60, y + 54, t["pc1"], 15, TESTO, 600)
    s.rect(60, y + 70, 300, 168, "#f8fafc", BORDO, 8, 1)
    for i, r in enumerate(t["veri"]):
        s.text(74, y + 100 + i * 29, r, 15, ROSSO, 600, mono=True)

    s.rect(430, y, 340, 258, "#ecfdf5", VERDE, 14, 2)
    s.scudo(600, y + 50)
    s.text(600, y + 106, t["filtro"], 15, VERDE, 700, "middle", spacing="1.2")
    for i, r in enumerate(t["f1"]):
        s.text(600, y + 136 + i * 25, r, 15, TESTO, 400, "middle")
    s.rect(478, y + 206, 244, 34, VERDE, None, 17)
    s.text(600, y + 228, t["pill1"], 15, "#ffffff", 700, "middle")

    s.rect(820, y, 340, 258, "#eff6ff", "#93c5fd")
    s.text(840, y + 30, t["cloud"], 13, GRIGIO, 700, spacing="1.2")
    s.text(840, y + 54, t["cloud1"], 15, TESTO, 600)
    s.rect(840, y + 70, 300, 168, "#ffffff", BORDO, 8, 1)
    for i, (a, b) in enumerate(t["finti"]):
        s.due(854, y + 100 + i * 29, a, b)
    s.freccia(386, y + 129, 418, y + 129, BLU, "fb")
    s.freccia(776, y + 129, 808, y + 129, BLU, "fb")

    # 2 · in uscita
    s.sezione(2, 500, t["s2"])
    y = 522
    s.rect(820, y, 340, 178, "#eff6ff", "#93c5fd")
    s.text(840, y + 30, t["cloud"], 13, GRIGIO, 700, spacing="1.2")
    s.text(840, y + 54, t["cloud2"], 15, TESTO, 600)
    s.rect(840, y + 72, 300, 54, "#ffffff", BORDO, 8, 1)
    s.due(854, y + 105, t["lettera"], seg("PERS"))

    s.rect(430, y, 340, 178, "#ecfdf5", VERDE, 14, 2)
    s.text(600, y + 32, t["filtro"], 15, VERDE, 700, "middle", spacing="1.2")
    for i, r in enumerate(t["f2"]):
        s.text(600, y + 62 + i * 25, r, 15, TESTO, 400, "middle", mono=(i == 1))
    s.rect(478, y + 122, 244, 34, VERDE, None, 17)
    s.text(600, y + 144, t["pill2"], 15, "#ffffff", 700, "middle")

    s.rect(40, y, 340, 178)
    s.text(60, y + 30, t["pc"], 13, GRIGIO, 700, spacing="1.2")
    s.text(60, y + 54, t["pc2"], 15, TESTO, 600)
    s.rect(60, y + 72, 300, 54, "#f8fafc", BORDO, 8, 1)
    s.due(74, y + 105, t["lettera"], t["nome"], colore=ROSSO)
    s.freccia(814, y + 89, 782, y + 89, VERDE, "fv")
    s.freccia(424, y + 89, 392, y + 89, VERDE, "fv")

    s.rect(40, y + 196, 1120, 46, "#fef2f2", "#fca5a5", 10)
    s.text(600, y + 225, t["fuori"], 15.5, ROSSO, 600, "middle")

    # 3 · regole
    s.sezione(3, 818, t["s3"])
    y = 840
    for i, (a, b, c) in enumerate(t["regole"]):
        x = 40 + i * 380
        s.rect(x, y, 360, 122)
        s.rect(x, y, 8, 122, VERDE, None, 4)
        s.text(x + 26, y + 36, a, 17.5, NAVY, 700)
        s.text(x + 26, y + 68, b, 14.5, GRIGIO)
        s.text(x + 26, y + 92, c, 14.5, GRIGIO)

    # 4 · cosa riconosce
    s.sezione(4, 1012, t["s4"])
    y = 1034
    for i, (a, b) in enumerate(t["tipi"]):
        x, yy = 40 + (i % 4) * 285, y + (i // 4) * 54
        s.rect(x, yy, 265, 42, "#ffffff", BORDO, 21)
        s.text(x + 20, yy + 27, a, 15, BLU, 700, mono=True)
        s.text(x + 84, yy + 27, b, 15, TESTO)

    # 5 · limiti
    s.sezione(5, 1186, t["s5"])
    y = 1208
    s.rect(40, y, 1120, 122, "#fffbeb", "#fcd34d")
    for i, (a, b, c) in enumerate(t["limiti"]):
        x = 66 + i * 372
        s.text(x, y + 36, a, 17, AMBRA, 700)
        s.text(x, y + 68, b, 14.5, TESTO)
        s.text(x, y + 92, c, 14.5, TESTO)

    # 6 · stato
    s.sezione(6, 1380, t["s6"])
    y = 1402
    stili = [("#dcfce7", VERDE), ("#fef3c7", AMBRA), ("#e2e8f0", GRIGIO)]
    for i, (a, b) in enumerate(t["stati"]):
        x = 40 + i * 380
        sfondo, colore = stili[i]
        s.rect(x, y, 360, 70)
        s.rect(x + 16, y + 12, 138, 26, sfondo, None, 13)
        s.text(x + 85, y + 30, a, 14, colore, 700, "middle")
        s.text(x + 18, y + 58, b, 14, GRIGIO)

    s.text(600, 1512, t["piede"], 14, GRIGIO, 400, "middle")
    return s.fine()


if __name__ == "__main__":
    for lingua, t in TESTI.items():
        f = QUI / t["file"]
        f.write_text(disegna(t), encoding="utf-8", newline="\n")
        print("scritto", f.name)
