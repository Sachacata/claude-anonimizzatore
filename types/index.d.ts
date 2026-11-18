export type Contatori = {
  righe: number        // righe della conversazione filtrate (con almeno una sostituzione)
  sostituzioni: number // dati personali sostituiti da token
  ripristini: number   // token rimessi in chiaro negli input degli strumenti locali
  bloccate: number     // letture dirette di file binari negate
}

// Lo scudo nella barra sotto il prompt: 'attivo' = progetto protetto e servizio
// che risponde; 'fermo' = progetto protetto ma servizio non raggiungibile
// (tutto trattenuto); 'spento' = filtro non attivo in questa sessione (la barra
// mostra il pulsante per accenderlo).
export type StatoScudo = 'spento' | 'attivo' | 'fermo'

// L'interruttore della sessione, mosso dal pulsante nella barra o da
// `/filtro acceso|spento|predefinito`. 'predefinito' = decide il file
// `.filtro-pii.json` del progetto; 'acceso' e 'spento' lo scavalcano per questa
// sessione soltanto. `radiceToken` ricorda il progetto in cui il filtro è stato
// attivo: dopo uno spegnimento i token già in conversazione vengono ancora
// rimessi in chiaro negli strumenti locali.
export type SceltaFiltro = 'predefinito' | 'acceso' | 'spento'
export type Interruttore = { scelta: SceltaFiltro; radiceToken: string | null }

declare module 'claude-code' {
  interface PluginState {
    'filtro-pii': {
      scudo: StatoScudo
      interruttore: Interruttore
      contatori:Contatori
    }
  }
}
