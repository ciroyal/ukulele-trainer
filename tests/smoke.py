"""Rauchtest für den Ukulele-Trainer in einem echten Chrome mit simuliertem Mikrofon.

Aufruf:  python3 tests/smoke.py [Pfad/zu/index.html]
Braucht: Python-Paket `playwright` und einen installierten Google Chrome (Pfad unten anpassen).
Prüft Tabs, Karte, beide Quizformen, Statistik, Stimmgerät und das Spielen im Finden-Tab.
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

        for v in ['map', 'find', 'name', 'tune', 'stats']:
            pg.click(f'[data-act="tab"][data-v="{v}"]')
            check('Tab ' + v, pg.locator('.tab.on').get_attribute('data-v') == v)

        pg.click('[data-v="map"]')
        expected = pg.evaluate("(function(){var c=0;for(var s=0;s<4;s++)for(var f=0;f<=5;f++)if(isNat(noteAt(s,f)))c++;return c})()")
        check('Karte zeigt alle Naturtöne Bund 0-5', pg.locator('.dot').count() == expected, f'{expected} erwartet')

        pg.click('[data-v="find"]')
        pg.evaluate("state.q={s:1,f:2,n:noteAt(1,2),done:false,ok:false,picked:null,id:1};render()")
        pg.click('rect.hit[data-s="1"][data-f="2"]')
        check('Finden: richtige Stelle', pg.evaluate("state.q.ok===true"))
        pg.wait_for_timeout(1100)
        check('Finden: springt weiter', pg.evaluate("state.q.done===false"))
        pg.evaluate("state.q={s:1,f:2,n:noteAt(1,2),done:false,ok:false,picked:null,id:2};render()")
        pg.click('rect.hit[data-s="2"][data-f="1"]')
        check('Finden: falsche Stelle zeigt Weiter', pg.evaluate("state.q.done&&!state.q.ok") and pg.locator('[data-act="next"]').count() == 1)

        pg.click('[data-v="name"]')
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

        pg.click('[data-v="find"]')
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
finally:
    srv.terminate()

print(f'\n{sum(results)} von {len(results)} bestanden')
sys.exit(0 if all(results) else 1)
