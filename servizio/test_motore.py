"""Test del motore filtro-pii (unittest, dati inventati). Esegui: py -m unittest test_motore -v"""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from mappa import Mappa  # noqa: E402
from motore import anonimizza, ripristina  # noqa: E402

CF = "BRTGCM80H15L840K"
IBAN = "IT60X0542811101000000123456"  # IBAN d'esempio pubblico, mod-97 valido


class TestRegex(unittest.TestCase):
    def setUp(self):
        self.m = Mappa()

    def round_trip(self, testo, **kw):
        a, n = anonimizza(testo, self.m, **kw)
        r, k = ripristina(a, self.m)
        self.assertEqual(r, testo, f"round trip fallito: {a!r}")
        return a, n

    def test_cf_iban_email_tel(self):
        testo = f"CF {CF}, IBAN {IBAN}, mail giacomo.b@esempio.it, cell. 333 1234567."
        a, n = self.round_trip(testo)
        self.assertEqual(n, 4)
        for tok in ("CF_0001", "IBAN_0001", "EMAIL_0001", "TEL_0001"):
            self.assertIn(tok, a)
        self.assertNotIn(CF, a)
        self.assertNotIn("esempio.it", a)

    def test_iban_non_valido_ignorato(self):
        a, n = anonimizza("IBAN IT60X0542811101000000123457", self.m)
        self.assertEqual(n, 0)

    def test_nome_maiuscolo_registro(self):
        a, n = self.round_trip("101;2026;BERTOLAZZI GIACOMO;accolto")
        self.assertEqual(a, "101;2026;PERS_0001;accolto")

    def test_stessa_persona_grafie_diverse(self):
        a1, _ = anonimizza("BERTOLAZZI GIACOMO", self.m)
        a2, _ = anonimizza("Lettera a Giacomo Bertolazzi (dizionario)", self.m)
        a3, _ = anonimizza(r"dati\Sentenza_101_2026_BERTOLAZZI_GIACOMO.pdf", self.m)
        self.assertEqual(a1, "PERS_0001")
        self.assertIn("PERS_0001b", a2)
        self.assertIn("PERS_0001c", a3)
        self.assertEqual(ripristina(a3, self.m)[0], r"dati\Sentenza_101_2026_BERTOLAZZI_GIACOMO.pdf")
        self.assertEqual(ripristina(a2, self.m)[0], "Lettera a Giacomo Bertolazzi (dizionario)")

    def test_titolo_professionale(self):
        a, n = self.round_trip("rappresentata dall'Avv. Serena Vianello del foro di Vicenza")
        self.assertIn("PERS_0001", a)
        self.assertNotIn("Vianello", a)
        self.assertIn("Vicenza", a)

    def test_blacklist_istituzioni(self):
        testo = "TRIBUNALE ORDINARIO DI VICENZA\nSEZIONE LAVORO\ncontro MINISTERO DELL'ISTRUZIONE E DEL MERITO"
        a, n = anonimizza(testo, self.m)
        self.assertEqual(n, 0)
        self.assertEqual(a, testo)

    def test_esclusi(self):
        a, n = anonimizza("Referente ADA LOVELACE, sede UFFICIO SCOLASTICO, città Vicenza",
                          self.m, esclusi=["Ada Lovelace", "Vicenza", "Ufficio Scolastico"])
        self.assertEqual(n, 0)

    def test_date_udienza_restano_nascita_no(self):
        testo = "udienza del 12/03/2026; ricorrente nata a Padova il 05/06/1980"
        a, n = self.round_trip(testo)
        self.assertIn("12/03/2026", a)
        self.assertIn("NASC_0001", a)
        self.assertNotIn("05/06/1980", a)

    def test_indirizzo(self):
        a, n = self.round_trip("residente in Via Giuseppe Verdi 12, Vicenza; ricorso in via principale")
        self.assertIn("IND_0001", a)
        self.assertIn("in via principale", a)

    def test_nomi_da_contesto(self):
        casi = {
            "sentenza n. 103/2026 – Elvira Cagnotto (codice fiscale CGNLVR76L67L781Z)": "Cagnotto",
            "From: Benedetta Sartorello <benedetta.sartorello@pec.example.com>": "Sartorello",
            "Vicenza, 18/02/2026 Il Giudice Clementina Fornasiero": "Fornasiero",
            "Il Giudice del lavoro Clementina Fornasiero ha deciso": "Fornasiero",
            "Egregio Sig. Ottavio Pasqualotto, con la presente": "Pasqualotto",
            "Gent.le Dott.ssa Marzia Dall'Osto": "Dall'Osto",
            "la ricorrente Annalisa De Boni, rappresentata": "De Boni",
        }
        for testo, cognome in casi.items():
            a, n = self.round_trip(testo)
            self.assertNotIn(cognome, a, testo)
            self.assertIn("PERS_", a, testo)

    def test_indirizzi_con_connettore(self):
        for ind in ("Via dei Tigli 12", "Viale Brigata Marche 3", "Contrà Ognissanti 7", "Via Fontana Vecchia 6", "Piazza dei Signori 1"):
            a, n = self.round_trip(f"residente in {ind}, 36100 Vicenza")
            self.assertIn("IND_", a, ind)
            self.assertNotIn(ind.split()[1], a, ind)
        a, n = anonimizza("procede in via di fatto e nel corso di causa in via principale", self.m)
        self.assertEqual(n, 0, a)

    def test_idempotenza(self):
        testo = f"BERTOLAZZI GIACOMO, {CF}, tel 333 1234567"
        a1, _ = anonimizza(testo, self.m)
        a2, n2 = anonimizza(a1, self.m)
        self.assertEqual(a1, a2)
        self.assertEqual(n2, 0)

    def test_ripristino_tollerante(self):
        anonimizza("BERTOLAZZI GIACOMO", self.m)
        self.assertEqual(ripristina("PERS_1 e PERS_0001 e PERS_00001", self.m)[0],
                         "BERTOLAZZI GIACOMO e BERTOLAZZI GIACOMO e BERTOLAZZI GIACOMO")
        self.assertEqual(ripristina("PERS_0009 sconosciuto, tel 333", self.m)[0], "PERS_0009 sconosciuto, tel 333")

    def test_token_non_riconosciuto_come_telefono(self):
        anonimizza("cell. 333 1234567", self.m)
        a, n = anonimizza("tel 333 1234567 e TEL_0001 già token", self.m)
        self.assertEqual(a, "tel TEL_0001 e TEL_0001 già token")
        self.assertEqual(n, 1)

    def test_dizionario_cognome_solo(self):
        anonimizza("BERTOLAZZI GIACOMO", self.m)
        a, n = anonimizza("il sig. Bertolazzi e poi la Bertolazzi, mai bertolazzi", self.m)
        self.assertEqual(a, "il sig. PERS_0001b e poi la PERS_0001b, mai bertolazzi")
        self.assertEqual(ripristina(a, self.m)[0], "il sig. Bertolazzi e poi la Bertolazzi, mai bertolazzi")

    def test_nome_noto_tutto_minuscolo(self):
        # Persona già vista in due grafie (Title Case e MAIUSCOLO): la grafia
        # tutta minuscola, in entrambi gli ordini, va ritrovata dal dizionario.
        anonimizza("la ricorrente Zanrosso Ofelia, rappresentata", self.m)
        anonimizza("101;2026;ZANROSSO OFELIA;accolto", self.m)
        for testo in ("la collega dice che zanrosso ofelia ha cambiato banca",
                      "ha scritto ofelia zanrosso ieri"):
            a, n = self.round_trip(testo)
            self.assertEqual(n, 1, a)
            self.assertNotIn("zanrosso", a)
            self.assertNotIn("ofelia", a)
            self.assertIn("PERS_", a)

    def test_etichette_grammaticali_non_sono_persone(self):
        a, n = anonimizza("VERB PROPN vett: 0 ner: True\nADJ NOUN vett: 1", self.m)
        self.assertEqual(n, 0, a)

    def test_maiuscole_con_riscontro_restano_persone(self):
        # Campo di registro, riga intera, ruolo o preposizione prima, «nato a» dopo,
        # nome di battesimo dell'elenco: il nominativo MAIUSCOLO va preso.
        for testo in ("101;2026;XHAFERI ARDIAN;accolto",
                      "TRA\nXHAFERI ARDIAN\nE\nMINISTERO DELL'ISTRUZIONE E DEL MERITO",
                      "il ricorso di XHAFERI ARDIAN va accolto",
                      "XHAFERI ARDIAN, nato a Tirana, chiede il pagamento",
                      "ha chiamato TESSAROLO GINEVRA per la pratica"):
            m = Mappa()
            a, n = anonimizza(testo, m)
            self.assertEqual(n, 1, a)
            self.assertNotIn("XHAFERI", a)
            self.assertNotIn("TESSAROLO", a)
            self.assertEqual(ripristina(a, m)[0], testo)

    def test_nome_condiviso_ha_un_token_suo(self):
        anonimizza("BIANCHINI MARIA e MARIA VERDINI", self.m)
        a, n = anonimizza("ha parlato Maria; poi Verdini", self.m)
        self.assertNotIn("Maria;", a)       # nome di due persone note: token a sé
        self.assertIn("PERS_" + "0003;", a)
        self.assertIn("PERS_0002", a)       # «Verdini» appartiene a una sola persona
        self.assertNotIn("Verdini", a)


