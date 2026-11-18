import { expect, test } from 'claude-code/testing'

// Servizio finto: «Giacomo Bertolazzi» ↔ PERS_0001 (dati inventati).
const ROOT = 'C:\\Progetti\\test anonimizzatore'
const CONFIG = JSON.stringify({ attivo: true, esclusi: ['Vicenza'] })

function servizioFinto(on: any, chiamate: string[] = []) {
  on('http.fetch', (_: unknown, e: { url: string; init?: { body?: string } }) => {
    const via = e.url.replace(/^http:\/\/127\.0\.0\.1:5117/, '')
    chiamate.push(via)
    if (via === '/stato') return { value: { status: 200, ok: true, headers: {}, text: '{"ok":true}' } }
    const { testo } = JSON.parse(e.init?.body ?? '{}') as { testo: string }
    const out = via === '/anonimizza'
      ? testo.replaceAll('Giacomo Bertolazzi', 'PERS_0001')
      : testo.replaceAll('PERS_0001', 'Giacomo Bertolazzi')
    const n = out === testo ? 0 : 1
    return { value: { status: 200, ok: true, headers: {}, text: JSON.stringify({ testo: out, n }) } }
  })
}

function ambiente(on: any, protetto: boolean) {
  on('session.root', () => ({ value: ROOT }))
  on('fs.read', () => {
    if (!protetto) throw new Error('ENOENT')
    return { value: CONFIG }
  })
  on('command.register', () => ({ value: { command: 'filtro' } }))
  on('ui.status', () => ({ value: undefined }))
  on('ui.toast', () => ({ value: undefined }))
  on('clock.sleep', () => ({ value: undefined }))
  on('clock.every', () => ({ deny: 'nei test il controllo periodico dello scudo non parte' }))
  on('process.run', () => ({ value: { exitCode: 0, stdout: '', stderr: '' } }))
  on('session.start', (_: unknown, e: { cwd: string }) => ({ cwd: e.cwd }))
  on('prompt.submit', (_: unknown, e: { text: string }) => ({ text: e.text }))
}

test('progetto non protetto: tutto passa invariato e il servizio non viene chiamato', async ($, on) => {
  ambiente(on, false)
  const chiamate: string[] = []
  servizioFinto(on, chiamate)
  let visto = ''
  on('tool.call', (_, e: any) => { visto = e.content; return { result: {} } })

  await $.session.start({ cwd: ROOT, surface: 'desktop', isInteractive: true })
  const r = await $.prompt.submit({ text: 'Scrivi a Giacomo Bertolazzi' })
  expect('text' in r && r.text).toBe('Scrivi a Giacomo Bertolazzi')
  await $.tool.call({ tool: 'Write', file_path: 'C:\\x.txt', content: 'Egregio PERS_0001' })
  expect(visto).toBe('Egregio PERS_0001')
  expect(chiamate.length).toBe(0)
})

test('progetto protetto: il prompt viene anonimizzato', async ($, on) => {
  ambiente(on, true)
  servizioFinto(on)
  await $.session.start({ cwd: ROOT, surface: 'desktop', isInteractive: true })
  const r = await $.prompt.submit({ text: 'Scrivi a Giacomo Bertolazzi' })
  expect('text' in r && r.text).toBe('Scrivi a PERS_0001')
})

test('progetto protetto: prompt con allegati fermato', async ($, on) => {
  ambiente(on, true)
  servizioFinto(on)
  await $.session.start({ cwd: ROOT, surface: 'desktop', isInteractive: true })
  const r = await $.prompt.submit({ text: 'guarda', attachments: [{ type: 'image', mediaType: 'image/png' }] })
  expect('drop' in r).toBe(true)
})

test('progetto protetto: i token tornano reali solo negli strumenti locali', async ($, on) => {
  ambiente(on, true)
  servizioFinto(on)
  const visti: Record<string, unknown> = {}
  on('tool.call', (_, e: any) => { visti[e.tool] = e; return { result: {} } })
  await $.session.start({ cwd: ROOT, surface: 'desktop', isInteractive: true })

  await $.tool.call({ tool: 'Write', file_path: 'C:\\lettera_PERS_0001.txt', content: 'Egregio PERS_0001' })
  expect((visti.Write as any).content).toBe('Egregio Giacomo Bertolazzi')
  expect((visti.Write as any).file_path).toBe('C:\\lettera_Giacomo Bertolazzi.txt')

  await $.tool.call({ tool: 'Edit', file_path: 'C:\\n.txt', old_string: 'PERS_0001 vecchio', new_string: 'PERS_0001 nuovo' })
  expect((visti.Edit as any).old_string).toBe('Giacomo Bertolazzi vecchio')

  await $.tool.call({ tool: 'Bash', command: 'grep PERS_0001 dati/registro.csv' })
  expect((visti.Bash as any).command).toBe('grep Giacomo Bertolazzi dati/registro.csv')

  await $.tool.call({ tool: 'WebSearch', query: 'PERS_0001' })
  expect((visti.WebSearch as any).query).toBe('PERS_0001')
})

