"""
motore.py — nucleo del filtro-pii.

Trova dati personali in un testo e li sostituisce con token stabili
(PERS_0001, CF_0002, IBAN_0003b…) e, al contrario, rimette i dati reali al
posto dei token. Nessuna interfaccia: lo usano servizio.py, ripristina_file.py
e i test. spaCy è opzionale: senza, lavorano solo le regex e il dizionario
delle entità già note.

Token: <TIPO>_<nnnn><variante>. L'id identifica l'entità (stesso id per
«Ginevra Quarzenti», «GINEVRA QUARZENTI», «ROSSI_MARIO»); la variante (nessuna, poi b, c…)
ricorda la grafia esatta, così il ripristino restituisce il testo originale
carattere per carattere (indispensabile per Edit.old_string).
"""
from __future__ import annotations

import re
from typing import Iterable

from mappa import Mappa, TIPI, RE_TOKEN
from nomi_battesimo import NOMI_CERTI, NOMI_AMBIGUI, PARTICELLE, PAROLE_COMUNI, CAPOLUOGHI

try:  # parole vuote dell'italiano: si importano anche senza il modello
    from spacy.lang.it.stop_words import STOP_WORDS as _STOP_IT
except Exception:  # spaCy assente
    _STOP_IT = frozenset()

# ──────────────────────────────────────────────────────────────────────────────
# Regex strutturate
# ──────────────────────────────────────────────────────────────────────────────

_OMO = "[0-9LMNPQRSTUV]"
RE_CF = re.compile(
    rf"\b[A-Z]{{6}}{_OMO}{{2}}[ABCDEHLMPRST]{_OMO}{{2}}[A-Z]{_OMO}{{3}}[A-Z]\b"
)
RE_IBAN = re.compile(r"\bIT\s?\d{2}\s?[A-Z]\s?(?:\d\s?){10}(?:[0-9A-Z]\s?){11}[0-9A-Z]\b")
RE_EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b")
RE_TEL = re.compile(r"(?:\+39[\s.-]?|\b)3\d{2}[\s.-]?\d{3}[\s.-]?\d{3,4}\b")
RE_CARTA = re.compile(r"\b(?:\d{4}[ -]){3}\d{4}\b")
_MESI = "gennaio|febbraio|marzo|aprile|maggio|giugno|luglio|agosto|settembre|ottobre|novembre|dicembre"
RE_NASC = re.compile(
    rf"\bnat[oa]\b[^\n]{{0,80}}?\bil\s+(\d{{1,2}}[/.\-]\d{{1,2}}[/.\-]\d{{2,4}}|\d{{1,2}}°?\s+(?:{_MESI})\s+\d{{4}})",
    re.IGNORECASE,
)
_CONNETTORI = r"(?i:di|del|della|dell'|delle|dei|degli|d'|e)"
RE_ADDRESS = re.compile(
    r"\b((?i:via|viale|corso|piazza|piazzale|largo|vicolo|strada|contrada|contrà|"
    r"localit[àa]|fraz\.?|frazione|borgo|salita|lungomare)\s+"
    # Locuzioni giuridiche/comuni («in via principale», «nel corso di») escluse.
    r"(?!(?i:principale|subordinata|breve|equitativa|giudiziale|"
    r"cautelare|monitoria|esclusiva|analogica|ordinaria|generale|"
    r"preliminare|definitiva|amministrativa|telematica|interpretativa|"
    r"ufficiale|straordinaria|prioritaria|autonoma|incidentale)\b)"
    # «Via dei Tigli»: connettore ammesso solo se segue una Maiuscola.
    r"(?:" + _CONNETTORI + r"\s+(?=[A-ZÀ-Þ]))?"
    r"[A-ZÀ-ÖØ-Þ][\w'\.À-ÿ]*"
    r"(?:\s+(?:" + _CONNETTORI + r"\s+)?[A-ZÀ-Þ][\w'\.À-ÿ]{1,20}){0,3}"
    r"(?:\s*,?\s*(?:n\.?\s*)?\d{1,4}[\/\-]?[A-Za-z]?)?)"
)

_NOME_TC = r"[A-ZÀ-Þ][a-zà-ÿ']+(?:[ \t]+(?:[Dd][aeio]'?[ \t]+|[Dd]ell?'?[ \t]*)?[A-ZÀ-Þ][a-zà-ÿ']+){1,2}"
# Nome in Title Case seguito da ciò che segue un nominativo negli atti:
# «Ginevra Cagnotto (codice fiscale…», «Ginevra Quarzenti, nato a…», «…, residente in».
RE_NAME_BEFORE = re.compile(
    r"\b(" + _NOME_TC + r")(?=\s*[,(]?\s*(?:codice fiscale|C\.?F\.?\s|CF\s|nat[oa]\s|residente|rappresentat[oa]|"
    r"domiciliat[oa]|in persona|elettivamente|difes[oa]|assistit[oa]))"
)
# Nome prima di un indirizzo email tra parentesi angolari: «From: Nome Cognome <…@…>».
RE_NAME_EMAIL = re.compile(r"\b(" + _NOME_TC + r")(?=\s*<[^<>\s]+@)")
# Nome dopo un ruolo scritto per intero: «Il Giudice Clementina Fornasiero».
RE_ROLE_NAME = re.compile(
    r"\b(?:[Gg]iudice|[Pp]residente|[Cc]ancellier[ea]|[Dd]irigente|[Dd]irettor[ea]|[Dd]irettrice|"
    r"[Ff]unzionari[oa]|[Ss]ignor[ae]?|[Ss]ignorina|[Dd]ottor[ea]|[Dd]ottoressa|[Aa]vvocat[oa]|"
    r"[Pp]rofessor[ae]|[Pp]rofessoressa|[Rr]icorrente|[Rr]esistente|[Ii]ngegner[ea]|[Ii]struttore|"
    r"[Rr]elatore|[Rr]elatrice|[Cc]onsiglier[ea]|[Ss]egretari[oa])"
    r"(?:\s+(?:del\s+lavoro|onorario|estensore|unico|designato|dott\.?|avv\.?))*\s+(" + _NOME_TC + r")"
)

