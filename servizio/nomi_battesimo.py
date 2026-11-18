"""
nomi_battesimo.py — elenco di nomi di battesimo italiani (tutto minuscolo).

Serve al motore per riconoscere i nominativi scritti tutti in minuscolo
(«ha chiamato bortolan ginevra»), che né le regex né spaCy prendono.

NOMI_CERTI: nomi che in italiano non sono anche parole comuni.
NOMI_AMBIGUI: nomi che sono anche parole comuni («rosa», «franco», «viola»):
valgono solo se spaCy conferma che la coppia è una persona.
I nomi che sono parole frequentissime («mia», «nella», «pia») sono lasciati
fuori apposta: farebbero scattare il controllo a ogni riga.
"""

NOMI_CERTI = frozenset(p for p in """
abramo achille adele adelaide adelina adelmo adolfo adriana adriano agata agnese agostino aida
alan alba_ alberta alberto albino alda aldo alessandra alessandro alessia alessio alex alfio alfonso
alfredo alice alida alina allegra_ amalia amedeo amelia amerigo amilcare anastasia andrea andreina
angela angelica angelina angelo anita anna annabella annalisa annamaria annarita annibale
anselmo antonella antonello antonia antonietta antonino antonio arcangelo arianna aristide armando
arnaldo aroldo arrigo artemio arturo attilio aurelia aurelio azzurra_
barbara bartolo bartolomeo battista beatrice benedetto beniamino benito beppe bernardo
bernardino berta bettina biagio bianca_ bibiana brigida brunella brunello brunilde
camilla camillo candida_ carla carlo carlotta carmela carmelo carmen carola carolina cassandra
caterina cecilia celestino cesare cesarina cesira chantal christian cinzia cipriano ciro clara
clarissa claudia claudio clelia clementina cleto clotilde consuelo corinna cornelio corrado cosimo
cristian cristiana cristiano cristina cristoforo
damiano dalila daniela daniele danilo dario davide debora deborah delia denis denise desiderio
diana diego dimitri dionisio domenico domitilla donatella donatello dorotea duilio
edda edgardo edmondo edoardo edvige egidio eleonora elena eliana eligio elio elisa elisabetta
elisea eliseo elvio elvira emanuela emanuele emilia emiliano emilio emma enea ennio enrica enrico
enzo erasmo ercole erica erika ermanno ermenegildo erminia erminio ernesta ernesto ersilia ester
ettore eugenia eugenio eusebio evaristo evelina ezio
fabia fabiana fabiano fabio fabiola fabrizia fabrizio fausta faustino federica federico fedora
felicia feliciano felicita ferdinando fernanda fernando ferruccio filiberto filippa filippo
filomena fiorenza flavia flavio flora floriana floriano fortunata francesca francesco
fulvia fulvio
gabriele gabriella gaetana gaetano gaia gaspare gastone gennaro genoveffa gerardo germana germano
gervasio giacinta giacinto giacomo giada giampaolo giampiero gian giancarlo gianfranco gianluca
gianluigi gianmarco gianmaria gianna gianni giannina gianpaolo gianpiero gigliola gilberto gilda
gildo gina ginevra gino gioacchino giordano giorgia giorgio giosuè giovanna giovanni giovannino
girolamo gisella giuditta giulia giuliana giuliano giulio giuseppa giuseppe giuseppina glauco
gloria goffredo graziano graziella gregorio greta guendalina guglielmo guerrino gustavo
iacopo ignazio igor ilaria ilario ileana ilenia imelda ines innocenzo iolanda ippolito irene
irma isabella isacco isidoro ivan ivana ivano ivo
jacopo jessica jolanda jonathan
katia ketty kevin
lamberto lara laura lauretta lavinia lazzaro leandro leonardo leonello leonida leonilde leopoldo
letizia liana lidia liliana linda lisa livia livio lodovico loredana lorella lorena lorenza
lorenzo loretta loris luana luca lucia luciana luciano lucilla lucio lucrezia ludovica ludovico
luigi luigia luigina luisa luisella
maddalena mafalda manlio manuel manuela manuele mara marcella marcello marco margherita_
maria marianna mariano mariangela mariarosa mariella marilena marina_ marinella mario marisa
marta martina martino marzia massimiliano massimiliana matilde matteo mattia maura maurizia
maurizio mauro melania melissa michela michelangelo michele michelina milena mirco mirella miriam
mirko mirta moira monica morena moreno
nadia natalia natalina natalino natascia nazario nazzareno nello nerina nerio nevio niccolò
nicla nico nicola nicoletta nicolò nilde nino nives noemi nora norberto norina
oddone odoardo ofelia olga olimpia olindo olivia oliviero ombretta omar onofrio orazio oreste
oriana orietta orlando ornella orsola osvaldo otello ottavia ottaviano ottavio ottorino
pamela paola paolina paolino paolo pasqua_ pasquale pasqualina patrizia patrizio pierangelo
piera pierina pierino pierluigi piermario piero pierpaolo pietro pompeo priscilla
quinto_ quirino
rachele raffaela raffaele raffaella raimondo ramona raniero raoul raul rebecca remigio renata
renato renzo riccarda riccardo rinaldo rino rita roberta roberto rocco rodolfo rolando romana_
romeo romilda romina romolo romualdo rosalba rosalia rosalinda rosanna rosaria rosario rosella
rosetta rosina rossana rossella ruggero
sabina sabrina salvatore samanta samantha samuele sandra sandro sante santina santino sara saverio
sebastiana sebastiano selene serafina serafino sergio settimio severino sibilla silvana silvano
silvestro silvia silvio simona simone simonetta siro sofia sonia stefania stefano susanna sveva
tamara tancredi tarcisio tatiana teodora teodoro teresa teresina thomas tiberio tiziana tiziano
tobia tommasa tommaso tonino tosca tullia tullio
ubaldo uberto ugo ulderico ulisse umberta umberto
valentina valentino valeria valeriano valerio vanda vanessa vania vanna vasco velia venanzio
veronica vilma vincenza vincenzo vinicio virgilio virginia virginio vitaliano vito vittoria_
vittorina vittorino vittorio viviana vladimiro
walter wanda william wilma
ylenia yuri
zaccaria zaira zeno zita zoe
""".split() if not p.endswith("_"))  # «nome_» = spostato tra gli ambigui o escluso

