import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register } from 'claude-code'

import type { Interruttore, SceltaFiltro, StatoScudo } from '../types'

import type { Contatori } from '../types'

// filtro-pii — filtro invisibile di anonimizzazione.
//
// Nei progetti che hanno `.filtro-pii.json` nella radice:
//  - tutto ciò che entra nella conversazione (prompt dell'utente, risultati degli
//    strumenti, note) passa dal servizio locale (127.0.0.1:5117) che sostituisce
//    nomi, codici fiscali, IBAN, email, telefoni, indirizzi e date di nascita
//    con token stabili (PERS_0001, CF_0002…) prima che il modello li legga;
//  - negli input degli strumenti LOCALI (percorsi, contenuti scritti, comandi)
//    i token tornano dati reali, così i file su disco sono quelli veri;
//  - la lettura diretta di PDF/Office/immagini è negata (arriverebbero interi);
//  - senza servizio non passa nulla (fail-closed).
// Negli altri progetti la mod è inerte.

const PORTA = 5117
const BASE = `http://127.0.0.1:${PORTA}`
// Lo script di avvio del servizio viaggia con la mod, in <cartella della mod>\servizio.
const avvioPs1 = ($: EngineInterface): string => `${$.plugin.root}\\servizio\\avvia_servizio.ps1`
const CONTATORI = { plugin: 'filtro-pii', key: 'contatori' } as const
const ZERO: Contatori = { righe: 0, sostituzioni: 0, ripristini: 0, bloccate: 0 }

// Stessa forma di RE_TOKEN in mappa.py (senza i gruppi).
const RE_TOKEN = /(?<![A-Za-z])(?:PERS|CF|IBAN|EMAIL|TEL|IND|NASC|CARTA)_?0*\d{1,4}[a-z]{0,2}(?![A-Za-z0-9])/
// Solo qui i token tornano dati reali: mai verso web o connettori esterni.
const STRUMENTI_LOCALI = new Set(['Read', 'Write', 'Edit', 'MultiEdit', 'NotebookEdit', 'Bash', 'PowerShell', 'Grep', 'Glob'])
const RISERVATI = new Set(['tool', 'tool_use_id', 'consent', 'agentId'])
const ESTENSIONI_PREDEFINITE = ['.pdf', '.xlsx', '.xlsm', '.xls', '.docx', '.doc', '.pptx', '.png', '.jpg', '.jpeg', '.gif', '.p7m', '.msg']
const TRATTENUTO = '[filtro-pii: servizio di anonimizzazione non raggiungibile, contenuto trattenuto. Avvia servizio\\avvia_servizio.ps1 (nella cartella della mod) e riprova.]'

const REGOLE = [
  '# Progetto protetto (mod filtro-pii)',
  'In questo progetto i dati personali che vedi sono pseudonimizzati da un filtro locale: PERS_0001 (persona), CF_0001 (codice fiscale), IBAN_0001, EMAIL_0001, TEL_0001, IND_0001 (indirizzo), NASC_0001 (data di nascita). Un suffisso (PERS_0001b) indica la stessa entità con un\'altra grafia.',
  'Usa i token tal quali, anche nei file che scrivi, nei comandi e nei percorsi: vengono rimessi in chiaro automaticamente prima dell\'esecuzione, quindi i file su disco hanno i dati reali anche se tu non li vedi. Non indovinare, non inventare e non alterare mai la grafia di un token (niente «PERS 1», niente maiuscole/minuscole cambiate).',
  'Nei risultati degli strumenti i dati reali tornano token: è normale rileggere un file appena scritto e vedere i token.',
  'La lettura diretta di PDF, Excel, Word, immagini, .p7m e .msg è negata: estrai il testo con uno script locale (`py -I` con PyMuPDF, openpyxl, python-docx, extract_msg) e leggi lo stdout. Niente ricerche web né invii con token nel testo: lì i token restano token.',
  'Il comando /filtro mostra lo stato del filtro.',
].join('\n')