# Nomi delle parti nelle sentenze e nei registri: 2-4 parole TUTTE MAIUSCOLE.
RE_UPPER_NAME = re.compile(
    r"\b([A-ZÀ-Þ][A-ZÀ-Þ']{1,}(?:[ \t]+[A-ZÀ-Þ][A-ZÀ-Þ']{1,}){1,3})\b"
)
# Nome dopo un titolo (Avv. Serena Vianello, Dott.ssa …).
RE_TITLED_NAME = re.compile(
    r"\b(?:[Aa]vv|[Dd]ott|[Pp]rof|[Ii]ng|[Dd]r|[Gg]eom|[Rr]ag|[Ss]ig|[Ss]igg|[Ss]ig\.ra|[Ee]gr|[Gg]ent|[Gg]ent\.le|[Gg]entile|[Ee]gregi[oa]|[Ss]pett|[Ss]pett\.le)"
    r"\.?[ \t]*(?:ti|ssa|sa|ri|ra|na|mo|ma|le)?\.?[ \t]+(?:[Ss]ig\.?(?:ra|na)?\.?[ \t]+|[Dd]ott\.?(?:ssa)?\.?[ \t]+|[Aa]vv\.?[ \t]+)?"
    r"([A-ZÀ-Þ][\wà-ÿ']+(?:[ \t]+[A-ZÀ-Þ][\wà-ÿ']+){0,2})"
)
# COGNOME_NOME dentro i nomi di file (Sentenza_101_2026_BERTOLAZZI_GIACOMO.pdf).
RE_FILE_NAME = re.compile(
    r"(?<=_)([A-ZÀ-Þ][A-ZÀ-Þ']+(?:_(?!E_ALTRI(?![A-Za-z]))[A-ZÀ-Þ][A-ZÀ-Þ']+){1,3})"
    r"(?=\.|_\d|_E_ALTRI(?![A-Za-z])|[^A-Za-z0-9_À-ÿ]|$)"
)

# Parole maiuscole che non sono nomi di persona (sentenze, uffici, codice, log).
UPPER_BLACKLIST = {
    "MINISTERO", "ISTRUZIONE", "MERITO", "TRIBUNALE", "ORDINARIO", "REPUBBLICA",
    "ITALIANA", "ITALIANO", "POPOLO", "NOME", "PARTE", "RICORRENTE", "RESISTENTE",
    "SENTENZA", "VERBALE", "CAUSA", "SEZIONE", "LAVORO", "GIUDICE", "CARTA",
    "DOCENTE", "LEGGE", "DECRETO", "LEGISLATIVO", "DPCM", "ATTESTAZIONE",
    "CONFORMITA", "CONFORMITÀ", "FIRMA", "QUALIFICATA", "FIRMATO", "EMESSO",
    "MODELLO", "SERIAL", "CGUE", "CORTE", "CASSAZIONE", "SUPREMA", "ACCORDO",
    "QUADRO", "DIRETTIVA", "STATO", "UFFICIO", "SCOLASTICO", "REGIONALE",
    "AMBITO", "TERRITORIALE", "USR", "UAT", "MIM", "MIUR", "INPS", "INAIL",
    "DEL", "DELLA", "DELLE", "DEI", "DEGLI", "DELL", "DELLO", "CON", "PER",
    "TRA", "FRA", "NEL", "SUL", "GMT", "CAP", "ATE", "IBAN", "PEC", "GAZZETTA",
    "UFFICIALE", "DISP", "ATT", "LAV", "STUDIO", "ONLUS", "SPA", "SRL", "SNC",
    "RICORSO", "OTTEMPERANZA", "SVOLGIMENTO", "PROCESSO", "MOTIVI", "DECISIONE",
    "FATTO", "DIRITTO", "CONCLUSIONI", "DISPOSITIVO", "SPESE", "LITE",
    "COMPENSATE", "CONDANNA", "ACCOGLIE", "RIGETTA", "DICHIARA", "ORDINANZA",
    "VISTO", "VISTI", "RITENUTO", "CONSIDERATO", "PREMESSO", "OGGETTO",
    "ALLEGATO", "ALLEGATI", "PROT", "PROTOCOLLO", "NOTA", "CIRCOLARE", "AVVISO",
    "GRADUATORIA", "DOCENTI", "ATA", "PERSONALE", "DIRIGENTE", "DIRIGENTI",
    "SCUOLA", "ISTITUTO", "COMPRENSIVO", "LICEO", "PROVINCIA", "COMUNE",
    "REGIONE", "VENETO", "ROMA", "ITALIA", "EURO", "TOTALE", "IMPORTO", "DATA",
    "NUMERO", "ANNO", "CODICE", "FISCALE", "NASCITA", "RESIDENZA", "INDIRIZZO",
    "TELEFONO", "EMAIL", "PDF", "XLSX", "DOCX", "CSV", "TXT", "EML", "README",
    "CLAUDE", "TODO", "NOTE", "OK", "KO", "ID", "URL", "HTTP", "HTTPS", "WWW",
    "JSON", "HTML", "API", "UTF", "ERROR", "WARNING", "INFO", "DEBUG", "TRUE",
    "FALSE", "NULL", "NONE", "SELECT", "FROM", "WHERE", "AND", "OR", "NOT", "IF",
    "ELSE", "FOR", "WHILE", "RETURN", "IMPORT", "DEF", "CLASS", "GET", "POST",
    "PUT", "DELETE", "PATH", "FILE", "FILES", "DIR", "USERS", "WINDOWS",
    "PROGRAM", "APPDATA", "LOCAL", "TEMP", "PERS", "CF", "TEL", "IND", "NASC",
    "SOGEI", "SIDI", "FOLIUM", "AOL", "NOIPA", "RGS", "MEF", "SOP", "RPD",
    "BONUS", "CTU", "VARIE", "QUANTIFICAZIONE", "CONSIGLIO", "ESITO", "UDIENZA",
    "AVVOCATO", "AVVOCATURA", "DISTRETTUALE", "GENERALE", "PRESIDENTE", "DOTT",
    "AVV", "PROF", "SIG", "SIGG", "ING", "CITTÀ", "CITTA", "AMMINISTRAZIONE",
    "PUBBLICA", "ENTE", "AZIENDA", "SOCIETÀ", "SOCIETA", "BANCA", "POSTE",
    # etichette grammaticali e di entità (output di spaCy e simili)
    "VERB", "PROPN", "NOUN", "ADJ", "ADV", "AUX", "ADP", "DET", "PRON", "NUM",
    "CCONJ", "SCONJ", "INTJ", "PUNCT", "SYM", "PART", "ORG", "LOC", "MISC",
    "PERSON", "GPE",
}

# Nomi propri che non vanno mai mascherati (strumenti e software).
# I nomi propri di chi usa il filtro vanno in «esclusi» nel file .filtro-pii.json.
ESCLUSI_GLOBALI = {
    "claude", "claude code", "anthropic", "folium", "outlook", "windows", "excel",
    "word", "python", "github", "google", "gmail", "microsoft", "onedrive",
    "sidi", "sogei", "noipa",
}


def _luhn(numero: str) -> bool:
    cifre = [int(c) for c in numero if c.isdigit()]
    somma = 0
    for i, d in enumerate(reversed(cifre)):
        if i % 2 == 1:
            d = d * 2 - 9 if d * 2 > 9 else d * 2
        somma += d
    return somma % 10 == 0


def _iban_valido(iban: str) -> bool:
    s = re.sub(r"\s", "", iban).upper()
    if len(s) != 27:
        return False
    r = s[4:] + s[:4]
    n = "".join(str(int(c, 36)) for c in r)
    return int(n) % 97 == 1