NOMI_AMBIGUI = frozenset("""
alba allegra amato angelo aurora azzurra beato bianca bruna bruno candida celeste chiara clemente
costante costanza dante donato dino fausto felice fiorella fiorenzo franca franco gemma grazia
guido leone libero lino margherita marina massimo modesto natale perla pino placido regina remo
rosa romana romano salvo santo serena severo stella viola vittoria
""".split())

# Particelle dei cognomi composti («de luca», «dalla costa»).
PARTICELLE = frozenset("de di da del della dello dei degli dal dalla dalle lo la li".split())

# Parole comuni che possono trovarsi accanto a un nome senza essere un cognome.
PAROLE_COMUNI = frozenset("""
a ad al alla alle allo ai agli anche ancora appena avere aveva avrà abbia
ben bene buon buona buongiorno
che chi ci ciao come con contro cosa così cui
da dal dalla dei del della delle dello detto deve di dice dopo dove dovrà due
e ed è era ecco entro
fa fatto fino fra fu
già gli grazie
ha hai hanno ho
ieri il in infatti inoltre invece io
la le lei li lo loro lui
ma mai me mentre mi mio mia molto
ne né nei nel nella nelle nello no noi non nostro nulla
o oggi ogni oltre ora oppure
per perché però più poi può prima
qua quale quando quanto quel quella quello questa questo qui quindi
sa sarà se sé sei sempre senza si sì sia solo sono sopra sotto sta stato stata su sua sue sul sulla suo suoi
tra tu tua tuo tutta tutte tutti tutto
un una uno
va vi via viene voi vuole
chiamato chiamata scritto scritta telefonato risposto chiesto mandato inviato ricevuto firmato
arriva arrivato arrivata viene venuto venuta parla parlato dice diceva chiede vuole deve
signor signora signore dottor dottore dottoressa avvocato avvocata collega colleghi
lunedì martedì mercoledì giovedì venerdì sabato domenica domani stamattina stasera
""".split())


# Capoluoghi di provincia: una parola nota che è anche una città («Verona»,
# «Trento») non si maschera quando è da sola, altrimenti «UAT Verona» o
# «Tribunale di Padova» diventerebbero illeggibili. Con nome e cognome
# insieme la persona si maschera comunque.
CAPOLUOGHI = frozenset("""
agrigento alessandria ancona aosta arezzo ascoli asti avellino bari barletta belluno benevento
bergamo biella bologna bolzano brescia brindisi cagliari caltanissetta campobasso caserta catania
catanzaro chieti como cosenza cremona crotone cuneo enna fermo ferrara firenze foggia forlì forli
frosinone genova gorizia grosseto imperia isernia lecce lecco livorno lodi lucca macerata mantova
massa matera messina milano modena monza napoli novara nuoro oristano padova palermo parma pavia
perugia pesaro pescara piacenza pisa pistoia pordenone potenza prato ragusa ravenna reggio rieti
rimini roma rovigo salerno sassari savona siena siracusa sondrio taranto teramo terni torino
trapani trento treviso trieste udine varese venezia verbania vercelli verona vibo vicenza viterbo
bassano schio thiene valdagno arzignano
""".split())