type Config = { attivo?: boolean; esclusi?: string[]; estensioni_bloccate?: string[] }

// Variabili di modulo: si azzerano al ricaricamento. Per questo NESSUN hook si
// fida di session.start: ognuno chiama assicuraConfig() prima di decidere se il
// progetto è protetto (il 10/11/2026 session.start era stato saltato per aver
// superato i 10 s di budget e la mod era rimasta inerte, lasciando passare tutto).
let protetto: { root: string; config: Config } | undefined
let configLetta = false
let radiciLette = ''
let cwdSessione: string | undefined
let diagnosi = 'configurazione non ancora letta'
let servizioOk = false
let ultimoAvvio = 0

// L'interruttore della sessione (pulsante nella barra, `/filtro acceso|spento`):
// scavalca `.filtro-pii.json` per questa sessione soltanto. Sta in `$.state`,
// quindi sopravvive al ricaricamento della mod; qui ne resta una copia.
const CHIAVE_INTERRUTTORE = { plugin: 'filtro-pii', key: 'interruttore' } as const
const SENZA_SCELTA: Interruttore = { scelta: 'predefinito', radiceToken: null }
let interruttore: Interruttore | undefined
const SPEGNI = 'Spegni il filtro'
const LASCIA = 'Lascia acceso'

const REGOLE_SPENTO = [
  '# Filtro spento in questa sessione (mod filtro-pii)',
  'Il filtro di anonimizzazione è stato spento a mano: da adesso i dati personali arrivano in chiaro.',
  'I token già comparsi nella conversazione (PERS_…, CF_…, IBAN_…) restano validi: negli strumenti locali vengono ancora rimessi in chiaro. Non inventarne di nuovi.',
].join('\n')

async function leggiInterruttore($: EngineInterface): Promise<Interruttore> {
  if (interruttore) return interruttore
  try {
    const { value } = await $.state.get(CHIAVE_INTERRUTTORE)
    interruttore = value ?? SENZA_SCELTA
  } catch {
    return SENZA_SCELTA // stato non leggibile adesso: vale il file, si riprova al prossimo hook
  }
  return interruttore
}

async function scriviInterruttore($: EngineInterface, nuovo: Interruttore): Promise<void> {
  interruttore = nuovo
  await $.state.set(CHIAVE_INTERRUTTORE, nuovo)
}

// Lo scudo nella barra sotto il prompt (ui.render su SessionMode, in fondo al
// file) legge questo valore: scriverlo ridisegna la barra.
const SCUDO = atom({ plugin: 'filtro-pii', key: 'scudo' } as const, 'spento' as StatoScudo)
const CONTROLLO_MS = 30_000
let scudoNoto: StatoScudo | undefined
let controllo: unknown

// Le cartelle in cui cercare `.filtro-pii.json`, chieste al motore ADESSO.
// Nell'app desktop il processo della sessione nasce «in attesa» (--await-claim)
// prima che l'utente scelga il progetto: la radice vista da session.start può non
// essere quella in cui poi si lavora, quindi non va mai tenuta per buona.
async function radiciCorrenti($: EngineInterface): Promise<string[]> {
  const radici: string[] = []
  const aggiungi = (p: unknown): void => {
    if (typeof p === 'string' && p !== '' && !radici.includes(p)) radici.push(p)
  }
  try {
    aggiungi(await $.session.root())
  } catch (err) {
    diagnosi = `session.root() fallita: ${String(err)}`
  }
  try {
    aggiungi(await $.session.cwd())
  } catch {
    // cwd non disponibile: bastano le altre
  }
  aggiungi(cwdSessione)
  return radici
}