def _norm_parola(p: str) -> str:
    return p.strip("'.,;:()[]\"").lower()


def _escluso(superficie: str, esclusi: set[str]) -> bool:
    chiave = " ".join(sorted(_norm_parola(p) for p in re.split(r"[\s_]+", superficie) if p))
    if chiave in esclusi:
        return True
    parole = [_norm_parola(p) for p in re.split(r"[\s_]+", superficie) if p]
    # Una sola parola che è anche parola di un escluso (es. il solo cognome).
    return len(parole) == 1 and any(parole[0] in e.split() for e in esclusi)


def _prepara_esclusi(esclusi: Iterable[str]) -> set[str]:
    out = set()
    for e in list(ESCLUSI_GLOBALI) + list(esclusi):
        out.add(" ".join(sorted(_norm_parola(p) for p in e.split() if p)))
    return out


# ──────────────────────────────────────────────────────────────────────────────
# spaCy (opzionale)
# ──────────────────────────────────────────────────────────────────────────────

_NLP = None


def carica_nlp(nome: str = "it_core_news_lg"):
    """Carica il modello spaCy una volta sola (solo tok2vec + ner)."""
    global _NLP
    if _NLP is None:
        import spacy
        _NLP = spacy.load(nome, disable=["parser", "lemmatizer", "attribute_ruler", "morphologizer", "tagger"])
        _NLP.max_length = 2_000_000
    return _NLP


def _entita_spacy(testo: str, nlp) -> list[tuple[int, int, str]]:
    """Persone trovate da spaCy, in due passate (originale e Title Case)."""
    spans: list[tuple[int, int, str]] = []
    if not testo.strip():
        return spans
    doc = nlp(testo)
    for ent in doc.ents:
        if ent.label_ in ("PER", "PERSON"):
            spans.append((ent.start_char, ent.end_char, ent.text))
    if re.search(r"\b[A-ZÀ-Þ]{2,}\b", testo):
        titolato = re.sub(r"\b[A-ZÀ-Þ][A-ZÀ-Þ']{1,}\b", lambda m: m.group(0).title(), testo)
        if len(titolato) == len(testo):
            for ent in nlp(titolato).ents:
                if ent.label_ in ("PER", "PERSON"):
                    spans.append((ent.start_char, ent.end_char, testo[ent.start_char:ent.end_char]))
    return spans


# ──────────────────────────────────────────────────────────────────────────────
# Anonimizzazione
# ──────────────────────────────────────────────────────────────────────────────

_RE_PULISCI_NOME = re.compile(r"^[\s'\"(\[]+|[\s'\",;:.)\]]+$")

# Parole che separano le parti di una causa («Quarzenti Ginevra contro Ministero»,
# «avverso», «c/»): non sono mai un pezzo del nominativo, nemmeno con la
# maiuscola («Quarzenti Ginevra Contro Ministero» nei campi estratti dalle sentenze).
_CONNETTIVI = frozenset({"contro", "avverso", "versus", "vs"})
_RE_CONNETTIVO = re.compile(r"(?i)(?<![A-Za-zÀ-ÿ])(?:contro|avverso|versus|vs\.?|c/)(?![A-Za-zÀ-ÿ])")


def _taglia_connettivo(inizio: int, fine: int, sup: str) -> tuple[int, int, str]:
    """Toglie da un nominativo il connettivo e ciò che lo segue (o, se è in
    testa, il connettivo soltanto)."""
    m = _RE_CONNETTIVO.search(sup)
    if not m:
        return inizio, fine, sup
    if m.start() == 0:
        resto = sup[m.end():]
        taglio = m.end() + (len(resto) - len(resto.lstrip(" 	_:,;-")))
        return _taglia_connettivo(inizio + taglio, fine, sup[taglio:])
    sup = sup[:m.start()].rstrip(" 	_:,;-")
    return inizio, inizio + len(sup), sup


def _pulisci_nome(s: str) -> str:
    return _RE_PULISCI_NOME.sub("", s)


def _nome_plausibile(s: str) -> bool:
    if len(s) < 4 or not re.search(r"[A-Za-zÀ-ÿ]", s):
        return False
    if re.search(r"\d", s):
        return False
    parole = [p for p in re.split(r"[\s_]+", s) if p]
    if not parole or len(parole) > 4:
        return False
    if any(p.strip("'.").upper() in UPPER_BLACKLIST for p in parole):
        return False
    # Deve iniziare con una maiuscola (spaCy a volte prende parole comuni).
    return s[0].isupper()


_RE_TUTTO_MAIUSCOLO = re.compile(r"[A-ZÀ-Þ][A-ZÀ-Þ']+(?:[ \t]+[A-ZÀ-Þ][A-ZÀ-Þ']+){1,3}")
_RE_INDIZIO_PRIMA = re.compile(
    r"(?i)(?:\b(?:avv|dott|prof|ing|dr|geom|rag|sigg?|egr|gent|spett|signor[ae]?|signorina|giudice|"
    r"presidente|cancellier[ea]|ricorrente|resistente|appellante|appellat[oa]|attor[ei]|attrice|"
    r"convenut[oa]|contro|da|di|per)\b[\w.]*|c/)[ \t:]*$"
)
_RE_INDIZIO_DOPO = re.compile(
    r"\s*[,(\-–]?\s*(?:codice fiscale|C\.?F\.?[\s:]|nat[oa]\s|residente|rappresentat[oa]|domiciliat[oa]|"
    r"in persona|elettivamente|difes[oa]|assistit[oa]|contro\b|c/)", re.I
)
_SEPARATORI_CAMPO = ";|\t\n\r"


def _maiuscolo_confermato(testo: str, inizio: int, fine: int, sup: str,
                          da_spacy: list[tuple[int, int]], nlp=None) -> bool:
    """Due-quattro parole tutte MAIUSCOLE separate da spazi valgono come
    persona se c'è un riscontro: un nome di battesimo dell'elenco, un indizio
    nel contesto (titolo, ruolo o preposizione prima; «nato a», «C.F.»… dopo),
    la posizione da campo di registro (tra «;», «|», tabulazioni o da sola
    sulla riga) oppure almeno una parola fuori dal vocabolario di spaCy.
    Senza riscontri e con sole parole del vocabolario è testo tecnico
    («READ ONLY») e sporcherebbe la mappa. Senza spaCy vale sempre.
    Le altre grafie non passano di qui e sono sempre confermate."""
    if not _RE_TUTTO_MAIUSCOLO.fullmatch(sup):
        return True
    if any(p.strip("'").lower() in NOMI_CERTI or p.strip("'").lower() in NOMI_AMBIGUI
           for p in sup.split()):
        return True
    if _RE_INDIZIO_PRIMA.search(testo[max(0, inizio - 40):inizio]):
        return True
    if _RE_INDIZIO_DOPO.match(testo[fine:fine + 40]):
        return True
    sx = inizio == 0 or testo[inizio - 1] in _SEPARATORI_CAMPO
    dx = fine == len(testo) or testo[fine] in _SEPARATORI_CAMPO
    if sx and dx:
        return True
    if nlp is None:
        return True  # senza vocabolario non si può distinguere: meglio mascherare
    # Nessun riscontro: si scarta solo se TUTTE le parole sono del vocabolario
    # («READ ONLY», «STATUS CODE»). Una parola sconosciuta è con ogni
    # probabilità un cognome raro o straniero: nel dubbio si maschera.
    # (La conferma di spaCy qui non conta: sul testo reso Capitalizzato prende
    # per persona anche «Read Only».)
    return any(not nlp.vocab.has_vector(p.strip("'").lower()) for p in sup.split())


