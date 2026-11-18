# Limiti noti

Il filtro lavora «al meglio»: nel dubbio maschera, ma non vede tutto. Questo elenco viene dalle prove fatte durante lo sviluppo. Prima di usarlo con dati veri, misura il comportamento sui tuoi documenti con `servizio\misura_a_secco.py`.

## Dati che possono restare in chiaro

| Caso | Esempio (nomi di fantasia) | Rimedio |
|---|---|---|
| Cognome da solo di una persona mai vista, senza indizi intorno | «resta da pagare Quarzenti» | elenco `noti` nella configurazione |
| Nome di battesimo da solo | «ha chiamato Ginevra» | nessuno |
| Nome tutto minuscolo con nome ambiguo e cognome che è una parola comune | «rosa bianchi» | nessuno |
| Nome minuscolo non presente nell'elenco dei nomi di battesimo (stranieri, rari) | «ha scritto dragomir quarzenti» | nessuno |
| Nominativo TUTTO MAIUSCOLO in prosa, fatto solo di parole del vocabolario, senza nome in elenco e senza indizi | due cognomi che sono parole comuni | raro; elenco `noti` |
| Cognome attaccato ad altro testo in un nome di file | `verbalequarzenti.pdf` | nomi di file con separatori |
| CAP e comune | «36061 Bassano del Grappa» | per scelta: i luoghi non sono mascherati |
| Telefoni fissi | «0444 123456» | per scelta: solo i cellulari |
| Date di nascita senza «nato/a … il» | una data in una colonna «Data nascita» | nessuno |
| Testo in lingue diverse dall'italiano | | il modello linguistico è italiano |

Senza spaCy (servizio avviato con `--senza-spacy`, o modello non installato) lavorano solo le espressioni regolari e l'elenco delle persone già note: il riconoscimento dei nomi peggiora molto. `GET /stato` dice quale modello è in uso.

## Canali che il filtro non copre

- **Immagini.** Screenshot, zoom di pagina, scansioni, foto: arrivano al modello come sono. La lettura diretta delle immagini con lo strumento `Read` è negata, ma gli strumenti del browser e del desktop che restituiscono immagini non vengono bloccati. Sulle pagine con dati reali usa solo comandi che restituiscono testo, numeri o sì/no.
- **PDF scansionati e file firmati** (`.p7m`): non hanno testo da estrarre, quindi non sono né letti né filtrati. Servono OCR o estrazione a parte.
- **Allegati al prompt.** In un progetto protetto il prompt con allegati viene fermato.
- **Ciò che è già in conversazione** quando accendi il filtro a metà sessione.
- **Le risposte del modello** non vengono ritoccate: il modello ha visto solo segnaposto, quindi scrive segnaposto. Se però un dato gli è arrivato in chiaro per uno dei casi sopra, lo può ripetere.

## Verso l'esterno i segnaposto restano segnaposto

I segnaposto tornano dati reali solo negli strumenti locali. Ricerche web, connettori (posta, calendario, documenti online) e strumenti MCP ricevono i segnaposto alla lettera. Conseguenze:

- una bozza di posta creata da Claude contiene `PERS_…` al posto dei nomi: fatti salvare il testo in un file locale e incollalo tu;
- una ricerca web su una persona non funziona.

È voluto: è ciò che impedisce ai dati di uscire.

## Falsi positivi

- Parole comuni con la maiuscola, nomi di strumenti, di cartelle, di prodotti o di variabili possono diventare segnaposto persona; spezzoni di testo inglese possono diventare segnaposto indirizzo. Succede soprattutto nei testi tecnici e nelle istruzioni.
- L'output tecnico con parole TUTTE MAIUSCOLE di seguito può far nascere finte persone nella mappa.
- Nomi di scuole, vie e istituti intitolati a persone diventano segnaposto.

Non sono fughe, ma possono rendere ambigue le istruzioni che il modello legge. Rimedi: aggiungere le parole a `esclusi`; azzerare la mappa quando si è sporcata durante le prove.

## Attriti d'uso

- **`Edit` in modalità automatica.** Quando l'input di `Edit` contiene un segnaposto, la mod lo rimette in chiaro dopo il controllo della modalità automatica, che allora rifiuta la chiamata. Serve l'approvazione a mano, oppure modificare porzioni di testo senza nomi.
- **Segnaposto letterali.** Un segnaposto scritto in un file o in un comando viene sempre rimesso in chiaro. Per scriverlo alla lettera (per esempio in un test) va spezzato.
- **Controlli «a occhio».** Coerenza tra codice fiscale e nominativo, ordine cognome/nome, confronto di firme: il modello non può farli guardando. Servono script che rispondano sì/no.
- **Avvio a freddo.** Il servizio impiega 10-15 secondi a caricare il modello; in quel tempo nulla passa.
- **Riavvio.** Se il servizio cade a metà di un turno, il contenuto resta trattenuto fino al messaggio successivo dell'utente, quando la mod lo riavvia.

## Sicurezza della mappa

La mappa contiene i dati reali. È cifrata (Fernet) con una chiave che sta sullo stesso computer, nel profilo dell'utente: protegge da una copia accidentale della cartella del progetto o da un commit sbagliato, non da chi ha accesso al profilo. Il servizio non ha autenticazione: qualunque programma che giri sul computer può chiedergli di ripristinare un segnaposto. Su un computer condiviso o non fidato, non usarlo.