async function leggiConfig($: EngineInterface, note?: string[]): Promise<void> {
  const radici = note ?? await radiciCorrenti($)
  radiciLette = radici.join('|')
  protetto = undefined
  let trovato: { root: string; config: Config } | undefined
  for (const root of radici) {
    let grezzo: string
    try {
      grezzo = await $.fs.read(`${root}\\.filtro-pii.json`)
    } catch {
      continue // nessun .filtro-pii.json qui: progetto non protetto
    }
    try {
      const config = JSON.parse(grezzo.replace(/^﻿/, '')) as Config
      trovato = { root, config }
      protetto = config.attivo === false ? undefined : trovato
      diagnosi = protetto ? `protetto (${root})` : `.filtro-pii.json con attivo=false (${root})`
    } catch (err) {
      // Il file c'è ma non si legge: meglio proteggere con i valori predefiniti che restare inerti.
      protetto = { root, config: {} }
      trovato = protetto
      diagnosi = `.filtro-pii.json illeggibile, uso i valori predefiniti (${String(err)})`
    }
    break
  }
  if (!protetto && radici.length > 0 && !diagnosi.startsWith('.filtro')) diagnosi = `nessun .filtro-pii.json in: ${radici.join(' | ')}`
  configLetta = radici.length > 0

  // L'interruttore della sessione scavalca il file. Acceso senza file: si
  // protegge la prima cartella della sessione con i valori predefiniti.
  const scelto = await leggiInterruttore($)
  if (scelto.scelta === 'spento') {
    protetto = undefined
    diagnosi = 'spento a mano in questa sessione'
  } else if (scelto.scelta === 'acceso' && !protetto && radici.length > 0) {
    protetto = trovato ?? { root: radici[0] as string, config: {} }
    diagnosi = `acceso a mano in questa sessione (${protetto.root})`
  }
  if (protetto && scelto.radiceToken !== protetto.root) {
    await scriviInterruttore($, { ...scelto, radiceToken: protetto.root }).catch(() => undefined)
  }
}

// Accende o spegne il filtro per questa sessione (o torna a far decidere il file).
async function imposta($: EngineInterface, scelta: SceltaFiltro): Promise<void> {
  const adesso = await leggiInterruttore($)
  await scriviInterruttore($, { ...adesso, scelta })
  await leggiConfig($)
  if (protetto) await assicuraServizio($, undefined, 6000)
  await aggiornaScudo($)
}

// Il pulsante nella barra. Accendere è immediato; spegnere chiede conferma,
// perché da quel momento i dati passano in chiaro.
async function premuto($: EngineInterface): Promise<void> {
  await assicuraConfig($)
  if (!protetto) {
    await imposta($, 'acceso')
    $.ui.toast('filtro-pii: filtro ACCESO in questa sessione. Vale da adesso: ciò che è già in chat è già passato in chiaro.')
    return
  }
  let risposta: string
  try {
    risposta = await $.ui.ask('Spegnere il filtro in questa sessione? Da adesso i dati personali passano in chiaro.', { options: [SPEGNI, LASCIA], header: 'Filtro' })
  } catch {
    $.ui.toast('filtro-pii: conferma non ottenuta, il filtro resta acceso. Per spegnerlo: /filtro spento')
    return
  }
  if (risposta !== SPEGNI) return
  await imposta($, 'spento')
  $.ui.toast('filtro-pii: filtro SPENTO in questa sessione. Da adesso i dati passano in chiaro.')
}

// Filtro spento dopo essere stato acceso: i token già in conversazione devono
// ancora tornare dati reali negli strumenti locali, altrimenti finirebbero
// scritti alla lettera nei file. Se il servizio non risponde, la chiamata passa
// com'è (il filtro è spento: niente da trattenere).
async function ripristinaDaSpento<T extends { tool: string }>($: EngineInterface, e: T): Promise<T> {
  const radice = interruttore?.scelta === 'spento' ? interruttore.radiceToken : null
  if (!radice || !STRUMENTI_LOCALI.has(e.tool)) return e
  try {
    const conta = { n: 0 }
    const nuovo = await ripristinaValore($, e, conta, radice) as T
    if (conta.n > 0) await somma($, { ripristini: conta.n })
    return nuovo
  } catch {
    return e
  }
}