class TestFugheGiro9(unittest.TestCase):
    """Forme di testo in cui il 10/11/2026 erano rimasti nomi in chiaro
    (nomi inventati)."""
    CF = "RSSMRA80A01H501U"

    @classmethod
    def setUpClass(cls):
        try:
            from motore import carica_nlp
            cls.nlp = carica_nlp()
        except Exception:
            cls.nlp = None

    def passa(self, testo, m=None):
        m = m if m is not None else Mappa()
        a, _ = anonimizza(testo, m, nlp=self.nlp)
        self.assertEqual(ripristina(a, m)[0], testo)
        return a

    def test_cartella_collettiva_e_altri(self):
        a = self.passa(r"lavorati\Sentenza_867_2026_03_11_2026_04_11_2026_16687_ZANFARDIN_CARLO_ENRICO_E_ALTRI_3")
        for p in ("ZANFARDIN", "CARLO", "ENRICO"):
            self.assertNotIn(p, a)
        self.assertIn("_E_ALTRI_3", a)

    def test_cartella_cognome_con_particella_e_due_nomi(self):
        a = self.passa("Sentenza_881_2026_02_11_2026_04_11_2026_16707_DI_ZORDANEL_PIERLUIGI_CESARE no ricorso")
        for p in ("ZORDANEL", "PIERLUIGI", "CESARE", "DI_"):
            self.assertNotIn(p, a)
        self.assertIn(" no ricorso", a)

    def test_tabella_con_barre_e_spazi(self):
        a = self.passa("11 | 853 | 02_11_2026 | 2023/2024 | 2 | 1000 | QUARZENTI GINEVRA | " + self.CF)
        self.assertNotIn("QUARZENTI", a)
        self.assertNotIn("GINEVRA", a)

    def test_celle_vicine_al_codice_fiscale(self):
        for testo in ("3;823;20_10_2026;2;1000;;ROSA;MORO;" + self.CF,
                      "(4, 'Tribunale', '823', None, 'BIANCA', 'ZORDANEL', '" + self.CF + "')",
                      self.CF + "\tMoro\tRosa\t2 voucher"):
            a = self.passa(testo)
            for p in ("ROSA", "MORO", "BIANCA", "ZORDANEL", "Moro", "Rosa"):
                self.assertNotIn(p, a, testo)

    def test_terzo_nome_accanto_a_persona_nota(self):
        m = Mappa()
        self.passa("ZORDANEL PIERLUIGI, nato a Thiene", m)
        a = self.passa("il fascicolo ZORDANEL PIERLUIGI CESARE resta in carico", m)
        self.assertNotIn("CESARE", a)

    def test_cognome_di_due_persone_note(self):
        m = Mappa()
        self.passa("Ginevra Quarzenti, nata a Schio", m)
        self.passa("Ornella Quarzenti, nata a Schio", m)
        a = self.passa("resta da pagare Quarzenti, poi si chiude", m)
        self.assertNotIn("Quarzenti", a)

    def test_due_parole_su_tre_di_persona_nota(self):
        m = Mappa()
        t1 = self.passa("ZANFARDIN CARLO ENRICO, nato a Schio", m)
        a = self.passa("ha telefonato Carlo Zanfardin", m)
        self.assertNotIn("Zanfardin", a)
        self.assertEqual(a.split()[-1][:9], t1.split(",")[0][:9])  # stessa persona, stesso numero

    def test_parola_nota_attaccata_a_cifre(self):
        m = Mappa()
        self.passa("ZANF ARDIN, nato a Schio", m)
        a = self.passa("formato nrg=ZANF0NNNN e file ZANF0NNNN_01.pdf", m)
        self.assertIn("ZANF0NNNN", a)

    def test_cognome_noto_che_e_parola_comune(self):
        if self.nlp is None:
            self.skipTest("serve spaCy")
        m = Mappa()
        self.passa("CARTELLA MARIO, nato a Schio", m)
        a = self.passa("Cartella di lavoro: svuotare la cartella dopo ogni giro.", m)
        self.assertIn("Cartella di lavoro", a)
        a = self.passa("ha telefonato Mario Cartella per la pratica", m)
        self.assertNotIn("Cartella", a)
        # la minuscola dentro un nome di file non fa di un cognome una parola comune
        a = self.passa("- [Cartella 369/2026 fuori giro](folium-cartella-369-2026.md) da pagare", m)
        self.assertNotIn("[Cartella", a)

    def test_formule_degli_atti(self):
        for testo, vietate in (
                ("iscritta al n. 1153 /2026 RG Lav. promossa da: \nZORDANEL’ PIERLUIGI , con l’avv. Tizio", ("ZORDANEL", "PIERLUIGI")),
                ("nella qualità di difensore di   \nZANFARDIN C.F. " + self.CF + ", in forza di procure", ("ZANFARDIN",)),
                ("TRIBUNALE VICENZA 537 / 2026 Causa: Zanfardin c. MIM; RG: 537/2026", ("Zanfardin",)),
                ("resa dal Tribunale di Vicenza Sez. Lavoro - Zanfardin/MIM", ("Zanfardin",))):
            a = self.passa(testo)
            for p in vietate:
                self.assertNotIn(p, a, testo)
        a = self.passa("il ricorso promosso da USR Veneto/MIM non esiste")
        self.assertIn("Veneto/MIM", a)

    def test_capoluogo_da_solo_resta(self):
        m = Mappa()
        self.passa("VERONA MARIO, nato a Schio", m)
        a = self.passa("il fascicolo passa all'UAT Verona", m)
        self.assertIn("Verona", a)