def _span_token(testo: str) -> list[tuple[int, int]]:
    return [(m.start(), m.end()) for m in RE_TOKEN.finditer(testo)]


def _sovrappone(a: tuple[int, int], protetti: list[tuple[int, int]]) -> bool:
    return any(a[0] < p[1] and p[0] < a[1] for p in protetti)


def _risolvi_sovrapposizioni(spans):
    spans = sorted(spans, key=lambda x: (x[0], -(x[1] - x[0])))
    out, fine = [], -1
    for s in spans:
        if s[0] >= fine:
            out.append(s)
            fine = s[1]
    return out


# Una parola attaccata a cifre («AAAA0NNNN») non è una parola: il token messo
# al suo posto non si potrebbe più ripristinare.
_RE_PAROLA_NOTA = re.compile(r"(?<![A-Za-zÀ-ÿ0-9])[A-Za-zÀ-ÿ]+(?:'[A-Za-zÀ-ÿ]+)*(?![A-Za-zÀ-ÿ0-9])")
# Non contano le minuscole dentro nomi di file e percorsi («folium-rossi-369.md»).
_RE_MINUSCOLA = re.compile(r"(?<![A-Za-zÀ-ÿ0-9_/\\\-.])[a-zà-ÿ]{4,}(?![A-Za-zÀ-ÿ0-9_/\\\-])")
_RE_SEP_NOTI = re.compile(r"[ \t_]{1,3}|[ \t]*\r?\n[ \t]*")

try:
    from spacy.lang.it.stop_words import STOP_WORDS as _PAROLE_VUOTE
except Exception:  # spaCy assente
    _PAROLE_VUOTE = frozenset()


def _norm_nota(p: str) -> str:
    return p.replace("'", "").lower()


def _regex_altri_noti(mappa: Mappa):
    """Regex delle entità note che non sono persone (indirizzi, email; CF e
    IBAN solo finché sono pochi: hanno comunque la loro regex)."""
    if getattr(mappa, "_rx_altri_versione", -1) != mappa._versione:
        per_tipo: dict[str, list[str]] = {}
        for ent in mappa.dati["entita"].values():
            if ent["tipo"] in ("EMAIL", "CF", "IBAN", "IND"):
                per_tipo.setdefault(ent["tipo"], []).extend(v for v in ent["varianti"].values() if len(v) >= 4)
        pezzi = [re.escape(v) for t in ("IND", "EMAIL") for v in per_tipo.get(t, [])]
        strutturati = [re.escape(v) for t in ("CF", "IBAN") for v in per_tipo.get(t, [])]
        if len(strutturati) <= 500:
            pezzi += strutturati
        if pezzi:
            alt = "|".join(sorted(set(pezzi), key=len, reverse=True))
            mappa._rx_altri = re.compile(r"(?<![\w])(?:" + alt + r")(?![\w])", re.IGNORECASE)
        else:
            mappa._rx_altri = None
        mappa._rx_altri_versione = mappa._versione
    return mappa._rx_altri


def _cerca_noti(testo: str, mappa: Mappa, escl: set[str] | frozenset = frozenset(), nlp=None) -> list[tuple]:
    """Occorrenze di entità già in mappa (anche con grafia diversa).
    Persone: si scorrono le parole del testo e si cercano nell'indice delle
    parole note. Due o più parole vicine della stessa persona valgono in
    qualsiasi ordine e grafia; una parola da sola vale se è scritta con la
    maiuscola (o tutta MAIUSCOLA) ed è lunga almeno 5 lettere (4 se tutta
    maiuscola), anche quando appartiene a più persone note («Maria»).
    Una parola da sola che nello stesso testo compare anche tutta in
    minuscolo ed è nel vocabolario («Cartella… la cartella») è una parola
    comune che coincide con un cognome noto: resta in chiaro.
    Ritorna (inizio, fine, tipo, superficie, id_noto | None)."""
    out: list[tuple] = []
    rx = _regex_altri_noti(mappa)
    if rx is not None:
        for m in rx.finditer(testo):
            tipo = mappa.tipo_di_superficie(m.group(0))
            if tipo and tipo != "PERS":
                out.append((m.start(), m.end(), tipo, m.group(0), None))
    idx = mappa._parole_pers()
    if not idx:
        return out
    ws = [(m.start(), m.end(), m.group(0)) for m in _RE_PAROLA_NOTA.finditer(testo)]
    n, i = len(ws), 0
    minuscole: set[str] | None = None

    def parola_comune(b: str) -> bool:
        nonlocal minuscole
        if nlp is None or b in NOMI_CERTI or b in NOMI_AMBIGUI or not nlp.vocab.has_vector(b):
            return False
        if minuscole is None:
            minuscole = set(_RE_MINUSCOLA.findall(testo))
        return b in minuscole
    while i < n:
        s, e, p = ws[i]
        ids = idx.get(_norm_nota(p))
        if not ids:
            i += 1
            continue
        j, cur = i, ids
        while j + 1 < n and j - i < 4:
            succ = idx.get(_norm_nota(ws[j + 1][2]))
            if not succ or not (cur & succ) or not _RE_SEP_NOTI.fullmatch(testo[ws[j][1]:ws[j + 1][0]]):
                break
            cur = cur & succ
            j += 1
        if j > i:
            gruppo = [w[2] for w in ws[i:j + 1]]
            pesanti = [w for w in gruppo if len(_norm_nota(w)) >= 3 and _norm_nota(w) not in PARTICELLE]
            if len(pesanti) >= 2 or (pesanti and all(w[0].isupper() for w in gruppo)):
                sup = testo[s:ws[j][1]]
                if not _escluso(sup, escl):
                    out.append((s, ws[j][1], "PERS", sup, next(iter(cur)) if len(cur) == 1 else None))
                i = j + 1
                continue
        b = _norm_nota(p)
        maiuscola = p.isupper()
        if (p[0].isupper() and (maiuscola or p[1:] == p[1:].lower())
                and (len(b) >= 5 or (maiuscola and len(b) >= 4))
                and p.upper() not in UPPER_BLACKLIST and b not in PARTICELLE and b not in CAPOLUOGHI
                and (maiuscola or b in NOMI_CERTI or b in NOMI_AMBIGUI
                     or (b not in PAROLE_COMUNI and b not in _PAROLE_VUOTE))
                and not _escluso(p, escl) and not parola_comune(b)):
            out.append((s, e, "PERS", p, next(iter(ids)) if len(ids) == 1 else None))
        i += 1
    return out