// Un «non protetto» non si tiene mai in memoria: si rilegge a ogni hook (costa
// una lettura di file fallita). Un «protetto» si rilegge solo se la cartella
// della sessione è cambiata. Così una lettura fatta troppo presto, o nella
// cartella sbagliata, non lascia la mod inerte per tutta la sessione.
async function assicuraConfig($: EngineInterface): Promise<void> {
  const radici = await radiciCorrenti($)
  if (!configLetta || !protetto || radici.join('|') !== radiciLette) await leggiConfig($, radici)
  await aggiornaScudo($)
}

// Porta lo scudo allo stato di adesso. Lo scudo dice «attivo» solo se il
// progetto è protetto E il servizio risponde: se l'ultima chiamata è fallita
// lo richiede al servizio prima di decidere. Non lancia mai: un errore qui non
// deve fermare il filtro.
async function aggiornaScudo($: EngineInterface): Promise<void> {
  try {
    let stato: StatoScudo = 'spento'
    if (protetto) {
      if (!servizioOk) servizioOk = await servizioRisponde($)
      stato = servizioOk ? 'attivo' : 'fermo'
    }
    scudoNoto ??= await read($, SCUDO)
    if (stato !== scudoNoto) {
      await update($, SCUDO, () => stato)
      scudoNoto = stato
    }
    if (protetto && controllo === undefined) {
      // A sessione ferma nessun hook gira: senza questo controllo lo scudo
      // resterebbe verde anche se il servizio si fosse fermato nel frattempo.
      controllo = $.clock.every(CONTROLLO_MS, () => {
        void (async () => {
          if (protetto) servizioOk = await servizioRisponde($)
          await aggiornaScudo($)
        })()
      })
    }
  } catch {
    // lo scudo è solo un'indicazione
  }
}

async function servizioRisponde($: EngineInterface): Promise<boolean> {
  try {
    const r = await $.http.fetch(`${BASE}/stato`)
    return r.ok
  } catch {
    return false
  }
}

// Avvia il servizio se non risponde e aspetta che parta, ma senza mai superare
// `budgetMs`: gli hook hanno 10 s, oltre vengono saltati. Se non basta, il
// servizio finisce di partire da solo e gli hook successivi lo trovano attivo
// (nel frattempo session.append e tool.call trattengono tutto: fail-closed).
async function assicuraServizio($: EngineInterface, signal?: AbortSignal, budgetMs = 7000): Promise<boolean> {
  const fine = Date.now() + budgetMs
  servizioOk = await servizioRisponde($)
  if (servizioOk) return true
  if (Date.now() - ultimoAvvio > 20_000) {
    ultimoAvvio = Date.now()
    try {
      const timeoutMs = Math.max(1500, Math.min(5000, fine - Date.now() - 1000))
      await $.process.run(['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', avvioPs1($)], { timeoutMs })
    } catch (err) {
      $.ui.toast(`filtro-pii: non riesco ad avviare il servizio (${String(err)}). Esegui a mano servizio\\avvia_servizio.ps1 nella cartella della mod`)
    }
  }
  for (let i = 0; i < 10 && !servizioOk && Date.now() < fine; i++) {
    await $.clock.sleep(500, signal ? { signal } : undefined).catch(() => undefined)
    if (signal?.aborted) break
    servizioOk = await servizioRisponde($)
  }
  return servizioOk
}