class TestElencoNoti(unittest.TestCase):
    def test_semina_da_excel(self):
        import openpyxl
        from semina import semina_noti
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "registro.xlsx"
            wb = openpyxl.Workbook()
            ws = wb.active
            ws.append(["N. Sentenza", "Nome", "Cognome", "Avvocato"])
            ws.append(["101/2026", "Ofelia", "ZANROSSO", "Avv. Tiberio Quagliarol"])
            ws.append(["102/2026", "Carlo", "Zanfardin", "Quagliarol/Brusaferr"])
            wb.save(f)
            m, visti = Mappa(), {}
            voci = [{"file": "registro.xlsx", "persone": [["Cognome", "Nome"], ["Avvocato"]]}]
            self.assertGreaterEqual(semina_noti(m, Path(d), voci, visti), 3)
            self.assertEqual(semina_noti(m, Path(d), voci, visti), 0)  # file invariato: non si rilegge
            a, n = anonimizza("- [Zanrosso 369/2026 fuori giro] poi Zanfardin/Brusaferr no ricorso", m)
            for p in ("Zanrosso", "Zanfardin", "Brusaferr"):
                self.assertNotIn(p, a)


class TestMappaPersistenza(unittest.TestCase):
    def test_salva_cifrata_e_ricarica(self):
        from cryptography.fernet import Fernet
        chiave = Fernet.generate_key()
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / ".filtro-pii" / "mappa.json"
            m = Mappa(p, chiave)
            a, _ = anonimizza(f"BERTOLAZZI GIACOMO {CF}", m)
            m.salva()
            testo_file = p.read_text(encoding="utf-8")
            self.assertNotIn("BERTOLAZZI", testo_file)
            self.assertIn("cifrato", testo_file)
            m2 = Mappa(p, chiave)
            self.assertEqual(ripristina(a, m2)[0], f"BERTOLAZZI GIACOMO {CF}")
            self.assertEqual(m2.conteggi(), {"PERS": 1, "CF": 1})

    def test_varianti_oltre_25(self):
        m = Mappa()
        toks = {m.token("PERS", f"Rossi Mario{' ' * i}") for i in range(30)}
        self.assertEqual(len(toks), 30)
        for t in toks:
            self.assertRegex(t, r"^PERS_0001[a-z]{0,2}$")