_NON_NOMI_VICINI = {"ALTRI", "ALTRE", "ALTRO", "ALTRA", "RICORSO", "SENTENZA", "NO"}


def _estendi_persone(testo: str, scelti: list[tuple], mappa: Mappa, nlp, escl) -> list[tuple]:
    """Allarga una persona già trovata alle parole attaccate (uno spazio o un
    «_») che sono con ogni probabilità un altro pezzo del nominativo: un nome
    di battesimo, una parola di una persona nota, una parola fuori dal
    vocabolario; a sinistra anche la particella con la maiuscola («DI_»,
    «De »). Senza questo restava in chiaro il terzo nome di «COGNOME NOME
    NOME2» o il cognome di «COGNOME_<persona nota>»."""
    idx = mappa._parole_pers()
    tutti = NOMI_CERTI | NOMI_AMBIGUI

    def vale(w: str) -> bool:
        b = _norm_nota(w)
        if len(b) < 3 or not w[0].isupper() or not (w.isupper() or w[1:] == w[1:].lower()):
            return False
        if b in _CONNETTIVI:
            return False
        if w.upper() in UPPER_BLACKLIST or w.upper() in _NON_NOMI_VICINI or _escluso(w, escl):
            return False
        if b in tutti:
            return True
        if b in _PAROLE_VUOTE or b in PAROLE_COMUNI or b in PARTICELLE:
            return False
        if b in idx:
            return True
        return nlp is not None and not nlp.vocab.has_vector(b)

    out: list[tuple] = []
    for k, c in enumerate(scelti):
        inizio, fine, tipo, sup = c[:4]
        if tipo != "PERS":
            out.append(c)
            continue
        limite_sx = out[-1][1] if out else 0
        limite_dx = scelti[k + 1][0] if k + 1 < len(scelti) else len(testo)
        i0, f0 = inizio, fine
        for _ in range(3):
            m = re.match(r"[ _]([A-Za-zÀ-ÿ]+(?:'[A-Za-zÀ-ÿ]+)*)(?![A-Za-zÀ-ÿ0-9])", testo[fine:fine + 40])
            if not m or fine + m.end() > limite_dx or not vale(m.group(1)):
                break
            fine += m.end()
        for _ in range(3):
            pezzo = testo[max(limite_sx, inizio - 40):inizio]
            m = re.search(r"(?<![A-Za-zÀ-ÿ0-9'])([A-Za-zÀ-ÿ]+(?:'[A-Za-zÀ-ÿ]+)*)[ _]$", pezzo)
            if not m:
                break
            w = m.group(1)
            if vale(w):
                inizio -= len(pezzo) - m.start()
                continue
            if _norm_nota(w) in PARTICELLE and w[0].isupper():
                inizio -= len(pezzo) - m.start()
            break
        if (inizio, fine) != (i0, f0):
            out.append((inizio, fine, "PERS", testo[inizio:fine], c[4] if len(c) > 4 else None))
        else:
            out.append(c)
    return out


_NOME_ATTO = r"[A-ZÀ-Þ][A-Za-zÀ-ÿ'’]+(?:[ \t]+(?:[Dd][aeio]'?[ \t]+|[Dd]ell?[ae]?'?[ \t]*)?[A-ZÀ-Þ][A-Za-zÀ-ÿ'’]+){0,3}"
_RE_FORMULE = (
    # «promossa da: ⏎NICOLO’ GINEVRA , con l’avv.», «difensore di ⏎QUARZENTI C.F.», «nell'interesse di …»
    re.compile(r"(?:\bpromoss[ao][ \t]+da|\bdifensore(?:[ \t]+domiciliatario)?[ \t]+d(?:i|el(?:la)?)"
               r"|\bnell[’']interesse[ \t]+d(?:i|el(?:la)?))[ \t]*:?[ \t]*(?:\r?\n[ \t]*)?"
               r"(?:(?:sig|prof|dott)\.?(?:ra|ssa)?\.?[ \t]+)?(" + _NOME_ATTO + r")"),
    # «Causa: Quarzenti c. MIM», «Sez. Lavoro - Quarzenti/MIM», «QUARZENTI GINEVRA c/ Ministero»
    re.compile(r"(?<![A-Za-zÀ-ÿ])(" + _NOME_ATTO + r")[ \t]*(?:c\.|c/|/|contro)[ \t]*"
               r"(?:M\.?I\.?M\b|MIUR\b|M\.?I\.?U\.?R\b|Ministero\b|MINISTERO\b)"),
    # una o più parole MAIUSCOLE subito prima di «C.F.» / «codice fiscale»
    re.compile(r"(?<![A-Za-zÀ-ÿ])([A-ZÀ-Þ][A-ZÀ-Þ'’]{3,}(?:[ \t]+[A-ZÀ-Þ][A-ZÀ-Þ'’]+){0,3})"
               r"[ \t]*[,(]?[ \t]*(?:C\.[ \t]?F\.|(?i:codice[ \t]+fiscale))"),
)


def _nomi_da_formule(testo: str) -> list[tuple[int, int, str]]:
    """Nominativi (anche un cognome solo) retti da una formula tipica degli
    atti e delle PEC di notifica."""
    out = []
    for rx in _RE_FORMULE:
        for m in rx.finditer(testo):
            v = m.group(1)
            parole = [p.strip("'’") for p in v.split()]
            if len(v.replace(" ", "")) < 4 or any(p.upper() in UPPER_BLACKLIST for p in parole):
                continue
            if all(p.lower() in PAROLE_COMUNI or p.lower() in _PAROLE_VUOTE or p.lower() in PARTICELLE for p in parole):
                continue
            out.append((m.start(1), m.end(1), v))
    return out


_RE_SEP_CELLA = re.compile(
    r"[ \t]*[;|\t][ \t]*"                       # ; | tab, anche con spazi intorno
    r"|(?<=['\"])[ \t]*,[ \t]*"                 # 'a', 'b'
    r"|[ \t]*,[ \t]*(?=['\"])"                  # None, 'b'
)
_RE_CELLA_NOME = re.compile(r"[A-ZÀ-Þ][A-Za-zÀ-ÿ']*(?:[ \t]+[A-ZÀ-Þ][A-Za-zÀ-ÿ']*){0,3}")
_RE_CELLA_CF = re.compile(r"(?:(?i:c\.?f\.?|codice fiscale)[ \t]*[:=]?[ \t]*)?" + RE_CF.pattern.replace(r"\b", ""))
_BORDI_CELLA = " \t'\"()[]{}"