async function chiama($: EngineInterface, via: '/anonimizza' | '/ripristina', testo: string, radice = protetto?.root): Promise<{ testo: string; n: number }> {
  if (!radice || testo === '') return { testo, n: 0 }
  const r = await $.http.fetch(`${BASE}${via}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ progetto: radice, testo }),
  })
  if (!r.ok) throw new Error(`filtro-pii ${via}: HTTP ${r.status}`)
  const out = JSON.parse(r.text) as { testo: string; n: number }
  servizioOk = true
  return out
}

async function somma($: EngineInterface, delta: Partial<Contatori>): Promise<void> {
  const { value = ZERO } = await $.state.get(CONTATORI)
  const nuovo = { ...value }
  for (const k of Object.keys(delta) as (keyof Contatori)[]) nuovo[k] = (nuovo[k] ?? 0) + (delta[k] ?? 0)
  await $.state.set(CONTATORI, nuovo)
}

// Anonimizza i blocchi di una riga della conversazione (testo e tool_result).
// Se il servizio non risponde, il testo viene sostituito da un avviso: fail-closed.
async function anonimizzaBlocchi($: EngineInterface, blocchi: readonly unknown[]): Promise<{ blocchi: unknown[]; n: number }> {
  let n = 0
  const testo = async (t: string): Promise<string> => {
    try {
      const r = await chiama($, '/anonimizza', t)
      n += r.n
      return r.testo
    } catch {
      servizioOk = false
      n += 1
      return TRATTENUTO
    }
  }
  const out: unknown[] = []
  for (const b of blocchi) {
    const blocco = b as { type?: string; text?: string; content?: unknown }
    if (blocco.type === 'text' && typeof blocco.text === 'string') {
      out.push({ ...blocco, text: await testo(blocco.text) })
    } else if (blocco.type === 'tool_result') {
      if (typeof blocco.content === 'string') {
        out.push({ ...blocco, content: await testo(blocco.content) })
      } else if (Array.isArray(blocco.content)) {
        const interni: unknown[] = []
        for (const c of blocco.content) {
          const cb = c as { type?: string; text?: string }
          interni.push(cb.type === 'text' && typeof cb.text === 'string' ? { ...cb, text: await testo(cb.text) } : c)
        }
        out.push({ ...blocco, content: interni })
      } else {
        out.push(b)
      }
    } else {
      out.push(b)
    }
  }
  return { blocchi: out, n }
}

// Rimette i dati reali nelle stringhe di un input (ricorsivo), saltando le chiavi riservate.
async function ripristinaValore($: EngineInterface, v: unknown, conta: { n: number }, radice?: string): Promise<unknown> {
  if (typeof v === 'string') {
    if (!RE_TOKEN.test(v)) return v
    const r = await chiama($, '/ripristina', v, radice ?? protetto?.root)
    conta.n += r.n
    return r.testo
  }
  if (Array.isArray(v)) {
    const out: unknown[] = []
    for (const x of v) out.push(await ripristinaValore($, x, conta, radice))
    return out
  }
  if (v !== null && typeof v === 'object') {
    const out: Record<string, unknown> = {}
    for (const [k, x] of Object.entries(v)) out[k] = RISERVATI.has(k) ? x : await ripristinaValore($, x, conta, radice)
    return out
  }
  return v
}

function estensioneDi(percorso: string): string {
  const m = /\.[A-Za-z0-9]{1,5}$/.exec(percorso.trim())
  return m ? m[0].toLowerCase() : ''
}

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    // Un errore qui non deve impedire la lettura della configurazione.
    await $.command.register({ name: 'filtro', description: 'Stato del filtro di anonimizzazione (filtro-pii)' }).catch(() => undefined)
    cwdSessione = typeof (e as { cwd?: unknown }).cwd === 'string' ? (e as { cwd: string }).cwd : undefined
    await leggiConfig($)
    if (protetto) await assicuraServizio($, next.signal, 6000)
    await aggiornaScudo($)
    return next(e)
  })

  on('prompt.submit', async ($, e, next) => {
    await assicuraConfig($)
    if (!protetto) return next(e)
    // Comandi slash e prompt nascosti non accettano riscritture del testo:
    // passano, e la loro riga viene comunque filtrata in session.append.
    if (e.command || e.isMeta) return next(e)
    if (e.attachments && e.attachments.length > 0) {
      $.ui.toast('filtro-pii: allegati non filtrabili in un progetto protetto. Salva il file nel progetto e chiedi di estrarne il testo.')
      return { drop: 'filtro-pii: prompt con allegati fermato (progetto protetto, allegati non filtrabili)' }
    }
    if (!await assicuraServizio($, next.signal)) {
      $.ui.toast('filtro-pii: servizio non raggiungibile, prompt fermato')
      return { drop: 'filtro-pii: servizio di anonimizzazione non raggiungibile' }
    }
    try {
      const { testo, n } = await chiama($, '/anonimizza', e.text)
      if (n > 0) await somma($, { righe: 1, sostituzioni: n })
      return next({ ...e, text: testo })
    } catch (err) {
      servizioOk = false
      $.ui.toast(`filtro-pii: servizio non raggiungibile, prompt fermato (${String(err)})`)
      return { drop: 'filtro-pii: servizio di anonimizzazione non raggiungibile' }
    }
  }).catch(($, e, next) => (next.called || !protetto ? next(e) : { drop: 'filtro-pii: errore nel filtro, prompt fermato per sicurezza' }))

  on('session.append', async ($, e, next) => {
    await assicuraConfig($)
    if (!protetto || e.message.type === 'assistant') return next(e)
    const { blocchi, n } = await anonimizzaBlocchi($, e.message.content)
    if (n > 0) await somma($, { righe: 1, sostituzioni: n })
    return next({ ...e, message: { ...e.message, content: blocchi as typeof e.message.content } })
  }).catch(($, e, next) => {
    if (next.called || !protetto) return next(e)
    // Errore nel filtro: la riga entra, ma col testo trattenuto (fail-closed).
    const content = e.message.content.map(b => {
      const blocco = b as { type?: string }
      if (blocco.type === 'text') return { ...blocco, text: TRATTENUTO }
      if (blocco.type === 'tool_result') return { ...blocco, content: TRATTENUTO }
      return b
    })
    return next({ ...e, message: { ...e.message, content: content as typeof e.message.content } })
  })

  on('tool.call', async ($, e, next) => {
    await assicuraConfig($)
    if (!protetto) return next(await ripristinaDaSpento($, e))
    const bloccate = protetto.config.estensioni_bloccate ?? ESTENSIONI_PREDEFINITE
    if (e.tool === 'Read') {
      const percorso = String((e as Record<string, unknown>).file_path ?? '')
      const est = estensioneDi(percorso)
      if (est && bloccate.includes(est)) {
        await somma($, { bloccate: 1 })
        return {
          deny: `filtro-pii: progetto protetto, lettura diretta di «${est}» negata (il file arriverebbe intero ai server). `
            + 'Estrai il testo con uno script locale (`py -I`: PyMuPDF per PDF, openpyxl per Excel, python-docx per Word, extract_msg per .msg) e leggi lo stdout, che viene filtrato.',
        }
      }
    }
    if (!STRUMENTI_LOCALI.has(e.tool)) return next(e)
    const conta = { n: 0 }
    try {
      const nuovo = await ripristinaValore($, e, conta) as typeof e
      if (conta.n > 0) await somma($, { ripristini: conta.n })
      return next(nuovo)
    } catch (err) {
      servizioOk = false
      return { deny: `filtro-pii: servizio di anonimizzazione non raggiungibile (${String(err)}); chiamata fermata per non far uscire dati in chiaro.` }
    }
  }).catch(($, e, next) => (next.called || !protetto ? next(e) : { deny: 'filtro-pii: errore nel filtro, chiamata fermata per sicurezza' }))

  on('prompt.compose', async ($, e, next) => {
    const r = await next(e)
    await assicuraConfig($).catch(() => undefined)
    if (!protetto) {
      // Spento dopo essere stato acceso: il modello deve sapere che i token restano validi.
      if (interruttore?.scelta !== 'spento' || !interruttore.radiceToken) return r
      return { sections: [...r.sections, { id: 'filtro-pii:regole', text: REGOLE_SPENTO, scope: 'session' }] }
    }
    return { sections: [...r.sections, { id: 'filtro-pii:regole', text: REGOLE, scope: 'session' }] }
  })

  on('command.run', { command: 'filtro' }, async ($, e) => {
    // `/filtro acceso`, `/filtro spento`, `/filtro predefinito`: lo stesso
    // interruttore del pulsante nella barra (digitarlo vale come conferma).
    const richiesta = (e.args ?? '').trim().toLowerCase()
    const scelte: Record<string, SceltaFiltro> = { acceso: 'acceso', on: 'acceso', attiva: 'acceso', spento: 'spento', off: 'spento', disattiva: 'spento', predefinito: 'predefinito' }
    const scelta = scelte[richiesta]
    if (scelta) await imposta($, scelta)
    const { value = ZERO } = await $.state.get(CONTATORI)
    await leggiConfig($) // rilegge sempre: /filtro deve dire la verità di adesso
    const attivo = protetto ? await assicuraServizio($, undefined, 6000) : await servizioRisponde($)
    await aggiornaScudo($)
    const righe = [
      protetto ? `Progetto protetto: ${protetto.root}` : `Progetto non protetto: filtro inerte (${diagnosi}).`,
      `Servizio locale 127.0.0.1:${PORTA}: ${attivo ? 'attivo' : 'NON raggiungibile'}`,
    ]
    if (protetto) {
      righe.push(`In questa sessione: ${value.righe} righe filtrate, ${value.sostituzioni} sostituzioni, ${value.ripristini} ripristini, ${value.bloccate} letture binarie negate.`)
      if (protetto.config.esclusi?.length) righe.push(`Esclusi dal filtro: ${protetto.config.esclusi.join(', ')}`)
    }
    const int = await leggiInterruttore($)
    righe.push(int.scelta === 'predefinito'
      ? 'Interruttore della sessione: non toccato (decide .filtro-pii.json). Per cambiarlo: pulsante nella barra, /filtro acceso, /filtro spento.'
      : `Interruttore della sessione: ${int.scelta} a mano. Per tornare al file: /filtro predefinito.`)
    if (richiesta && !scelta) righe.push(`Argomento «${richiesta}» non riconosciuto: usa acceso, spento o predefinito.`)
    return { text: righe.join('\n') }
  })

  // Lo scudo: nella barra sotto il prompt, accanto alle etichette di modalità.
  // Verde solo con progetto protetto e servizio attivo; avviso se il progetto è
  // protetto ma il servizio è fermo; niente nei progetti non protetti.
  on('ui.render', { component: 'SessionMode' }, async ($, e, next) => {
    const stato = await read($, SCUDO)
    const sotto = await next(e) // le etichette del motore e delle altre mod restano
    const { Box, Button, Text } = $.ui.resolve(e)
    // La scritta è un pulsante: un clic accende il filtro (se spento) o chiede
    // conferma e lo spegne (se acceso), per questa sessione soltanto.
    // flexShrink 0: l'11/11/2026 nell'app desktop l'avviso usciva tagliato
    // («Filtro f») anche con spazio libero nella barra; la scritta non deve
    // restringersi per far posto alle altre etichette.
    return (
      <Box flexDirection="row" alignItems="center" gap={1} flexShrink={0}>
        <Box flexShrink={0}>
          <Button key="filtro" plain onPress={() => { void premuto($) }}>
            {stato === 'attivo'
              ? <Text color="success">🛡 Protetta</Text>
              : stato === 'fermo'
                ? <Text color="warning">⚠ Filtro fermo</Text>
                : <Text dimColor>Filtro spento</Text>}
          </Button>
        </Box>
        {sotto}
      </Box>
    )
  })
}