class TestSpacy(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            from motore import carica_nlp
            cls.nlp = carica_nlp()
        except Exception as e:  # pragma: no cover
            raise unittest.SkipTest(f"spaCy non disponibile: {e}")

    def test_prosa(self):
        m = Mappa()
        testo = "Il ricorrente Giacomo Bertolazzi ha chiesto il pagamento; il giudice Lucia Favaretto ha accolto."
        a, n = anonimizza(testo, m, nlp=self.nlp)
        self.assertNotIn("Bertolazzi", a)
        self.assertNotIn("Favaretto", a)
        self.assertEqual(ripristina(a, m)[0], testo)

    def test_nome_minuscolo_mai_visto(self):
        # Nominativi tutti minuscoli di persone mai viste: nome dell'elenco +
        # cognome, nei due ordini, anche con particella o cognome «parola comune».
        casi = {
            "ha chiamato bortolan ginevra per la pratica": ("bortolan", "ginevra"),
            "ieri ginevra bortolan ha scritto": ("bortolan", "ginevra"),
            "ieri ha telefonato tessarolo ginevra per il sollecito": ("tessarolo", "ginevra"),
            "ornella de luca chiede copia": ("ornella", "luca"),
            "il ricorrente rossi mario ha vinto": ("rossi", "mario"),
            "pagare a zanrosso ofelia entro lunedì": ("zanrosso", "ofelia"),
        }
        for testo, parole in casi.items():
            m = Mappa()
            a, n = anonimizza(testo, m, nlp=self.nlp)
            self.assertEqual(n, 1, a)
            for p in parole:
                self.assertNotIn(p, a, testo)
            self.assertEqual(ripristina(a, m)[0], testo)

    def test_nome_minuscolo_senza_cognome_resta(self):
        # Un nome accanto a un verbo, un avverbio o un aggettivo non è un nominativo.
        for testo in ("paolo arriva domani", "ha chiamato marco ieri sera",
                      "una rosa rossa sul tavolo", "sergio lavora a vicenza",
                      "il franco svizzero sale", "grazie mille, sara contenta"):
            a, n = anonimizza(testo, Mappa(), nlp=self.nlp)
            self.assertEqual(n, 0, a)

    def test_maiuscole_in_prosa_con_spacy(self):
        # Senza indizi nel contesto: una parola fuori vocabolario basta (cognome
        # raro o straniero); sole parole del vocabolario sono testo tecnico.
        m = Mappa()
        testo = "ieri ha chiamato XHAFERI ARDIAN in ufficio"
        a, n = anonimizza(testo, m, nlp=self.nlp)
        self.assertNotIn("XHAFERI", a)
        self.assertEqual(ripristina(a, m)[0], testo)
        for testo in ("the file is READ ONLY in this mode",
                      "HEAD REQUEST failed with STATUS CODE 404",
                      "colonne: CODICE MECCANOGRAFICO e DENOMINAZIONE SCUOLA nel foglio"):
            a, n = anonimizza(testo, Mappa(), nlp=self.nlp)
            self.assertEqual(n, 0, a)

    def test_coppie_con_maiuscola_e_nome_in_elenco(self):
        # Cognome + nome (o nome + COGNOME) che le altre regole a volte mancano.
        casi = {
            "Invito al pagamento - Sentenza n°369-2026 Bortolan Ginevra": ("Bortolan", "Ginevra"),
            "Oggetto: Re: Comunicazione Ofelia Zanrosso": ("Ofelia", "Zanrosso"),
            "in fondo alla pagina                Ginevra TESSAROLO": ("Ginevra", "TESSAROLO"),
            "#XYZ_Nominato OFELIA ZANROSSO_TL#": ("OFELIA", "ZANROSSO"),
            "File di Stocchero Mirco - Ufficio Contenzioso": ("Stocchero", "Mirco"),
            "ha scritto Blerina Krasniqi della segreteria": ("Blerina", "Krasniqi"),
            "in calce                Ginevra Martini1": ("Ginevra", "Martini"),
            "Nome: Documento - Fontana Lidia.pdf, Note: allegato": ("Fontana", "Lidia"),
        }
        for testo, parole in casi.items():
            m = Mappa()
            a, n = anonimizza(testo, m, nlp=self.nlp)
            for p in parole:
                self.assertNotIn(p, a, testo)
            self.assertEqual(ripristina(a, m)[0], testo)
        # una parola comune con la maiuscola accanto al nome non fa un nominativo
        for testo in ("Ciao Mirco, ti scrivo per la pratica", "Comunicazione Ofelia del 3 marzo"):
            a, n = anonimizza(testo, Mappa(), nlp=self.nlp)
            self.assertEqual(n, 0, a)

    def test_nomi_in_campi_separati(self):
        casi = {
            "853;02_11_2026;2;1000;;GINEVRA;TESSAROLO;ABC": ("GINEVRA", "TESSAROLO"),
            '{\n    "nome": "OFELIA",\n    "cognome": "ZANROSSO",\n    "importo": 500\n}': ("OFELIA", "ZANROSSO"),
            '{\n    "nome": "SARA",\n    "cognome": "FONTANA"\n}': ("SARA", "FONTANA"),
            "<prot:Cognome>Stocchero</prot:Cognome><prot:Nome>Mirco</prot:Nome>": ("Stocchero", "Mirco"),
            "Cognome e nome: Pozzan Lidia\nImporto: 500": ("Pozzan", "Lidia"),
        }
        for testo, parole in casi.items():
            m = Mappa()
            a, n = anonimizza(testo, m, nlp=self.nlp)
            for p in parole:
                self.assertNotIn(p, a, testo)
            self.assertEqual(ripristina(a, m)[0], testo)
        # cognome da solo dopo un indizio, se fuori dal vocabolario
        for testo in ('"sentenza_file": "Vicenza.Sentenza Tessarolo.813.2026 carta1.pdf"',
                      "sollecito spese sent. 632/2026 Zanrosso (bonus già pagato)",
                      "prorogato al DS Stocchero l'incarico di reggenza"):
            m = Mappa()
            a, n = anonimizza(testo, m, nlp=self.nlp)
            self.assertEqual(n, 1, a)
            self.assertEqual(ripristina(a, m)[0], testo)
        a, n = anonimizza("la Sentenza Tribunale di Vicenza n. 12", Mappa(), nlp=self.nlp)
        self.assertEqual(n, 0, a)
        # intestazioni e campi tecnici restano
        for testo in ("Cognome;Nome;Codice fiscale;Importo", "Nome: Documento - relata.pdf, Note: allegato",
                      '"nome_file": "sentenza.pdf"', "VIIC85700V;ISTITUTO COMPRENSIVO;SCHIO;4"):
            a, n = anonimizza(testo, Mappa(), nlp=self.nlp)
            self.assertEqual(n, 0, a)

    def test_nome_minuscolo_senza_spacy_non_scatta(self):
        a, n = anonimizza("ha chiamato bortolan ginevra", Mappa())
        self.assertEqual(n, 0, a)

    def test_claude_non_mascherato(self):
        m = Mappa()
        a, n = anonimizza("Claude legge il file con Python e Outlook.", m, nlp=self.nlp)
        self.assertEqual(n, 0, a)



class TestConnettivi(unittest.TestCase):
    """16/11/2026: «Nome Cognome Contro Ministero» finiva in un solo token."""

    @classmethod
    def setUpClass(cls):
        from motore import carica_nlp
        cls.nlp = carica_nlp()

    def test_connettivo_fuori_dal_nominativo(self):
        for nome in ("Santoro Michele", "Marchetti Luisa", "Fontana Giorgio"):
            for coda in ("Contro Ministero", "contro Ministero dell'Istruzione", "Avverso Ministero", "c/ MIM"):
                for testa in ("", "Avv. ", '"avvocato": "'):
                    testo = f"{testa}{nome} {coda}"
                    m = Mappa()
                    a, n = anonimizza(testo, m, nlp=self.nlp)
                    self.assertEqual(n, 1, a)
                    self.assertIn(coda, a, a)
                    self.assertNotIn(nome.split()[0], a, a)
                    self.assertEqual(ripristina(a, m)[0], testo)

    def test_connettivo_in_testa(self):
        m = Mappa()
        a, n = anonimizza("Contro Santoro Michele", m, nlp=self.nlp)
        self.assertTrue(a.startswith("Contro "), a)
        self.assertEqual(ripristina(a, m)[0], "Contro Santoro Michele")


if __name__ == "__main__":
    unittest.main(verbosity=2)