def _nomi_in_celle(testo: str, nlp=None) -> list[tuple[int, int, str]]:
    """Nomi in righe a celle (tabelle con «;», « | », tabulazioni, tuple e
    liste stampate da Python). Due regole: 1) le due celle prima e le due dopo
    un codice fiscale, se hanno la forma di un nome; 2) due celle vicine a
    forma di nome quando una contiene un nome di battesimo certo, oppure un
    nome ambiguo e l'altra una parola fuori dal vocabolario, oppure sono
    entrambe tutte MAIUSCOLE e una ha una parola fuori dal vocabolario."""
    tutti = NOMI_CERTI | NOMI_AMBIGUI
    trovati: dict[tuple[int, int], str] = {}

    def forma_nome(v: str) -> bool:
        if not _RE_CELLA_NOME.fullmatch(v) or len(v.replace(" ", "")) < 3:
            return False
        for p in v.split():
            b = p.strip("'").lower()
            if p.strip("'").upper() in UPPER_BLACKLIST:
                return False
            if b not in tutti and (b in PAROLE_COMUNI or b in _PAROLE_VUOTE):
                return False
        return True

    def ha(v: str, insieme) -> bool:
        return any(p.strip("'").lower() in insieme for p in v.split())

    def fuori(v: str) -> bool:
        return nlp is not None and any(not nlp.vocab.has_vector(p.strip("'").lower()) for p in v.split())

    pos = 0
    for riga in testo.splitlines(keepends=True):
        base, pos = pos, pos + len(riga)
        if len(riga) > 4000:
            continue
        seps = list(_RE_SEP_CELLA.finditer(riga))
        if not seps:
            continue
        celle: list[tuple[int, int, str]] = []
        a = 0
        for m in seps + [None]:
            b = m.start() if m else len(riga.rstrip("\r\n"))
            grezza = riga[a:b]
            netta = grezza.strip(_BORDI_CELLA)
            off = grezza.find(netta) if netta else 0
            celle.append((base + a + off, base + a + off + len(netta), netta))
            a = m.end() if m else b
        nomi = [forma_nome(c[2]) for c in celle]
        for i, c in enumerate(celle):
            if _RE_CELLA_CF.fullmatch(c[2]):
                for j in (i - 2, i - 1, i + 1, i + 2):
                    if 0 <= j < len(celle) and nomi[j]:
                        trovati[celle[j][:2]] = celle[j][2]
        for i in range(len(celle) - 1):
            if not (nomi[i] and nomi[i + 1]):
                continue
            x, y = celle[i][2], celle[i + 1][2]
            if (ha(x, NOMI_CERTI) or ha(y, NOMI_CERTI)
                    or (ha(x, tutti) and fuori(y)) or (ha(y, tutti) and fuori(x))
                    or (x.isupper() and y.isupper() and (fuori(x) or fuori(y)))):
                trovati[celle[i][:2]] = x
                trovati[celle[i + 1][:2]] = y
    return [(s, e, v) for (s, e), v in sorted(trovati.items())]


_RE_PAROLA = re.compile(r"[A-Za-zÀ-ÿ]+(?:'[A-Za-zÀ-ÿ]+)*")


def _dintorni(testo: str, inizio: int, fine: int) -> tuple[int, int]:
    """Riga che contiene [inizio, fine), al più 200 caratteri per lato."""
    a = max(testo.rfind("\n", 0, inizio) + 1, inizio - 200)
    b = testo.find("\n", fine)
    return a, min(len(testo) if b < 0 else b, fine + 200)


def _pos_parola(testo: str, inizio: int, nlp, cache: dict | None = None) -> str | None:
    """Categoria grammaticale (VERB, PROPN…) della parola che inizia a `inizio`,
    letta nel testo così com'è. I componenti si chiamano direttamente, senza
    toccare la pipeline condivisa (il morphologizer è caricato ma disattivato)."""
    a, b = _dintorni(testo, inizio, inizio + 1)
    doc = cache.get((a, b)) if cache is not None else None
    if doc is None:
        try:
            doc = nlp.make_doc(testo[a:b])
            for nome in ("tok2vec", "morphologizer"):
                doc = nlp.get_pipe(nome)(doc)
        except Exception:
            return None
        if cache is not None:
            cache[(a, b)] = doc
    for tok in doc:
        if tok.idx <= inizio - a < tok.idx + len(tok.text):
            return tok.pos_ or None
    return None


def _conferma_ner(testo: str, parole: list[tuple[int, int]], nlp) -> bool:
    """True se spaCy, con le parole rese Capitalizzate, vede lì una persona."""
    inizio, fine = parole[0][0], parole[-1][1]
    a, b = _dintorni(testo, inizio, fine)
    pezzo = list(testo[a:b])
    for s, e in parole:
        cap = testo[s:e].capitalize()
        if len(cap) != e - s:
            return False
        pezzo[s - a:e - a] = cap
    for ent in nlp("".join(pezzo)).ents:
        if ent.label_ in ("PER", "PERSON") and ent.start_char <= inizio - a and ent.end_char >= fine - a:
            return True
    return False


