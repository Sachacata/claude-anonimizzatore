# Collaudo in 4 punti

**Italiano** · [English](TESTING.en.md)

Da fare dopo l'installazione e **a ogni aggiornamento della mod**, sempre in una sessione nuova (una sessione già aperta continua a usare la mod che aveva caricato all'avvio).

Preparazione: copia la cartella `esempi` in un posto di prova, rinomina `filtro-pii.esempio.json` in `.filtro-pii.json` e apri una sessione di Claude Code in quella cartella. I dati di `nota.txt` sono inventati.

| # | Cosa fai | Cosa deve succedere |
|---|---|---|
| 1 | Digiti `/filtro` | «Progetto protetto» con la cartella giusta, servizio attivo. Nella barra: 🛡 Protetta |
| 2 | Chiedi «leggi nota.txt e dimmi cosa contiene» | Nella risposta compaiono segnaposto (`PERS_…`, `CF_…`, `IBAN_…`, `EMAIL_…`, `TEL_…`), non i nomi |
| 3 | Metti un PDF qualsiasi nella cartella e chiedi di leggerlo | La lettura diretta è negata; Claude estrae il testo con uno script, e il testo arriva filtrato |
| 4 | Fermi il servizio (comando sotto) e chiedi di rileggere `nota.txt` | «contenuto trattenuto», oppure il servizio riparte da solo. **Mai testo in chiaro** |

Per fermare il servizio:

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:5117/arresta
```

A servizio fermo la barra deve dire ⚠ Filtro fermo. Il servizio riparte al tuo messaggio successivo, oppure a mano con `servizio\avvia_servizio.ps1`.

## Se un punto fallisce

**Non usare il filtro con dati veri.** In particolare, se al punto 2 vedi i nomi in chiaro il filtro è inerte: controlla con `/filtro` la riga di diagnosi, verifica che la sessione sia nuova e che la mod risulti caricata.

## Cosa aspettarsi dalla nota di esempio

- cinque persone, un codice fiscale, un IBAN, due email, un cellulare, un indirizzo e una data di nascita diventano segnaposto;
- il nome scritto tutto minuscolo viene preso (serve spaCy);
- CAP e comune restano in chiaro: è un limite noto, vedi [LIMITI.md](LIMITI.md).