test('progetto protetto: lettura diretta di PDF ed Excel negata, txt no', async ($, on) => {
  ambiente(on, true)
  servizioFinto(on)
  let letto = ''
  on('tool.call', (_, e: any) => { letto = e.file_path; return { result: {} } })
  await $.session.start({ cwd: ROOT, surface: 'desktop', isInteractive: true })

  const pdf = await $.tool.call({ tool: 'Read', file_path: 'C:\\dati\\sentenza.PDF' })
  expect('deny' in pdf && /negata/.test(pdf.deny ?? '')).toBe(true)
  const xlsx = await $.tool.call({ tool: 'Read', file_path: 'C:\\dati\\registro.xlsx' })
  expect('deny' in xlsx).toBe(true)
  await $.tool.call({ tool: 'Read', file_path: 'C:\\dati\\nota.txt' })
  expect(letto).toBe('C:\\dati\\nota.txt')
})

test('progetto protetto: le righe della conversazione vengono filtrate', async ($, on) => {
  ambiente(on, true)
  servizioFinto(on)
  await $.session.start({ cwd: ROOT, surface: 'desktop', isInteractive: true })
  const r = await $.session.append({ message: { type: 'user', content: [{ type: 'text', text: 'nota su Giacomo Bertolazzi' }] } })
  expect('message' in r && JSON.stringify(r.message.content)).toContain('PERS_0001')
  expect('message' in r && JSON.stringify(r.message.content)).not.toContain('Bertolazzi')
})

test('session.start saltato: gli altri hook proteggono lo stesso', async ($, on) => {
  ambiente(on, true)
  servizioFinto(on)
  // Niente $.session.start: è il caso del 10/11/2026 (hook saltato per budget).
  const a = await $.session.append({ message: { type: 'user', content: [{ type: 'text', text: 'nota su Giacomo Bertolazzi' }] } })
  expect('message' in a && JSON.stringify(a.message.content)).not.toContain('Bertolazzi')
  const pdf = await $.tool.call({ tool: 'Read', file_path: 'C:\\dati\\sentenza.pdf' })
  expect('deny' in pdf).toBe(true)
})

test('sessione nata in un\'altra cartella (desktop, --await-claim): protegge appena la radice diventa il progetto', async ($, on) => {
  // Caso del collaudo del 10/11/2026 ore 09:21: session.start gira prima che la
  // sessione sia assegnata al progetto, e il «non protetto» restava in memoria.
  let radice = 'C:\\Users\\Altro'
  on('session.root', () => ({ value: radice }))
  on('fs.read', (_: unknown, e: any) => {
    if (!JSON.stringify(e).includes('test anonimizzatore')) throw new Error('ENOENT')
    return { value: CONFIG }
  })
  on('command.register', () => ({ value: { command: 'filtro' } }))
  on('ui.status', () => ({ value: undefined }))
  on('ui.toast', () => ({ value: undefined }))
  on('clock.sleep', () => ({ value: undefined }))
  on('clock.every', () => ({ deny: 'nei test il controllo periodico dello scudo non parte' }))
  on('process.run', () => ({ value: { exitCode: 0, stdout: '', stderr: '' } }))
  on('session.start', (_: unknown, e: any) => ({ cwd: e.cwd }))
  on('tool.call', () => ({ result: {} }))
  servizioFinto(on)
  await $.session.start({ cwd: radice, surface: 'desktop', isInteractive: true })
  const prima = await $.tool.call({ tool: 'Read', file_path: 'C:\\dati\\sentenza.pdf' })
  expect('deny' in prima).toBe(false)

  radice = ROOT
  const pdf = await $.tool.call({ tool: 'Read', file_path: 'C:\\dati\\sentenza.pdf' })
  expect('deny' in pdf).toBe(true)
  const a = await $.session.append({ message: { type: 'user', content: [{ type: 'text', text: 'nota su Giacomo Bertolazzi' }] } })
  expect('message' in a && JSON.stringify(a.message.content)).not.toContain('Bertolazzi')
})

// Lo scudo nella barra sotto il prompt (SessionMode).
const BARRA = { plugin: 'filtro-pii', component: 'SessionMode', props: { modes: [] } } as const

// Sta al posto del motore: disegna la barra com'è senza la mod.
function barraDelMotore(on: any) {
  on('ui.render', ($: any, e: any) => {
    const { Text } = $.ui.resolve(e)
    return h(Text, null, 'motore')
  })
}