def _nomi_minuscoli(testo: str, nlp=None) -> list[tuple[int, int, str]]:
    """Nominativi scritti (in tutto o in parte) in minuscolo: un nome di
    battesimo dell'elenco accanto a un probabile cognome, in qualsiasi ordine,
    anche con particella («de», «dalla»). Serve spaCy (senza, nessun
    risultato): la coppia vale se spaCy legge il cognome come nome proprio,
    oppure se il nome non è ambiguo, il cognome è letto come nome o aggettivo
    e non è una parola del vocabolario o la NER conferma la persona."""
    if nlp is None:
        return []
    parole = [(m.start(), m.end(), m.group(0)) for m in _RE_PAROLA.finditer(testo)]
    tutti = NOMI_CERTI | NOMI_AMBIGUI
    trovati: set[tuple[int, int]] = set()

    def attaccate(i: int, j: int) -> bool:
        tra = testo[parole[i][1]:parole[j][0]]
        return bool(tra) and not tra.strip(" \t")

    def cognome_possibile(p: str) -> bool:
        b = p.lower()
        return (len(b) >= 3 and b not in PAROLE_COMUNI and b not in PARTICELLE
                and b not in _STOP_IT and p.upper() not in UPPER_BLACKLIST)

    def valuta(idx: list[int], i_nome: int, i_cogn: int):
        nome, cogn = parole[i_nome][2], parole[i_cogn][2]
        if not cognome_possibile(cogn):
            return
        b = cogn.lower()
        certo = nome.lower() in NOMI_CERTI
        pos = _pos_parola(testo, parole[i_cogn][0], nlp, cache_pos)
        if nome[0].isupper() and cogn[0].isupper():
            # Entrambe con la maiuscola («Bortolan Ginevra», «Ginevra BORTOLAN»):
            # le altre regole a volte le mancano. Vale se l'altra parola è
            # fuori dal vocabolario, è anch'essa un nome certo, oppure (con
            # nome certo) spaCy la legge come nome proprio. «Comunicazione
            # Sonia», «Gentile Sara», «Ciao Marco» restano fuori.
            if b in tutti:
                ok = certo and b in NOMI_CERTI
            elif not nlp.vocab.has_vector(b):
                ok = True
            elif not certo:
                ok = False
            elif i_cogn > i_nome:
                ok = True  # «Ginevra Quarzenti»: dopo un nome certo, una maiuscola è un cognome
            else:
                # «Quarzenti Ginevra»: vale se non è la prima parola della frase
                # (lì la maiuscola non dice nulla: «Comunicazione Ginevra»).
                prima = testo[:parole[idx[0]][0]].rstrip(" \t")
                ok = pos == "PROPN" or not (not prima or prima[-1] in "\n\r.:;!?\"'«“”(>")
        elif pos == "PROPN":
            ok = True  # spaCy lo legge già come nome proprio
        elif not certo:
            ok = False  # «rosa rossa», «viola intenso»: troppo incerto
        else:
            nominale = pos in ("NOUN", "ADJ", "X")
            fuori_vocabolario = b not in tutti and not nlp.vocab.has_vector(b)
            if fuori_vocabolario and nominale:
                ok = True
            elif fuori_vocabolario or nominale:
                # Parola sconosciuta letta come verbo (la categoria è tirata a
                # indovinare) oppure parola comune letta come nome: decide la NER.
                ok = _conferma_ner(testo, [(parole[k][0], parole[k][1]) for k in idx], nlp)
            else:
                ok = False  # verbo o avverbio del vocabolario: «paolo arriva», «marco ieri»
        if ok:
            trovati.add((parole[idx[0]][0], parole[idx[-1]][1]))
            accettati.append(idx)

    cache_pos: dict = {}
    accettati: list[list[int]] = []
    n = len(parole)
    for i, (_, _, p) in enumerate(parole):
        if p.lower() not in tutti:
            continue
        # nome [particella] cognome
        if i + 1 < n and attaccate(i, i + 1):
            if parole[i + 1][2].lower() in PARTICELLE and i + 2 < n and attaccate(i + 1, i + 2):
                valuta([i, i + 1, i + 2], i, i + 2)
            else:
                valuta([i, i + 1], i, i + 1)
        # [particella] cognome nome
        if i >= 1 and attaccate(i - 1, i):
            if i >= 2 and parole[i - 2][2].lower() in PARTICELLE and attaccate(i - 2, i - 1):
                valuta([i - 2, i - 1, i], i, i - 1)
            else:
                valuta([i - 1, i], i, i - 1)
    # «Cognome Nome Cognome2»: se valgono sia la coppia a sinistra sia quella a
    # destra dello stesso nome, si prende tutto (altrimenti resterebbe fuori un pezzo).
    for a in accettati:
        for b in accettati:
            if a is not b and a[-1] == b[0] and len(a) + len(b) <= 5:
                trovati.add((parole[a[0]][0], parole[b[-1]][1]))
    # Due parole con la maiuscola entrambe fuori dal vocabolario («Blerina
    # Krasniqi»): nominativo con nome non in elenco. Le coppie tutte
    # MAIUSCOLE hanno già la loro regola.
    for i in range(n - 1):
        a, b = parole[i][2], parole[i + 1][2]
        if (len(a) < 4 or len(b) < 4 or (a.isupper() and b.isupper())
                or not _RE_FORMA_NOME.fullmatch(a) or not _RE_FORMA_NOME.fullmatch(b)
                or not attaccate(i, i + 1)
                or a.upper() in UPPER_BLACKLIST or b.upper() in UPPER_BLACKLIST):
            continue
        if not nlp.vocab.has_vector(a.lower()) and not nlp.vocab.has_vector(b.lower()):
            trovati.add((parole[i][0], parole[i + 1][1]))
    return [(s, e, testo[s:e]) for s, e in sorted(trovati)]


_RE_FORMA_NOME = re.compile(r"[A-ZÀ-Þ][a-zà-ÿ']+|[A-ZÀ-Þ][A-ZÀ-Þ']+")
_RE_FORMA_CAMPO = r"[A-ZÀ-Þ][A-Za-zÀ-ÿ']*(?:[ \t]+[A-ZÀ-Þ][A-Za-zÀ-ÿ']*){0,2}"
# «"cognome": "QUARZENTI"», «Nome: Ginevra», «<prot:Cognome>Quarzenti</prot:Cognome>».
_RE_CAMPO_ETICHETTA = re.compile(
    r"(?<![A-Za-zÀ-ÿ_])(?i:cognome|nome|nominativo)[\"']?[ \t]*[:=>][ \t]*[\"']?"
    r"(" + _RE_FORMA_CAMPO + r")(?=[ \t]*(?:[\"'<;,\r\n]|$))"
)
# Due celle vicine di una tabella («;GINEVRA;BORTOLAN;»), ciascuna di 1-3 parole.
_RE_DUE_CELLE = re.compile(
    r"(?<=[;|\t])(" + _RE_FORMA_CAMPO + r")[;|\t](?=(" + _RE_FORMA_CAMPO + r")(?:[;|\t\r\n]|$))"
)


def _nomi_in_campi(testo: str, nlp=None) -> list[tuple[int, int, str]]:
    """Nomi e cognomi tenuti in campi separati: valore di un'etichetta
    «nome»/«cognome» (JSON, XML, moduli) e celle vicine di una tabella in cui
    una contiene un nome di battesimo. Ogni campo è una voce a sé."""
    tutti = NOMI_CERTI | NOMI_AMBIGUI
    trovati: dict[tuple[int, int], str] = {}

    def pulita(v: str) -> bool:
        ps = [p.strip("'") for p in v.split()]
        return (len(v.replace(" ", "")) >= 3
                and not any(p.upper() in UPPER_BLACKLIST
                            or (p.lower() not in tutti
                                and (p.lower() in PAROLE_COMUNI or p.lower() in _STOP_IT))
                            for p in ps))

    def ha_nome(v: str, insieme) -> bool:
        return any(p.strip("'").lower() in insieme for p in v.split())

    def fuori_vocabolario(v: str) -> bool:
        return nlp is not None and any(not nlp.vocab.has_vector(p.strip("'").lower()) for p in v.split())

    for m in _RE_CAMPO_ETICHETTA.finditer(testo):
        if pulita(m.group(1)):
            trovati[(m.start(1), m.end(1))] = m.group(1)
    for m in _RE_DUE_CELLE.finditer(testo):
        a, b = m.group(1), m.group(2)
        if not (pulita(a) and pulita(b)):
            continue
        # Nome certo in una delle due; con un nome ambiguo («ROSA», «FRANCO»)
        # serve che l'altra cella abbia una parola fuori dal vocabolario.
        ok = ha_nome(a, NOMI_CERTI) or ha_nome(b, NOMI_CERTI) \
            or (ha_nome(a, tutti) and fuori_vocabolario(b)) \
            or (ha_nome(b, tutti) and fuori_vocabolario(a))
        if ok:
            trovati[(m.start(1), m.end(1))] = a
            trovati[(m.start(2), m.end(2))] = b
    # Cognome da solo dopo un indizio («Sentenza Bortolan.813», «sent. 632/2026
    # Bortolan», «DS Bortolan»): vale solo se è fuori dal vocabolario.
    if nlp is not None:
        for m in _RE_COGNOME_DOPO_INDIZIO.finditer(testo):
            v = m.group(1)
            if v.upper() not in UPPER_BLACKLIST and not nlp.vocab.has_vector(v.strip("'").lower()):
                trovati[(m.start(1), m.end(1))] = v
    return [(s, e, v) for (s, e), v in sorted(trovati.items())]


