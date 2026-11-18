# 4-point acceptance test

[Italiano](COLLAUDO.md) · **English**

Run it after installing and **after every update of the mod**, always in a new session (a session that is already open keeps using the mod it loaded at start-up).

Preparation: copy the `esempi` folder somewhere for testing, rename `filtro-pii.esempio.json` to `.filtro-pii.json` and open a Claude Code session in that folder. The data in `nota.txt` is made up.

| # | What you do | What must happen |
|---|---|---|
| 1 | Type `/filtro` | "Progetto protetto" (project protected) with the right folder, service running. In the bar: 🛡 Protetta |
| 2 | Ask "read nota.txt and tell me what it contains" | The answer shows placeholders (`PERS_…`, `CF_…`, `IBAN_…`, `EMAIL_…`, `TEL_…`), not the names |
| 3 | Put any PDF in the folder and ask Claude to read it | Direct reading is denied; Claude extracts the text with a script, and the text arrives filtered |
| 4 | Stop the service (command below) and ask to read `nota.txt` again | "contenuto trattenuto" (content withheld), or the service restarts by itself. **Never plain text** |

To stop the service:

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:5117/arresta
```

With the service stopped the bar must say ⚠ Filtro fermo (filter down). The service restarts at your next message, or by hand with `servizio\avvia_servizio.ps1`.

## If a point fails

**Do not use the filter with real data.** In particular, if at point 2 you see the names in plain text the filter is inert: check the diagnosis line with `/filtro`, make sure the session is new and that the mod is actually loaded.

## What to expect from the sample note

- five people, one tax code, one IBAN, two email addresses, one mobile number, one address and one date of birth become placeholders;
- the name written all in lower case is caught (spaCy required);
- postcode and town stay in plain text: a known limit, see [LIMITS.en.md](LIMITS.en.md).
