"""Rauchtest für den Griffbrett-Trainer (Ukulele und Gitarre) in einem echten Chrome mit simuliertem Mikrofon.

Aufruf:  python3 tests/smoke.py [Pfad/zu/index.html]
Braucht: Python-Paket `playwright` und einen installierten Google Chrome (Pfad unten anpassen).
Prüft Tabs, Karte, beide Quizformen, Statistik, Stimmgerät und das Spielen im Finden-Tab, danach die Gitarre.
"""
import math, os, struct, subprocess, sys, tempfile, time, wave
from playwright.sync_api import sync_playwright

CHROME = os.environ.get('CHROME', '/usr/bin/google-chrome')
APP = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), '..', 'index.html'))
PORT = 8791
tmp = tempfile.mkdtemp()

def make_wav(name, freq):
    """4 s Ton mit Obertönen (wie eine gezupfte Saite), Mono, 48 kHz."""
    path = os.path.join(tmp, name)
    sr = 48000
    w = wave.open(path, 'wb'); w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
    frames = []
    for i in range(sr * 4):
        t = i / sr
        v = 0.30*math.sin(2*math.pi*freq*t) + 0.15*math.sin(4*math.pi*freq*t) + 0.08*math.sin(6*math.pi*freq*t)
        frames.append(struct.pack('<h', int(v * 20000)))
    w.writeframes(b''.join(frames)); w.close()
    return path

results = []
def check(name, cond, info=''):
    results.append(bool(cond))
    print(('PASS ' if cond else 'FAIL ') + name + (f'  [{info}]' if info else ''))

def launch(p, wav):
    return p.chromium.launch(executable_path=CHROME, headless=True, args=[
        '--no-sandbox', '--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream',
        '--use-file-for-fake-audio-capture=' + wav])

def set_inst(pg, inst):
    """Instrument wählen: Einstellungen oben rechts öffnen, dann das Instrument antippen."""
    if pg.locator('[data-act="inst"]').count() == 0:
        pg.click('[data-act="settings"]')
    pg.click(f'[data-act="inst"][data-v="{inst}"]')

def go(pg, mode):
    """Öffnet eine Unterseite: erst die Gruppe, dann (falls nötig) den Unterreiter."""
    groups = {'map':'notes','find':'notes','name':'notes','cmap':'chords','cfind':'chords','cname':'chords','cplay':'chords','cdeg':'chords','tnotes':'notes','tscales':'scales','tchords':'chords','cbuild':'chords','cstep':'chords','path':'path',
              'smap':'scales','sfind':'scales','sname':'scales','splay':'scales','tune':'tune','stats':'stats'}
    pg.click(f'[data-act="grp"][data-v="{groups[mode]}"]')
    if pg.evaluate('state.mode') != mode:
        if pg.locator(f'[data-act="tab"][data-v="{mode}"]').count() == 0:
            pg.click('[data-act="tab"][data-practice="1"]')     # Übungen liegen hinter dem Reiter "Üben"
        pg.click(f'[data-act="tab"][data-v="{mode}"]')

def make_seq_wav(name, midis, dur=0.9):
    """Töne nacheinander (wie eine gespielte Tonleiter), Mono, 48 kHz."""
    path = os.path.join(tmp, name)
    sr = 48000
    w = wave.open(path, 'wb'); w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
    frames = []
    for m in midis:
        f = 440 * 2 ** ((m - 69) / 12)
        for i in range(int(sr * dur)):
            t = i / sr
            v = 0.30*math.sin(2*math.pi*f*t) + 0.15*math.sin(4*math.pi*f*t) + 0.08*math.sin(6*math.pi*f*t)
            frames.append(struct.pack('<h', int(v * 20000)))
    w.writeframes(b''.join(frames)); w.close()
    return path

def make_chord_wav(name, midis, dur=4.0):
    """Akkord: alle Töne gleichzeitig mit Obertönen (wie ein angeschlagener Akkord)."""
    path = os.path.join(tmp, name)
    sr = 48000
    w = wave.open(path, 'wb'); w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
    fr = [440 * 2 ** ((m - 69) / 12) for m in midis]
    frames = []
    for i in range(int(sr * dur)):
        t = i / sr
        v = sum(0.12*math.sin(2*math.pi*f*t) + 0.06*math.sin(4*math.pi*f*t) + 0.03*math.sin(6*math.pi*f*t) for f in fr)
        frames.append(struct.pack('<h', int(v * 20000)))
    w.writeframes(b''.join(frames)); w.close()
    return path

def new_page(browser, errors, bad):
    ctx = browser.new_context(viewport={'width': 390, 'height': 800}, permissions=['microphone'])
    pg = ctx.new_page()
    pg.on('pageerror', lambda e: errors.append(str(e)))
    pg.on('console', lambda m: errors.append(m.text) if m.type == 'error' else None)
    pg.on('response', lambda r: bad.append((r.status, r.url)) if r.status >= 400 else None)
    pg.goto(f'http://localhost:{PORT}/{os.path.basename(APP)}')
    pg.wait_for_selector('.tab')
    return pg