_RE_COGNOME_DOPO_INDIZIO = re.compile(
    r"(?:\b[Ss]entenza|\bsent\.|\b[Rr]icorso|\b[Rr]icorrente|\bDS|\bD\.S\.|\b[Dd]ocente|\bins\.)"
    r"[ \t]+(?:n\.?[ \t]*)?(?:\d+[/.\-]\d{2,4}[ \t]+)?"
    r"([A-ZÀ-Þ][a-zà-ÿ']{3,}|[A-ZÀ-Þ][A-ZÀ-Þ']{3,})(?![A-Za-zÀ-ÿ])"
)


def anonimizza(testo: str, mappa: Mappa, nlp=None, esclusi: Iterable[str] = ()) -> tuple[str, int]:
    """Sostituisce i dati personali con token. Ritorna (testo, n_sostituzioni)."""
    if not testo:
        return testo, 0
    escl = _prepara_esclusi(esclusi)
    protetti = _span_token(testo)
    cand: list[tuple[int, int, str, str]] = []  # (inizio, fine, tipo, superficie)

    def agg(inizio: int, fine: int, tipo: str, sup: str):
        if tipo == "PERS":
            inizio, fine, sup = _taglia_connettivo(inizio, fine, sup)
        if fine <= inizio or not sup.strip():
            return
        # Un token seguito subito da una cifra o da una lettera («Quarzenti1», nota a
        # piè di pagina) non si potrebbe più ripristinare: la coda entra nel dato.
        coda = re.match(r"[A-Za-z0-9]+", testo[fine:fine + 12])
        if coda:
            fine += coda.end()
            sup = testo[inizio:fine]
        if _sovrappone((inizio, fine), protetti):
            return
        cand.append((inizio, fine, tipo, sup))

    for m in RE_CF.finditer(testo):
        agg(m.start(), m.end(), "CF", m.group(0))
    for m in RE_IBAN.finditer(testo):
        if _iban_valido(m.group(0)):
            agg(m.start(), m.end(), "IBAN", m.group(0))
    for m in RE_EMAIL.finditer(testo):
        e = m.group(0)
        if not re.search(r"@(users\.noreply|anthropic)\.", e, re.I) and not _escluso(e, escl):
            agg(m.start(), m.end(), "EMAIL", e)
    for m in RE_TEL.finditer(testo):
        agg(m.start(), m.end(), "TEL", m.group(0))
    for m in RE_CARTA.finditer(testo):
        if _luhn(m.group(0)):
            agg(m.start(), m.end(), "CARTA", m.group(0))
    for m in RE_NASC.finditer(testo):
        agg(m.start(1), m.end(1), "NASC", m.group(1))
    for m in RE_ADDRESS.finditer(testo):
        sup = m.group(0).rstrip(" ,")
        if len(sup) > 8 and not _escluso(sup, escl):
            agg(m.start(), m.start() + len(sup), "IND", sup)

    nomi: list[tuple[int, int, str]] = []
    for m in RE_UPPER_NAME.finditer(testo):
        nomi.append((m.start(1), m.end(1), m.group(1)))
    for m in RE_TITLED_NAME.finditer(testo):
        nomi.append((m.start(1), m.end(1), m.group(1)))
    for m in RE_FILE_NAME.finditer(testo):
        nomi.append((m.start(1), m.end(1), m.group(1)))
    for rx in (RE_NAME_BEFORE, RE_NAME_EMAIL, RE_ROLE_NAME):
        for m in rx.finditer(testo):
            nomi.append((m.start(1), m.end(1), m.group(1)))
    da_spacy: list[tuple[int, int]] = []
    if nlp is not None:
        trovate = _entita_spacy(testo, nlp)
        nomi.extend(trovate)
        da_spacy = [(a, b) for a, b, _ in trovate]
    for inizio, fine, sup in nomi:
        pulito = _pulisci_nome(sup)
        if not pulito:
            continue
        off = sup.find(pulito)
        inizio, fine = inizio + off, inizio + off + len(pulito)
        if (_nome_plausibile(pulito) and not _escluso(pulito, escl)
                and _maiuscolo_confermato(testo, inizio, fine, pulito, da_spacy, nlp)):
            agg(inizio, fine, "PERS", pulito)

    for inizio, fine, sup in (_nomi_minuscoli(testo, nlp) + _nomi_in_campi(testo, nlp)
                             + _nomi_in_celle(testo, nlp) + _nomi_da_formule(testo)):
        if not _escluso(sup, escl):
            agg(inizio, fine, "PERS", sup)

    cand.extend(c for c in _cerca_noti(testo, mappa, escl, nlp) if not _sovrappone((c[0], c[1]), protetti))

    scelti = _risolvi_sovrapposizioni(cand)
    if not scelti:
        return testo, 0
    scelti = _estendi_persone(testo, scelti, mappa, nlp, escl)
    pezzi, pos = [], 0
    for c in scelti:
        inizio, fine, tipo, sup = c[:4]
        pezzi.append(testo[pos:inizio])
        pezzi.append(mappa.token(tipo, sup, c[4] if len(c) > 4 else None))
        pos = fine
    pezzi.append(testo[pos:])
    return "".join(pezzi), len(scelti)


# ──────────────────────────────────────────────────────────────────────────────
# Ripristino
# ──────────────────────────────────────────────────────────────────────────────

def ripristina(testo: str, mappa: Mappa) -> tuple[str, int]:
    """Rimette i dati reali al posto dei token conosciuti. Ritorna (testo, n)."""
    if not testo or mappa.vuota():
        return testo, 0
    n = 0

    def sost(m: re.Match) -> str:
        nonlocal n
        sup = mappa.superficie(m.group(1).upper(), int(m.group(2)), (m.group(3) or "").lower())
        if sup is None:
            return m.group(0)
        n += 1
        return sup

    return RE_TOKEN.sub(sost, testo), n


__all__ = ["anonimizza", "ripristina", "carica_nlp", "Mappa", "TIPI", "RE_TOKEN"]