test('scudo: verde solo con progetto protetto e servizio attivo', async ($, on) => {
  ambiente(on, true)
  barraDelMotore(on)
  servizioFinto(on)
  await $.session.start({ cwd: ROOT, surface: 'desktop', isInteractive: true })
  for (const surface of ['terminal', 'desktop'] as const) {
    const ui = await $.ui.mount({ ...BARRA, surface })
    expect((await ui.find({ type: 'Text', text: /Protetta/ }))?.text).toBe('🛡 Protetta')
    expect(await ui.find({ type: 'Text', text: /Filtro fermo/ })).toBeFalsy()
    await ui.unmount()
  }
})

test('scudo: nessuna icona nel progetto non protetto', async ($, on) => {
  ambiente(on, false)
  barraDelMotore(on)
  servizioFinto(on)
  await $.session.start({ cwd: ROOT, surface: 'desktop', isInteractive: true })
  await $.prompt.submit({ text: 'ciao' })
  const ui = await $.ui.mount({ ...BARRA, surface: 'desktop' })
  expect(await ui.find({ type: 'Text', text: /Protetta|Filtro fermo/ })).toBeFalsy()
  await ui.unmount()
})

test('scudo: avviso, non scudo, se il servizio non risponde', async ($, on) => {
  ambiente(on, true)
  barraDelMotore(on)
  on('http.fetch', () => { throw new Error('ECONNREFUSED') })
  await $.session.start({ cwd: ROOT, surface: 'desktop', isInteractive: true })
  const ui = await $.ui.mount({ ...BARRA, surface: 'desktop' })
  expect(await ui.find({ type: 'Text', text: /Protetta/ })).toBeFalsy()
  expect((await ui.find({ type: 'Text', text: /Filtro fermo/ }))?.text).toBe('⚠ Filtro fermo')
  await ui.unmount()
})

test('scudo: passa da avviso a verde quando il servizio torna', async ($, on) => {
  ambiente(on, true)
  barraDelMotore(on)
  let su = false
  on('http.fetch', () => {
    if (!su) throw new Error('ECONNREFUSED')
    return { value: { status: 200, ok: true, headers: {}, text: '{"ok":true,"testo":"x","n":0}' } }
  })
  on('tool.call', () => ({ result: {} }))
  await $.session.start({ cwd: ROOT, surface: 'desktop', isInteractive: true })
  const ui = await $.ui.mount({ ...BARRA, surface: 'desktop' })
  expect((await ui.find({ type: 'Text', text: /Filtro fermo/ }))?.text).toBe('⚠ Filtro fermo')
  su = true
  await $.tool.call({ tool: 'Read', file_path: 'C:\\dati\\nota.txt' })
  expect((await ui.find({ type: 'Text', text: /Protetta/ }))?.text).toBe('🛡 Protetta')
  await ui.unmount()
})

// L'interruttore della sessione (pulsante nella barra, /filtro acceso|spento).
// Nome e token di prova scritti a pezzi: questo file viene modificato da una
// sessione sotto filtro, che rimetterebbe in chiaro un token scritto intero.
const NOME = 'Xyzzy Prova'
const TOK = 'PERS' + '_0009'

function servizioProva(on: any, chiamate: string[] = []) {
  on('http.fetch', (_: unknown, e: { url: string; init?: { body?: string } }) => {
    const via = e.url.replace(/^http:\/\/127\.0\.0\.1:5117/, '')
    chiamate.push(via)
    if (via === '/stato') return { value: { status: 200, ok: true, headers: {}, text: '{"ok":true}' } }
    const { testo } = JSON.parse(e.init?.body ?? '{}') as { testo: string }
    const out = via === '/anonimizza' ? testo.replaceAll(NOME, TOK) : testo.replaceAll(TOK, NOME)
    return { value: { status: 200, ok: true, headers: {}, text: JSON.stringify({ testo: out, n: out === testo ? 0 : 1 }) } }
  })
}

test('interruttore: nel progetto non protetto il pulsante accende il filtro', async ($, on) => {
  ambiente(on, false)
  barraDelMotore(on)
  servizioProva(on)
  await $.session.start({ cwd: ROOT, surface: 'desktop', isInteractive: true })
  const ui = await $.ui.mount({ ...BARRA, surface: 'desktop' })
  expect((await ui.find({ type: 'Text', text: /Filtro spento/ }))?.text).toBe('Filtro spento')
  const prima = await $.prompt.submit({ text: `Scrivi a ${NOME}` })
  expect('text' in prima && prima.text).toBe(`Scrivi a ${NOME}`)

  await ui.press({ key: 'filtro' })
  expect((await ui.find({ type: 'Text', text: /Protetta/ }))?.text).toBe('🛡 Protetta')
  const dopo = await $.prompt.submit({ text: `Scrivi a ${NOME}` })
  expect('text' in dopo && dopo.text).toBe(`Scrivi a ${TOK}`)
  const pdf = await $.tool.call({ tool: 'Read', file_path: 'C:\\dati\\sentenza.pdf' })
  expect('deny' in pdf).toBe(true)
  await ui.unmount()
})