srv = subprocess.Popen([sys.executable, '-m', 'http.server', str(PORT), '--directory', os.path.dirname(APP)],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(1)
try:
    a440 = make_wav('a440.wav', 440.0)      # leere A-Saite, genau gestimmt
    c_flat = make_wav('c255.wav', 255.0)    # C-Saite etwa 44 Cent zu tief
    with sync_playwright() as p:
        errors, bad = [], []
        b = launch(p, a440)
        pg = new_page(b, errors, bad)

        for v in ['path', 'map', 'tnotes', 'find', 'name', 'cmap', 'cdeg', 'tchords', 'cbuild', 'cstep', 'cfind', 'cname', 'cplay', 'smap', 'tscales', 'sfind', 'sname', 'splay', 'tune', 'stats']:
            go(pg, v)
            check('Seite ' + v, pg.evaluate('state.mode') == v and pg.locator('#root .card, #root svg').count() > 0)

        go(pg, 'map')
        expected = pg.evaluate("(function(){var c=0;for(var s=0;s<4;s++)for(var f=0;f<=5;f++)if(isNat(noteAt(s,f)))c++;return c})()")
        check('Karte zeigt alle Naturtöne Bund 0-5', pg.locator('.dot').count() == expected, f'{expected} erwartet')

        go(pg, 'find')
        pg.evaluate("state.q={s:1,f:2,n:noteAt(1,2),done:false,ok:false,picked:null,id:1};render()")
        pg.click('rect.hit[data-s="1"][data-f="2"]')
        check('Finden: richtige Stelle', pg.evaluate("state.q.ok===true"))
        pg.wait_for_timeout(1100)
        check('Finden: springt weiter', pg.evaluate("state.q.done===false"))
        pg.evaluate("state.q={s:1,f:2,n:noteAt(1,2),done:false,ok:false,picked:null,id:2};render()")
        pg.click('rect.hit[data-s="2"][data-f="1"]')
        check('Finden: falsche Stelle zeigt Weiter', pg.evaluate("state.q.done&&!state.q.ok") and pg.locator('[data-act="next"]').count() == 1)

        go(pg, 'name')
        pg.evaluate("state.q={s:0,f:2,n:noteAt(0,2),done:false,ok:false,picked:null,id:3};render()")
        pg.click('.ans .btn:text-is("A")')
        check('Erkennen: A auf G-Saite Bund 2', pg.evaluate("state.q.ok===true"))
        pg.wait_for_timeout(1100)
        check('Erkennen: springt weiter', pg.evaluate("state.q.done===false"))

        pg.click('[data-v="stats"]')
        check('Statistik zeigt Töne', pg.locator('.row').count() >= 1)
        check('Statistik wird gespeichert', pg.evaluate("JSON.parse(localStorage.getItem('ukulele-trainer-v1')).total") >= 3)

        pg.click('[data-v="tune"]'); pg.click('[data-act="mic"]'); pg.wait_for_timeout(2500)
        check('Stimmgerät erkennt A', pg.inner_text('#tn-note') == 'A', pg.inner_text('#tn-hz'))
        check('Stimmgerät: gestimmt', pg.inner_text('#tn-msg') == 'Gestimmt!', pg.inner_text('#tn-msg'))
        pg.click('[data-act="mic"]')
        check('Mikrofon lässt sich stoppen', pg.evaluate("state.mic.on===false"))

        go(pg, 'find')
        pg.evaluate("state.q={s:1,f:0,n:0,done:false,ok:false,picked:null,id:5};render()")   # Ziel C, gespielt wird A
        pg.click('[data-act="mic"]'); pg.wait_for_timeout(2500)
        check('Finden mit Mikrofon: falscher Ton zählt nicht', pg.evaluate("state.q.id===5&&state.q.done===false"))
        c0 = pg.evaluate("stats.correct")
        pg.evaluate("state.q={s:3,f:0,n:9,done:false,ok:false,picked:null,id:9};state.mic.stable=0;state.mic.cool=0;render()")
        pg.wait_for_timeout(900)
        check('Finden mit Mikrofon: richtiger Ton zählt', pg.evaluate("stats.correct")==c0+1 and pg.evaluate("state.q.id===9&&state.q.ok"))

        check('Keine Fehler in der Konsole', not errors, str(errors[:3]))
        check('Keine fehlgeschlagenen Anfragen', not bad, str(bad[:3]))
        b.close()

        b = launch(p, c_flat)
        pg = new_page(b, [], [])
        pg.click('[data-v="tune"]'); pg.click('[data-act="mic"]'); pg.wait_for_timeout(2500)
        check('Stimmgerät: zu tiefe C-Saite', pg.inner_text('#tn-note') == 'C' and 'Zu tief' in pg.inner_text('#tn-msg'), pg.inner_text('#tn-msg'))
        b.close()

        # --- Gitarre ---
        e2 = make_wav('e2.wav', 82.41)      # tiefe E-Saite
        h3 = make_wav('h3.wav', 246.94)     # H-Saite
        e4 = make_wav('e4.wav', 329.63)     # hohe e-Saite
        d3 = make_wav('d3.wav', 146.83)     # D-Saite
        for wav, note, label in [(e2, 'E', 'tiefes E'), (h3, 'H', 'H'), (e4, 'e', 'hohes e')]:
            b = launch(p, wav)
            errors, bad = [], []
            pg = new_page(b, errors, bad)
            set_inst(pg, 'gtr')
            pg.click('[data-v="tune"]'); pg.click('[data-act="mic"]'); pg.wait_for_timeout(3000)
            check('Gitarre Stimmgerät: ' + label, pg.inner_text('#tn-note') == note and pg.inner_text('#tn-msg') == 'Gestimmt!',
                  pg.inner_text('#tn-note') + ' / ' + pg.inner_text('#tn-hz') + ' / ' + pg.inner_text('#tn-msg'))
            b.close()

        b = launch(p, d3)
        errors, bad = [], []
        pg = new_page(b, errors, bad)
        set_inst(pg, 'gtr')
        go(pg, 'map')
        check('Gitarre: 6 Saiten auf der Karte', pg.evaluate("STR.length")==6 and pg.locator('rect.hit').count()==6*6)
        expected = pg.evaluate("(function(){var c=0;for(var s=0;s<6;s++)for(var f=0;f<=5;f++)if(isNat(noteAt(s,f)))c++;return c})()")
        check('Gitarre: Karte zeigt alle Naturtöne', pg.locator('.dot').count() == expected, f'{expected} erwartet')
        check('Gitarre: eigene Statistik', pg.evaluate("stats.total")==0)
        check('Gitarre: Auswahl bleibt nach Neuladen', (pg.reload() or True) and pg.evaluate("state.inst")=='gtr')
        go(pg, 'find')
        pg.evaluate("state.q={s:2,f:0,n:2,done:false,ok:false,picked:null,id:11};render()")  # D auf der D-Saite
        pg.click('[data-act="mic"]'); pg.wait_for_timeout(2500)
        check('Gitarre Finden mit Mikrofon: D-Saite', pg.evaluate("stats.correct")>=1 and pg.evaluate("state.q.id!==11||state.q.ok"))
        set_inst(pg, 'uke')
        check('Wechsel zur Ukulele stoppt Mikrofon', pg.evaluate("state.mic.on===false&&STR.length===4"))
        check('Gitarre/Ukulele: keine Konsolenfehler', not errors, str(errors[:3]))
        b.close()

        # Einstellungen oben rechts: Instrument nur dort wählbar
        b = launch(p, a440)
        pg = new_page(b, [], [])
        check('Instrumentwahl ist zunächst versteckt', pg.locator('[data-act="inst"]').count() == 0 and pg.locator('.gear').count() == 1)
        box = pg.locator('.gear').bounding_box()
        check('Zahnrad sitzt oben rechts', box['x'] > 390 - 80 and box['y'] < 80, str(box))
        fork = pg.locator('.fork').bounding_box()
        check('Stimmgabel sitzt links neben dem Zahnrad', fork['x'] + fork['width'] <= box['x'] and abs(fork['y'] - box['y']) < 2 and pg.locator('.fork svg').count() == 1, str(fork))
        check('Stimmen ist kein Reiter mehr', pg.locator('.tabs.top .tab[data-v="tune"]').count() == 0 and pg.locator('.tabs.top .tab').count() == 5)
        pg.click('.fork')
        check('Stimmgabel öffnet das Stimmgerät', pg.evaluate("state.mode")=='tune' and pg.locator('#tn-note').count() == 1 and pg.locator('.fork.on').count() == 1)
        pg.click('[data-act="settings"]')
        check('Einstellungen zeigen beide Instrumente', pg.locator('[data-act="inst"]').count() == 2)
        pg.click('[data-act="inst"][data-v="gtr"]')
        check('Auswahl schließt die Einstellungen', pg.locator('[data-act="inst"]').count() == 0 and pg.evaluate("state.inst")=='gtr' and pg.inner_text('h1') == 'Gitarre' and 'Griffbrett-Trainer' not in pg.inner_text('#root'))
        pg.click('[data-act="settings"]')
        check('Einstellungen zeigen die Version', 'Version 1.' in pg.inner_text('#root') and 'Stand der App' not in pg.inner_text('#root'))
        check('Ton-Schalter in den Einstellungen', pg.locator('input[data-act="sound"]').count() == 1 and pg.evaluate("state.sound") is True)
        pg.uncheck('input[data-act="sound"]')
        check('Ton lässt sich ausschalten und bleibt nach Neuladen aus', pg.evaluate("state.sound") is False and (pg.reload() or True) and pg.evaluate("state.sound") is False)
        pg.click('[data-act="settings"]'); pg.check('input[data-act="sound"]')
        check('Ton wieder einschalten', pg.evaluate("state.sound") is True and pg.evaluate("localStorage.getItem('griffbrett-sound')")=='1')
        go(pg, 'map')
        check('Bereichsauswahl hat keinen Ton-Schalter mehr', pg.locator('input[data-act="sound"]').count() == 0)
        pg.click('[data-act="settings"]'); pg.click('[data-act="grp"][data-v="notes"]')
        check('Seitenwechsel schließt die Einstellungen', pg.locator('[data-act="inst"]').count() == 0)
        b.close()

        # --- Akkorde und Tonleitern (Ukulele, dann Gitarre) ---
        b = launch(p, a440)
        errors, bad = [], []
        pg = new_page(b, errors, bad)
        # Griffe: jeder Griff muss genau die Töne seines Akkords enthalten (Grundton, Terz, Quinte, ggf. Septime)
        chk = pg.evaluate("""(function(){var bad=[];
          Object.keys(INSTR).forEach(function(id){useInstrument(id);INSTR[id].chords.forEach(function(c){
            var ns=[];c.f.forEach(function(f,s){if(f>=0){var n=noteAt(s,f);if(ns.indexOf(n)<0)ns.push(n);}});
            var want=[c.r,(c.r+((c.q==='m'||c.q==='dim')?3:4))%12,(c.r+(c.q==='dim'?6:7))%12].concat(c.q==='7'?[(c.r+10)%12]:[]);
            // Beim Septakkord darf die Quinte fehlen (Standardgriff C7 auf der Gitarre: x32310)
            var wantNoFifth=want.filter(function(n){return !(c.q==='7'&&n===(c.r+7)%12);});
            var okSet=ns.slice().sort().join()===want.slice().sort().join()||(c.q==='7'&&ns.slice().sort().join()===wantNoFifth.slice().sort().join());
            if(!okSet)bad.push(id+' '+c.n+' Töne '+ns);
            if(c.f.length!==STR.length)bad.push(id+' '+c.n+' Länge');
            var first=c.f.findIndex(function(f){return f>=0;});
            if(noteAt(first,c.f[first])!==c.r&&!(id==='uke'))bad.push(id+' '+c.n+' Bass nicht Grundton');
          });});useInstrument('uke');return bad;})()""")
        check('Alle Akkordgriffe enthalten genau die richtigen Töne', chk == [], str(chk))
        go(pg, 'cmap')
        pf = pg.locator('.stickyfb .play'); fb = pg.locator('.stickyfb svg.fb-svg')
        pfb, fbb = pf.bounding_box(), fb.bounding_box()
        check('Akkordkarte: Play-Knopf im Griffbrett oben links, kein Name-Feld', pf.count() == 1 and pfb['x'] < fbb['x'] + 80 and pfb['y'] < fbb['y'] + 60 and pg.locator('.titlerow').count() == 0 and 'Anschlagen' not in pg.inner_text('#root'), str((pfb, fbb)))
        pg.evaluate("(function(){window.__seq=0;var o=window.playSeq;window.playSeq=function(f,m){window.__seq=f.length;return o(f,m)}})()")
        pg.click('.stickyfb .play')
        check('Akkordkarte: Play-Knopf schlägt den Akkord an', pg.evaluate("window.__seq") == 4)
        check('Akkordkarte: ein Punkt je Saite', pg.locator('.dot').count() == 4, str(pg.locator('.dot').count()))
        go(pg, 'cfind')
        pg.evaluate("state.q={i:0,fing:[0,0,0,0],done:false,ok:false,picked:null,id:21};render()")   # C-Dur
        pg.click('rect.hit[data-s="3"][data-f="3"]')
        pg.click('[data-act="cchk"]')
        check('Greifen: C-Dur richtig', pg.evaluate("state.q.ok===true"))
        pg.evaluate("state.q={i:0,fing:[0,0,0,0],done:false,ok:false,picked:null,id:22};render()")
        pg.click('[data-act="cchk"]')
        check('Greifen: leere Saiten sind falsch', pg.evaluate("state.q.done&&!state.q.ok") and 'Richtig wäre' in pg.inner_text('.fb'))
        go(pg, 'cname')
        pg.evaluate("state.q={i:21,fing:[],done:false,ok:false,picked:null,id:23};render()")          # A-Moll
        pg.click('.ans .btn:text-is("Am")')
        check('Akkord erkennen: Am', pg.evaluate("state.q.ok===true&&stats.chords.Am.c===1"))
        # Tonart wählen: nur passende Akkorde (C-Dur auf der Ukulele: C Am F G G7 Dm Em)
        go(pg, 'cmap')
        pg.select_option('select[data-act="kroot"]', '0'); pg.select_option('select[data-act="ktype"]', '0')
        names = pg.evaluate("chordsInKey().inKey.map(function(k){return INSTR.uke.chords[k].n}).sort().join(' ')")
        check('Tonart C-Dur: passende Akkorde', names == 'Am C Dm Em F G G7 H°', names)
        check('Karte gruppiert (In C-Dur, Weitere eingeklappt)', 'In C-Dur' in pg.inner_text('#root') and pg.locator('[data-act="more"]').count() == 1 and pg.locator('[data-act="csel"]').count() == 8)
        pg.click('[data-act="more"]')
        check('Weitere Akkorde klappen als Knöpfe auf (gleiches Design)', pg.locator('[data-act="csel"]').count() == 48 and pg.locator('[data-act="csel"]').nth(1).evaluate("e=>e.className")==pg.locator('[data-act="csel"]').last.evaluate("e=>e.className"))
        pg.click('[data-act="csel"]:text-is("D")')
        check('Weiterer Akkord per Knopf wählbar', pg.evaluate("INSTR.uke.chords[state.cSel].n")=='D')
        pg.click('[data-act="more"]')
        check('Weitere Akkorde lassen sich wieder einklappen', pg.locator('[data-act="csel"]').count() == 8)
        go(pg, 'cname')
        check('Akkord erkennen: nur passende Antworten', pg.locator('.ans .btn').count() == 8, str(pg.locator('.ans .btn').count()))
        drawn = pg.evaluate("(function(){var s={};for(var i=0;i<60;i++){newChordQ();s[INSTR.uke.chords[state.q.i].n]=1;}return Object.keys(s).sort().join(' ')})()")
        check('Akkord-Aufgaben nur aus der Tonart', set(drawn.split()) <= set('Am C Dm Em F G G7 H°'.split()), drawn)
        pg.select_option('select[data-act="kroot"]', '-1')
        # Stufenakkorde: Aufbau der Dreiklänge aus der Tonleiter
        tri = pg.evaluate("""(function(){function s(r,t){return [0,1,2,3,4,5,6].map(function(d){var x=triadAt(r,t,d);return x.roman+' '+x.name;}).join(', ');}
          return [s(0,0),s(9,1)];})()""")
        check('Stufenakkorde C-Dur', tri[0] == 'I C, ii Dm, iii Em, IV F, V G, vi Am, vii° H°', tri[0])
        check('Stufenakkorde A-Moll', tri[1] == 'i Am, ii° H°, III C, iv Dm, v Em, VI F, VII G', tri[1])
        go(pg, 'cdeg')
        pg.select_option('select[data-act="kroot"]', '0'); pg.select_option('select[data-act="ktype"]', '0')
        check('Stufen-Übersicht: 7 Zeilen', pg.locator('[data-act="dsel"]').count() == 7)
        pg.click('[data-act="dsel"][data-v="3"]')
        check('Stufe IV zeigt F mit Griff', pg.evaluate("INSTR.uke.chords[state.cSel].n")=='F' and pg.locator('.dot').count() == 4, str(pg.locator('.dot').count()))
        pg.click('[data-act="dsel"][data-v="6"]')
        check('Stufe vii° zeigt H° mit Griff', pg.evaluate("INSTR.uke.chords[state.cSel].n")=='H°' and pg.locator('.dot').count() >= 3, str(pg.locator('.dot').count()))
        go(pg, 'cbuild')
        pg.evaluate("state.kRoot=0;state.kType=0;state.q={kind:'build',root:0,t:0,d:1,tri:triadAt(0,0,1),sel:[],done:false,ok:false,picked:null,id:81};render()")   # ii in C-Dur = Dm
        for n in ('D', 'F'):
            pg.click(f'.ans .btn:text-is("{n}")')
        pg.click('.ans .btn:text-is("G")')
        pg.click('.ans .btn:text-is("G")')   # wieder abwählen
        pg.click('.ans .btn:text-is("A")')
        pg.click('[data-act="bchk"]')
        check('Akkord bauen: Dm aus C-Dur', pg.evaluate("state.q.ok===true&&stats.degrees['Dur ii'].c===1"))
        pg.evaluate("state.q={kind:'build',root:0,t:0,d:1,tri:triadAt(0,0,1),sel:[],done:false,ok:false,picked:null,id:82};render()")
        for n in ('D', 'Fis/Ges', 'A'):
            pg.click(f'.ans .btn:text-is("{n}")')
        pg.click('[data-act="bchk"]')
        check('Akkord bauen: falsche Töne', pg.evaluate("state.q.done&&!state.q.ok") and 'Richtig wäre' in pg.inner_text('.fb'))
        go(pg, 'cstep')
        pg.evaluate("state.q={kind:'step',root:0,t:0,d:5,tri:triadAt(0,0,5),form:0,done:false,ok:false,picked:null,id:83};render()")   # Am in C-Dur = vi
        pg.click('.ans .btn:text-is("vi")')
        check('Stufe erkennen: Am ist vi', pg.evaluate("state.q.ok===true"))
        pg.evaluate("state.q={kind:'step',root:7,t:0,d:3,tri:triadAt(7,0,3),form:1,done:false,ok:false,picked:null,id:84};render()")   # IV in G-Dur = C
        check('Frage nach Akkord der IV. Stufe', 'IV. Stufe von G-Dur' in pg.inner_text('.card .prompt'))
        pg.click('.ans .btn:text-is("C")')
        check('Akkord zur Stufe: IV in G-Dur ist C', pg.evaluate("state.q.ok===true"))
        pg.select_option('select[data-act="kroot"]', '-1')
        go(pg, 'path')
        check('Lernpfad zeigt 3 Stufen', pg.locator('.stage').count() == 3 and 'Als Nächstes' in pg.inner_text('#root'))
        txt = pg.inner_text('#root')
        check('Lernpfad: Schritte statt Stufen, Sterne je Übung', 'Schritt 1 · Töne' in txt and 'Stufe 1' not in txt and '0 von 2 Übungen bestanden' in txt and 'Finden ☆☆☆ · Erkennen ☆☆☆' in txt and 'Bonus: Spielen' in txt and 'Ganzton' not in txt and 'Du lernst, wo welcher Ton' in txt and '(' not in txt.split('Zwischentöne')[-1][:3])
        go(pg, 'name')
        first = pg.locator('[data-act="ans"]').first.inner_text(); last = pg.locator('[data-act="ans"]').last.inner_text()
        check('Töne erkennen: Antworten beginnen mit A', first == 'A' and last == 'G', first + ' ' + last)
        # Antwort sprechen
        P = lambda s: pg.evaluate("JSON.stringify(voiceParse(%r))" % s)
        import json as _j
        pr = {s: _j.loads(P(s)) for s in ['Fis', 'A-Moll', 'C-Dur', 'G7', 'G sieben', 'H vermindert', 'Cis Moll', 'vier', 'es ist ein C', 'c e g', 'weiter', 'amoll', 'B']}
        check('Sprache: Tonnamen', pr['Fis']['pcs'] == [6] and pr['es ist ein C']['pcs'][-1] == 0 and pr['c e g']['pcs'] == [0, 4, 7] and pr['B']['pcs'] == [10], str(pr['Fis']))
        check('Sprache: Akkord-Art', pr['A-Moll']['qual'] == 'm' and pr['A-Moll']['pcs'] == [9] and pr['C-Dur']['qual'] == '' and pr['G7']['qual'] == '7' and pr['G7']['pcs'] == [7] and pr['H vermindert']['qual'] == 'dim' and pr['Cis Moll']['pcs'] == [1] and pr['amoll']['pcs'] == [9] and pr['amoll']['qual'] == 'm', str(pr['G7']))
        check('Sprache: Zahl und Befehl', pr['vier']['num'] == 4 and pr['G sieben']['num'] == 7 and pr['weiter']['next'] is True)
        pa = {x: _j.loads(P(x)) for x in ['Cäsar', 'Cäsar erhöht', 'Emil erniedrigt', 'Anton Moll', 'Gustav sieben', 'Berta', 'Heinrich vermindert']}
        check('Sprache: Buchstabier-Namen', pa['Cäsar']['pcs'] == [0] and pa['Cäsar erhöht']['pcs'] == [1] and pa['Emil erniedrigt']['pcs'] == [3] and pa['Anton Moll']['pcs'] == [9] and pa['Anton Moll']['qual'] == 'm' and pa['Gustav sieben']['pcs'] == [7] and pa['Berta']['pcs'] == [10] and pa['Heinrich vermindert']['qual'] == 'dim', str(pa))
        go(pg, 'name')
        pg.evaluate("state.sharps=false;state.q=null;render()")
        w1 = pg.evaluate("voiceWords().join(' ')")
        pg.evaluate("state.sharps=true;state.q=null;render()")
        w2 = pg.evaluate("voiceWords().join(' ')")
        pg.evaluate("state.sharps=false;state.q=null;render()")
        check('Sprache: Vokabular nur aus sichtbaren Antworten (kein B ohne Zwischentöne)', w1 == 'a h c d e f g h h weiter [unk]' and ' b ' in w2 and 'cis' in w2, w1)
        check('Sprechen-Knopf in Antwort-Übungen', pg.locator('[data-act="voice"]').count() == 1)
        pg.evaluate("state.q={s:1,f:2,n:2,done:false,ok:false,picked:null,id:1};render();voiceHeard('D')")
        check('Sprache: Ton erkennen richtig', pg.evaluate("state.q.done&&state.q.ok"))
        pg.evaluate("state.q={s:1,f:2,n:2,done:false,ok:false,picked:null,id:2};render();voiceHeard('E')")
        check('Sprache: falscher Ton zählt als falsch', pg.evaluate("state.q.done&&!state.q.ok&&state.q.picked===4"))
        pg.evaluate("voiceHeard('weiter')")
        check('Sprache: weiter', pg.evaluate("state.q.done===false"))
        go(pg, 'cname')
        pg.evaluate("state.kRoot=-1;state.q={i:chordIndexOf(9,'m'),fing:[0,0,0,0],done:false,ok:false,picked:null,id:3};render();voiceHeard('A-Moll')")
        check('Sprache: Akkord erkennen', pg.evaluate("state.q.done&&state.q.ok"))
        pg.evaluate("state.q={i:chordIndexOf(7,'7'),fing:[0,0,0,0],done:false,ok:false,picked:null,id:4};render();voiceHeard('G sieben')")
        check('Sprache: G sieben', pg.evaluate("state.q.done&&state.q.ok"))
        go(pg, 'cstep')
        pg.evaluate("state.q={kind:'step',root:0,t:0,d:3,tri:triadAt(0,0,3),form:0,done:false,ok:false,picked:null,id:5};render();voiceHeard('vier')")
        check('Sprache: Stufe als Zahl', pg.evaluate("state.q.done&&state.q.ok"))
        pg.evaluate("state.q={kind:'step',root:0,t:0,d:1,tri:triadAt(0,0,1),form:1,done:false,ok:false,picked:null,id:6};render();voiceHeard('D-Moll')")
        check('Sprache: Akkord zur Stufe', pg.evaluate("state.q.done&&state.q.ok"))
        go(pg, 'cbuild')
        pg.evaluate("state.q={kind:'build',root:0,t:0,d:0,tri:triadAt(0,0,0),sel:[],done:false,ok:false,picked:null,id:7};render();voiceHeard('C');voiceHeard('E G')")
        check('Sprache: Dreiklang bauen', pg.evaluate("state.q.done&&state.q.ok"), pg.evaluate("JSON.stringify(state.q.sel)"))
        go(pg, 'find')
        check('Kein Sprechen-Knopf bei Finden', pg.locator('[data-act="voice"]').count() == 0)
        # Tonleitern: kein Schalter für Zwischentöne, Grundton-Auswahl stattdessen im Menü
        cnt = []
        for m in ['smap', 'sfind', 'sname']:
            go(pg, m); cnt.append(pg.locator('input[data-act="sharps"]').count())
        go(pg, 'sfind')
        check('Tonleitern ohne Zwischentöne-Schalter', cnt == [0, 0, 0] and pg.locator('select[data-act="range"]').count() == 1 and 'alle 12' in pg.inner_text('select[data-act="proot"]'), str(cnt))
        rr = pg.evaluate("(function(){var o={};[-1,-2].forEach(function(p){state.pRoot=p;state.pType=0;state.mode='sfind';var u={};for(var i=0;i<60;i++){newForMode();u[state.q.root]=1;}o[p]=Object.keys(u).length;});state.pRoot=-1;state.pType=-1;return [o[-1],o[-2]];})()")
        check('Grundton zufällig: 7 Stammtöne oder alle 12', rr == [7, 12], str(rr))
        # Positionen und Varianten beim Tonleiter-Spielen
        BOX = "(function(r,t,p){return STR.map(function(x,s){return scaleBox(r,SCALES[t],p).filter(function(d){return d.s===s}).map(function(d){return d.f}).join(',')}).join(' ')})"
        pg.evaluate("useInstrument('gtr')")
        b1 = pg.evaluate(BOX + "(9,3,2)"); b2 = pg.evaluate(BOX + "(0,0,3)")
        check('Position: A-Moll-Pentatonik 5. Bund (Gitarre)', b1 == '5,8 5,7 5,7 5,7 5,8 5,8', b1)
        check('Position: C-Dur 7. Bund (Gitarre)', b2 == '7,8,10 7,8,10 7,9,10 7,9,10 8,10 7,8,10', b2)
        badbox = pg.evaluate("""(function(){var bad=[];['uke','gtr'].forEach(function(id){useInstrument(id);for(var r=0;r<12;r++)SCALES.forEach(function(sc){for(var p=0;p<5;p++){var bx=scaleBox(r,sc,p),set=scaleNotes(r,sc),u={},lo=99,hi=0;bx.forEach(function(d){u[noteAt(d.s,d.f)]=1;if(set.indexOf(noteAt(d.s,d.f))<0)bad.push('fremd');lo=Math.min(lo,d.f);hi=Math.max(hi,d.f);});if(Object.keys(u).length!==set.length||hi-lo>5)bad.push(id+r+sc.id+p);for(var s=0;s<STR.length;s++){var c=bx.filter(function(d){return d.s===s}).length;if(c<2||c>3)bad.push(id+r+sc.id+p+'s'+s);}}});});useInstrument('uke');return bad;})()""")
        check('Alle Positionen: vollständig, nur Tonleitertöne, höchstens 5 Bünde, 2-3 Töne je Saite', badbox == [], str(badbox[:5]))
        go(pg, 'smap')
        pg.select_option('select[data-act="mpos"]', '2')
        lab = pg.evaluate("[].map.call(document.querySelectorAll('.fb-svg .hit'),function(e){return +e.getAttribute('data-f')}).filter(function(f){return f>0}).sort(function(a,b){return a-b})")
        check('Tonleiterkarte: Position zeigt Ausschnitt ab Bund 4', lab[0] == 4 and pg.locator('.dot').count() == 12, str(lab[:3]))
        pg.select_option('select[data-act="mpos"]', '-1')
        go(pg, 'splay')
        pg.select_option('select[data-act="proot"]', '0'); pg.select_option('select[data-act="ptype"]', '0')
        seqs = []
        for d in ['0', '1', '2']:
            pg.select_option('select[data-act="sdir"]', d); seqs.append(pg.evaluate("state.q.seq.join(' ')"))
        check('Spielen: auf, ab, auf und ab', seqs == ['0 2 4 5 7 9 11 0', '0 11 9 7 5 4 2 0', '0 2 4 5 7 9 11 0 11 9 7 5 4 2 0'], str(seqs))
        pg.select_option('select[data-act="sdir"]', '0'); pg.select_option('select[data-act="sstart"]', '1')
        st = pg.evaluate("(function(){var u={},ok=true;for(var i=0;i<14;i++){newForMode();var q=state.q;u[q.start]=1;if(q.seq[0]!==q.start||q.seq[q.seq.length-1]!==q.start||q.seq.length!==8)ok=false;}return [Object.keys(u).length,ok];})()")
        check('Spielen: Start auf wechselndem Ton', st == [7, True], str(st))
        pg.select_option('select[data-act="spos"]', '1')
        check('Spielen: Position zeigt Griffbrett und Titel', pg.locator('.fb-svg').count() == 1 and 'Position 2' in pg.inner_text('.card .prompt >> nth=-1'), pg.inner_text('#root')[-200:])
        pg.select_option('select[data-act="spos"]', '-1'); pg.select_option('select[data-act="sstart"]', '0')
        pg.select_option('select[data-act="proot"]', '-1'); pg.select_option('select[data-act="ptype"]', '-1')
        # Keine gleiche Aufgabe direkt hintereinander
        REP = "(function(mode,setup,key){setup();state.mode=mode;var prev=null,rep=0;for(var i=0;i<300;i++){newForMode();var k=key(state.q);if(k===prev)rep++;prev=k;}return rep;})"
        r1 = pg.evaluate(REP + "('sfind',function(){state.pRoot=0;state.pType=0},function(q){return q.s})")
        r2 = pg.evaluate(REP + "('sfind',function(){state.pRoot=-1;state.pType=-1},function(q){return q.s})")
        r3 = pg.evaluate(REP + "('sname',function(){state.pRoot=0;state.pType=0},function(q){return q.k})")
        r4 = pg.evaluate(REP + "('splay',function(){state.pRoot=-1;state.pType=-1},function(q){return q.root+':'+q.t})")
        r5 = pg.evaluate("(function(){state.pRoot=-1;state.pType=-1;state.mode='sname';var all=[],mx=0;for(var i=0;i<300;i++){newForMode();var q=state.q;all.push(scaleNotes(q.root,SCALES[q.t])[q.k-1]);}for(var i=0;i+10<=all.length;i++){var c={};all.slice(i,i+10).forEach(function(x){c[x]=(c[x]||0)+1;});for(var k in c)if(c[k]>mx)mx=c[k];}return mx;})()")
        check('Tonleitern erkennen: derselbe Ton höchstens 2-mal in 10 Aufgaben', r5 <= 2, str(r5))
        pg.evaluate("state.pRoot=-1;state.pType=-1;state.q=null;state.mode='path';render()")
        check('Tonleiter-Übungen: nie dieselbe Saite/Aufgabe direkt hintereinander', r1 == 0 and r2 == 0 and r3 == 0 and r4 == 0, str((r1, r2, r3, r4)))
        # Runden und Bewertung
        go(pg, 'find')
        check('Übung zeigt Rundenkarte mit Schwellen', 'Runde · 60 s' in pg.inner_text('#root') and '★★ ab 12' in pg.inner_text('#root'))
        pg.click('[data-act="rstart"]')
        check('Runde startet und zeigt Timer', pg.evaluate("state.round!==null") and pg.locator('#rbar').count() == 1)
        pg.evaluate("for(var i=0;i<12;i++)record(i%12,true);")
        check('Runde zählt richtige Antworten', pg.evaluate("state.round.ok")==12 and pg.evaluate("state.round.total")==12)
        pg.evaluate("finishRound()")
        check('Runde: 12 richtig = 2 Sterne, Ziel erreicht', pg.evaluate("state.roundResult.stars")==2 and 'Ziel erreicht' in pg.inner_text('#root') and pg.evaluate("stats.rounds.find.stars")==2, pg.evaluate("JSON.stringify(state.roundResult)"))
        pg.click('[data-act="rstart"]')
        pg.evaluate("for(var i=0;i<12;i++)record(i%12,true);for(var i=0;i<6;i++)record(i,false);finishRound()")
        check('Runde: unter 80 % richtig = 0 Sterne, Bestwert bleibt', pg.evaluate("state.roundResult.stars")==0 and pg.evaluate("stats.rounds.find.stars")==2)
        pg.click('[data-act="rstart"]'); go(pg, 'name')
        check('Seitenwechsel bricht die Runde ab', pg.evaluate("state.round")==None)
        pg.click('[data-act="rstart"]')
        pg.evaluate("for(var i=0;i<17;i++)record(i%12,true);finishRound()")
        check('Runde: 17 richtig bei Erkennen = 2 Sterne', pg.evaluate("stats.rounds.name.stars")==2)
        go(pg, 'path'); tx = pg.inner_text('#root')
        check('Schritt 1 geschafft, Schritt 2 als Nächstes', 'Geschafft' in tx and '2 von 2 Übungen bestanden' in tx and pg.locator('.stage.next h2').inner_text().startswith('Schritt 2'), tx[:300])
        pg.evaluate("stats.rounds={};save()")
        go(pg, 'path')
        # Theorie als eigener Teil je Schritt
        go(pg, 'tnotes')
        tx = pg.inner_text('#root')
        check('Theorie Töne', all(k in tx for k in ['Stammtöne und Zwischentöne', 'Halbton und Ganzton', 'Oktave', 'Leere Saiten: G C E A']) and pg.locator('.theory').count() == 4, tx[:80])
        go(pg, 'tscales')
        tx = pg.inner_text('#root')
        check('Theorie Tonleitern', 'Ganz-Ganz-Halb-Ganz-Ganz-Ganz-Halb' in tx and 'C-Dur: C D E F G A H C' in tx and 'A-Moll: A H C D E F G A' in tx and 'C-Dur-Pentatonik ist C D E G A' in tx and 'A-Moll-Pentatonik ist A C D E G' in tx, tx[:200])
        go(pg, 'tchords')
        tx = pg.inner_text('#root')
        check('Theorie Akkorde', 'In C-Dur: I C, ii Dm, iii Em, IV F, V G, vi Am, vii° H°' in tx and 'In A-Moll: i Am, ii° H°, III C, iv Dm, v Em, VI F, VII G' in tx and 'G7 in C-Dur ist G H D F' in tx, tx[:200])
        go(pg, 'path')
        pg.locator('.stage h2').nth(0).click()
        check('Lernpfad: Tipp auf Schritt 1 öffnet Töne (zuletzt benutzte Seite)', pg.evaluate("groupOf(state.mode).id")=='notes' and pg.evaluate("state.mode")==pg.evaluate("state.gm.notes"), pg.evaluate("state.mode"))
        go(pg, 'path'); pg.locator('.stage h2').nth(2).click()
        check('Lernpfad: Tipp auf Schritt 3 öffnet Akkorde (zuletzt benutzte Seite)', pg.evaluate("groupOf(state.mode).id")=='chords' and pg.evaluate("state.mode")==pg.evaluate("state.gm.chords"), pg.evaluate("state.mode"))
        go(pg, 'path')
        check('Lernpfad: keine Links in den Stufen', pg.locator('.stage .btn').count() == 0)
        go(pg, 'smap')
        pg.evaluate("state.sRoot=0;state.sType=0;render()")
        exp = pg.evaluate("(function(){var set=[0,2,4,5,7,9,11],c=0;for(var s=0;s<4;s++)for(var f=0;f<=5;f++)if(set.indexOf(noteAt(s,f))>=0)c++;return c})()")
        check('Tonleiterkarte C-Dur', pg.locator('.dot').count() == exp, str(exp))
        go(pg, 'smap')
        pg.evaluate("window.__seq=0")
        pg.click('.titlerow .play')
        check('Tonleiterkarte: Play-Knopf spielt 8 Töne, kein Anhören-Feld', pg.evaluate("window.__seq") == 8 and 'Anhören' not in pg.inner_text('#root'), str(pg.evaluate("window.__seq")))
        go(pg, 'cdeg')
        pg.click('[data-act="dsel"][data-v="1"]'); pg.evaluate("window.__seq=0")
        pg.click('.stickyfb .play')
        check('Stufen: Play-Knopf im Griffbrett', pg.evaluate("window.__seq") == 4 and 'Anschlagen' not in pg.inner_text('#root'))
        go(pg, 'sfind')
        pg.evaluate("state.q={kind:'find',root:0,t:0,s:1,targets:[0,2,4,5],found:[],miss:0,bad:null,done:false,ok:false,id:31};render()")  # C-Dur auf der C-Saite
        pg.click('rect.hit[data-s="1"][data-f="1"]')
        check('Tonleiter finden: Fehlversuch', pg.evaluate("state.q.miss===1&&!state.q.done"))
        for f in (0, 2, 4, 5):
            pg.click(f'rect.hit[data-s="1"][data-f="{f}"]')
        check('Tonleiter finden: alle gefunden, aber mit Fehler', pg.evaluate("state.q.done&&!state.q.ok"))
        pg.evaluate("state.q={kind:'find',root:0,t:0,s:1,targets:[0,2,4,5],found:[],miss:0,bad:null,done:false,ok:false,id:32};render()")
        for f in (0, 2, 4, 5):
            pg.click(f'rect.hit[data-s="1"][data-f="{f}"]')
        check('Tonleiter finden: fehlerfrei richtig', pg.evaluate("state.q.ok===true&&stats.scales.maj.c>=1"))
        go(pg, 'sname')
        pg.select_option('select[data-act="proot"]', '9'); pg.select_option('select[data-act="ptype"]', '1')   # A-Moll festlegen
        picks = [pg.evaluate("(newScaleQ('name'),state.q.root+'/'+state.q.t)") for _ in range(8)]
        check('Tonleiter wählbar: immer A-Moll', set(picks) == {'9/1'}, str(set(picks)))
        check('Tonleiter-Auswahl bleibt nach Neuladen', (pg.reload() or True) and pg.evaluate("state.pRoot===9&&state.pType===1"))
        go(pg, 'sname')
        pg.select_option('select[data-act="proot"]', '-1'); pg.select_option('select[data-act="ptype"]', '-1')
        pg.evaluate("state.q={kind:'name',root:0,t:0,k:3,picked:null,done:false,ok:false,id:41};render()")   # 3. Ton von C-Dur = E
        pg.click('.ans .btn:text-is("E")')
        check('Tonleiter erkennen: 3. Ton von C-Dur', pg.evaluate("state.q.ok===true"))
        set_inst(pg, 'gtr')
        go(pg, 'cfind')
        pg.evaluate("state.q={i:0,fing:[0,0,0,0,0,0],done:false,ok:false,picked:null,id:51};render()")     # C-Dur: x32010
        pg.click('rect.hit[data-s="0"][data-f="0"]')                      # tiefe E-Saite dämpfen
        for s, f in ((1, 3), (2, 2), (4, 1)):
            pg.click(f'rect.hit[data-s="{s}"][data-f="{f}"]')
        pg.click('[data-act="cchk"]')
        check('Gitarre Greifen: C-Dur mit gedämpfter Saite', pg.evaluate("state.q.ok===true"))
        go(pg, 'stats')
        check('Statistik zeigt Akkorde und Tonleitern', 'Akkord' in pg.inner_text('#root') and 'Tonleiter' in pg.inner_text('#root'))
        check('Akkorde/Tonleitern: keine Konsolenfehler', not errors and not bad, str((errors + bad)[:3]))
        b.close()

        # Akkorde erkennen: synthetische Griffe aller Akkorde beider Instrumente müssen richtig zugeordnet werden
        b = launch(p, a440)
        pg = new_page(b, [], [])
        res = pg.evaluate("""(function(){var bad=[],n=0;
          ['uke','gtr'].forEach(function(id){useInstrument(id);var I=INSTR[id];
            I.chords.forEach(function(c){
              var sr=48000,N=8192,buf=new Float32Array(N);
              c.f.forEach(function(f,s){if(f<0)return;var fr=STR[s].f*Math.pow(2,f/12);
                for(var i=0;i<N;i++){var v=0;for(var h=1;h<=5;h++)v+=Math.sin(2*Math.PI*fr*h*i/sr)/(h*h*0.6+0.4);buf[i]+=0.08*v;}});
              for(var i=0;i<N;i++)buf[i]+=(Math.random()-0.5)*0.03;
              var r=matchChord(chroma(buf,sr,id==='gtr'?40:55,88),I.chords);n++;
              if(I.chords[r.i].n!==c.n||r.score<0.03||r.margin<0.03)bad.push(id+' '+c.n+' -> '+I.chords[r.i].n+' '+r.score.toFixed(2)+'/'+r.margin.toFixed(2));
            });});return {n:n,bad:bad};})()""")
        check('Akkorderkennung: alle ' + str(res['n']) + ' Griffe richtig', not res['bad'], str(res['bad']))
        b.close()

        # Tonnamen: deutsches System mit Doppelnamen für Zwischentöne
        b = launch(p, a440)
        errors, bad = [], []
        pg = new_page(b, errors, bad)
        names = pg.evaluate("NAMES.join(' ')")
        check('Tonnamen mit Doppelnamen', names == 'C Cis/Des D Dis/Es E F Fis/Ges G Gis/As A Ais/B H', names)
        check('Tonartname mit beiden Namen', pg.evaluate("scaleName(6,SCALES[0])") == 'Fis-Dur / Ges-Dur' and pg.evaluate("scaleName(0,SCALES[1])") == 'C-Moll')
        chn = pg.evaluate("(function(){var c=INSTR.uke.chords,u={};c.forEach(function(x){u[x.n]=1});return [Object.keys(u).length,c.length,c[1].n,c[1].t,c[13].n,c[25].n,c[37].n,c[10].n]})()")
        check('Akkordnamen eindeutig, deutsch', chn == [48, 48, 'Cis', 'Cis-Dur / Des-Dur', 'Cism', 'Cis°', 'Cis7', 'Ais'], str(chn))
        go(pg, 'map')
        pg.check('input[data-act="sharps"]')
        check('Karte: Zwischentöne zweizeilig', pg.locator('.dot text.two').count() >= 2 and 'Zwischentöne' in pg.inner_text('#root'))
        pg.evaluate("localStorage.setItem('ukulele-trainer-v1',JSON.stringify({total:3,correct:3,best:3,notes:{},chords:{'C#m':{a:3,c:3},'Am':{a:1,c:1}}}))")
        pg.reload()
        check('Alte Akkordschlüssel werden umbenannt', pg.evaluate("stats.chords.Cism&&stats.chords.Cism.a===3&&stats.chords.Am.a===1&&!stats.chords['C#m']"))
        check('Tonnamen: keine Konsolenfehler', not errors and not bad, str((errors + bad)[:3]))
        b.close()

        # Akkord spielen mit dem simulierten Mikrofon: Ukulele C-Dur (G4 C4 E4 C5), danach falscher Akkord
        for wavname, midis, target, inst, expect in [('c_uke.wav', [67, 60, 64, 72], 0, 'uke', True),
                                                     ('am_uke.wav', [69, 69, 60, 64], 0, 'uke', False),
                                                     ('am_gtr.wav', [45, 52, 57, 60, 64], 21, 'gtr', True),
                                                     ('c7_uke.wav', [67, 60, 64, 70], 36, 'uke', True),    # C7 gespielt, Ziel C7
                                                     ('c7b_uke.wav', [67, 60, 64, 70], 0, 'uke', False),  # C7 gespielt, Ziel C
                                                     ('cb_uke.wav', [67, 60, 64, 72], 36, 'uke', False)]:  # C gespielt, Ziel C7
            b = launch(p, make_chord_wav(wavname, midis))
            errors, bad = [], []
            pg = new_page(b, errors, bad)
            if inst == 'gtr':
                set_inst(pg, 'gtr')
            go(pg, 'cplay')
            pg.evaluate(f"state.q={{i:{target},fing:[],done:false,ok:false,picked:null,id:71}};render()")
            pg.click('[data-act="mic"]'); pg.wait_for_timeout(3000)
            got = pg.evaluate("(stats.chords&&Object.keys(stats.chords).length?Object.keys(stats.chords).map(function(k){return stats.chords[k].c}).reduce(function(a,b){return a+b},0):0)")
            check(f'Akkord spielen ({inst}, Ziel {"richtig" if expect else "falsch gespielt"})', (got >= 1) == expect, f'richtig gezählt: {got}')
            check('Akkord spielen: keine Konsolenfehler', not errors and not bad, str((errors + bad)[:3]))
            b.close()

        # Tonleiter spielen: C-Dur aufwärts C4..C5 mit dem simulierten Mikrofon
        scale = make_seq_wav('cmaj.wav', [60, 62, 64, 65, 67, 69, 71, 72])
        b = launch(p, scale)
        errors, bad = [], []
        pg = new_page(b, errors, bad)
        go(pg, 'splay')
        pg.evaluate("state.q={kind:'play',root:0,t:0,seq:[0,2,4,5,7,9,11,0],idx:0,done:false,ok:false,id:61};render()")
        pg.click('[data-act="mic"]')
        pg.wait_for_timeout(9500)
        check('Tonleiter spielen: C-Dur erkannt', pg.evaluate("(stats.scales.maj||{c:0}).c")>=1, pg.evaluate("JSON.stringify(state.q)"))
        check('Tonleiter spielen: keine Konsolenfehler', not errors and not bad, str((errors + bad)[:3]))
        b.close()
finally:
    srv.terminate()

print(f'\n{sum(results)} von {len(results)} bestanden')
sys.exit(0 if all(results) else 1)
