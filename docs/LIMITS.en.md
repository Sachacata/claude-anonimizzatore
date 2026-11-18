# Known limits

[Italiano](LIMITI.md) · **English**

The filter works on a best-effort basis: when in doubt it masks, but it does not see everything. This list comes from the tests run during development. Before using it with real data, measure how it behaves on your own documents with `servizio\misura_a_secco.py`.

## Data that may stay in plain text

| Case | Example (invented names) | Remedy |
|---|---|---|
| Lone surname of a person never seen before, with no clues around it | "resta da pagare Quarzenti" | `noti` list in the configuration |
| Lone first name | "ha chiamato Ginevra" | none |
| All-lower-case name with an ambiguous first name and a surname that is a common word | "rosa bianchi" | none |
| Lower-case name not in the first-name list (foreign, rare) | "ha scritto dragomir quarzenti" | none |
| ALL-CAPS name in running text made only of dictionary words, with no listed first name and no clues | two surnames that are common words | rare; `noti` list |
| Surname glued to other text in a file name | `verbalequarzenti.pdf` | file names with separators |
| Postcode and town | "36061 Bassano del Grappa" | by design: places are not masked |
| Landline numbers | "0444 123456" | by design: mobiles only |
| Dates of birth without "nato/a … il" | a date in a "Data nascita" column | none |
| Text in languages other than Italian | | the language model is Italian |

Without spaCy (service started with `--senza-spacy`, or model not installed) only the regular expressions and the list of already-known people are at work: name recognition gets much worse. `GET /stato` tells which model is in use.

## Channels the filter does not cover

- **Images.** Screenshots, page zooms, scans, photos: they reach the model as they are. Direct reading of images with the `Read` tool is denied, but browser and desktop tools that return images are not blocked. On pages with real data, use only commands that return text, numbers or yes/no.
- **Scanned PDFs and signed files** (`.p7m`): there is no text to extract, so they are neither read nor filtered. They need OCR or separate extraction.
- **Prompt attachments.** In a protected project a prompt with attachments is stopped.
- **What is already in the conversation** when you switch the filter on mid-session.
- **The model's answers** are not rewritten: the model has only seen placeholders, so it writes placeholders. But if a piece of data reached it in plain text through one of the cases above, it can repeat it.

## Towards the outside, placeholders stay placeholders

Placeholders turn back into real data only in local tools. Web searches, connectors (email, calendar, online documents) and MCP tools receive the placeholders literally. As a result:

- an email draft created by Claude contains `PERS_…` instead of names: have the text saved to a local file and paste it yourself;
- a web search about a person does not work.

This is intended: it is what keeps the data from leaving.

## False positives

- Capitalised common words and names of tools, folders, products or variables can become person placeholders; fragments of English text can become address placeholders. It happens mostly in technical text and instructions.
- Technical output with consecutive ALL-CAPS words can create fake people in the map.
- Names of schools, streets and institutes named after people become placeholders.

These are not leaks, but they can make the instructions the model reads ambiguous. Remedies: add the words to `esclusi`; reset the map when it has been polluted during testing.

## Friction in daily use

- **`Edit` in auto mode.** When the input of `Edit` contains a placeholder, the mod puts the real data back after the auto-mode check, which then refuses the call. You need to approve by hand, or edit stretches of text without names.
- **Literal placeholders.** A placeholder written in a file or a command is always turned back into real data. To write it literally (for instance in a test) it must be split.
- **Checks "by eye".** Consistency between tax code and name, surname/first-name order, comparing signatures: the model cannot do them by looking. They need scripts that answer yes or no.
- **Cold start.** The service takes 10-15 seconds to load the model; during that time nothing gets through.
- **Restart.** If the service goes down in the middle of a turn, content stays withheld until the user's next message, when the mod restarts it.

## Security of the map

The map contains the real data. It is encrypted (Fernet) with a key kept on the same computer, in the user's profile: it protects against an accidental copy of the project folder or a wrong commit, not against someone with access to the profile. The service has no authentication: any program running on the computer can ask it to restore a placeholder. Do not use it on a shared or untrusted computer.