test('interruttore: spegnere chiede conferma; senza conferma resta acceso', async ($, on) => {
  ambiente(on, true)
  barraDelMotore(on)
  servizioProva(on)
  let risposta = 'Lascia acceso'
  let domande = 0
  // $.ui.ask è una chiamata dello strumento AskUserQuestion: qui risponde il test.
  on('tool.call', (_: unknown, e: any) => {
    if (e.tool !== 'AskUserQuestion') return { result: {} }
    domande += 1
    const answers: Record<string, string> = {}
    for (const q of e.questions) answers[q.question] = risposta
    return { result: { questions: e.questions, answers } }
  })
  await $.session.start({ cwd: ROOT, surface: 'desktop', isInteractive: true })
  const ui = await $.ui.mount({ ...BARRA, surface: 'desktop' })

  await ui.press({ key: 'filtro' })
  expect(domande).toBe(1)
  const acceso = await $.prompt.submit({ text: `Scrivi a ${NOME}` })
  expect('text' in acceso && acceso.text).toBe(`Scrivi a ${TOK}`)

  risposta = 'Spegni il filtro'
  await ui.press({ key: 'filtro' })
  expect((await ui.find({ type: 'Text', text: /Filtro spento/ }))?.text).toBe('Filtro spento')
  const spento = await $.prompt.submit({ text: `Scrivi a ${NOME}` })
  expect('text' in spento && spento.text).toBe(`Scrivi a ${NOME}`)
  await ui.unmount()
})

test('interruttore: dopo lo spegnimento i token già visti tornano reali negli strumenti locali', async ($, on) => {
  ambiente(on, true)
  servizioProva(on)
  const visti: Record<string, any> = {}
  on('tool.call', (_, e: any) => { visti[e.tool] = e; return { result: {} } })
  await $.session.start({ cwd: ROOT, surface: 'desktop', isInteractive: true })
  await $.command.run({ command: 'filtro', args: 'spento' })

  await $.tool.call({ tool: 'Write', file_path: 'C:\\x.txt', content: `Gentile ${TOK}` })
  expect(visti.Write.content).toBe(`Gentile ${NOME}`)
  await $.tool.call({ tool: 'WebSearch', query: TOK })
  expect(visti.WebSearch.query).toBe(TOK)
  // Spento: la lettura diretta dei PDF non è più negata e le righe entrano in chiaro.
  const pdf = await $.tool.call({ tool: 'Read', file_path: 'C:\\dati\\sentenza.pdf' })
  expect('deny' in pdf).toBe(false)
  const a = await $.session.append({ message: { type: 'user', content: [{ type: 'text', text: `nota su ${NOME}` }] } })
  expect('message' in a && JSON.stringify(a.message.content)).toContain(NOME)
})

test('interruttore: /filtro acceso, spento e predefinito', async ($, on) => {
  ambiente(on, false)
  servizioProva(on)
  await $.session.start({ cwd: ROOT, surface: 'desktop', isInteractive: true })

  const su = await $.command.run({ command: 'filtro', args: 'acceso' })
  expect(su?.text ?? '').toContain('acceso a mano')
  const acceso = await $.prompt.submit({ text: `Scrivi a ${NOME}` })
  expect('text' in acceso && acceso.text).toBe(`Scrivi a ${TOK}`)

  await $.command.run({ command: 'filtro', args: 'predefinito' })
  const dopo = await $.prompt.submit({ text: `Scrivi a ${NOME}` })
  expect('text' in dopo && dopo.text).toBe(`Scrivi a ${NOME}`)

  const boh = await $.command.run({ command: 'filtro', args: 'forse' })
  expect(boh?.text ?? '').toContain('non riconosciuto')
})

test('progetto protetto, servizio assente: niente passa (fail-closed)', async ($, on) => {
  ambiente(on, true)
  on('http.fetch', () => { throw new Error('ECONNREFUSED') })
  let chiamato = false
  on('tool.call', () => { chiamato = true; return { result: {} } })
  await $.session.start({ cwd: ROOT, surface: 'desktop', isInteractive: true })

  const p = await $.prompt.submit({ text: 'ciao' })
  expect('drop' in p).toBe(true)
  const w = await $.tool.call({ tool: 'Write', file_path: 'C:\\x.txt', content: 'Egregio PERS_0001' })
  expect('deny' in w).toBe(true)
  expect(chiamato).toBe(false)
  const a = await $.session.append({ message: { type: 'user', content: [{ type: 'text', text: 'nota su Giacomo Bertolazzi' }] } })
  expect('message' in a && JSON.stringify(a.message.content)).not.toContain('Bertolazzi')
})
