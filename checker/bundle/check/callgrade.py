import io, json, os, sys, urllib.request
from pathlib import Path
import numpy as np, soundfile as sf
OPEN = {'thanks', 'thank you', 'okay', 'ok', 'got it', 'sure', 'alright', 'all right', 'mm', 'mhm', 'right', 'great', 'perfect'}

def words(chan, sr, cache):
    if cache.exists():
        return json.loads(cache.read_text())
    w = [{'w': '', 's': round(a, 3), 'e': round(b, 3)} for a, b in vad(chan, sr)]
    cache.write_text(json.dumps(w))
    os.chmod(cache, 384)
    return w

def vad(chan, sr):
    import torch
    from silero_vad import load_silero_vad, get_speech_timestamps
    m = load_silero_vad()
    ts = get_speech_timestamps(torch.from_numpy(chan.astype(np.float32)), m, sampling_rate=sr, min_speech_duration_ms=80, min_silence_duration_ms=100)
    return [(t['start'] / sr, t['end'] / sr) for t in ts]

def segs(ws, gap=0.7):
    out = []
    for w in ws:
        if out and w['s'] - out[-1]['e'] <= gap:
            out[-1]['e'] = w['e']
            out[-1]['words'].append(w)
        else:
            out.append({'s': w['s'], 'e': w['e'], 'words': [w]})
    for o in out:
        o['text'] = ' '.join((w['w'] for w in o['words']))
    return out

def norm(t):
    return t.lower().strip(' .,!?')

def skip_opening(ws):
    k = 0
    while k < len(ws):
        if k + 1 < len(ws) and norm(ws[k]['w']) + ' ' + norm(ws[k + 1]['w']) in OPEN and (ws[k + 1]['w'][-1:] in '.!,'):
            k += 2
            continue
        if norm(ws[k]['w']) in OPEN and ws[k]['w'][-1:] in '.!,':
            k += 1
            continue
        break
    return k

def grade(wav):
    x, sr = sf.read(wav)
    gdir = wav.parent.joinpath('grade')
    gdir.mkdir(exist_ok=True)
    os.chmod(gdir, 448)
    C = words(x[:, 0], sr, gdir.joinpath(wav.stem + '.caller.json'))
    R = words(x[:, 1], sr, gdir.joinpath(wav.stem + '.recep.json'))
    rv = vad(x[:, 1], sr)
    cs, rs = (segs(C), segs(R))
    ev = sorted([('c', s) for s in cs] + [('r', s) for s in rs], key=lambda t: t[1]['s'])
    rows = []
    for i, (who, s) in enumerate(ev):
        nxt = ev[i + 1] if i + 1 < len(ev) else None
        if who != 'c' or not nxt or nxt[0] != 'r':
            continue
        ce, r = (s['e'], nxt[1])
        snd = next((a for a, b in rv if b > ce - 0.05), None)
        ws = r['words']
        k = skip_opening(ws)
        real = ws[k] if k < len(ws) else None
        j = i + 2
        while real is None and j < len(ev) and (ev[j][0] == 'r'):
            w2 = ev[j][1]['words']
            k2 = skip_opening(w2)
            real = w2[k2] if k2 < len(w2) else None
            j += 1
        rows.append({'t': round(ce, 2), 'caller': s['text'], 'sound': round(snd - ce, 2) if snd is not None else None, 'word': round(ws[0]['s'] - ce, 2), 'real': round(real['s'] - ce, 2) if real else None, 'opening': ' '.join((w['w'] for w in ws[:k])), 'reply': r['text']})
    return (rows, cs, rs)

def main():
    wav = Path(sys.argv[1])
    rows, cs, rs = grade(wav)
    late = lambda r: r['real'] if r['real'] is not None else r['word']
    bad = [r for r in rows if late(r) > 0.5]
    print(f"{wav.name}: {len(rows)} replies, {len(bad)} over 0.5 s to the first real word -> {('FAIL' if bad or not rows else 'PASS')}")
    print(f"{'at':>6} {'sound':>6} {'word':>6} {'real':>6}  opening | caller -> reply")
    for r in rows:
        print(f"{r['t']:6.1f} {str(r['sound']):>6} {r['word']:6.2f} {str(r['real']):>6}  {r['opening'] or '-'} | ...{r['caller'][-50:]} -> {r['reply'][:120]}")
    if '--full' in sys.argv:
        for who, s in sorted([('CALLER', s) for s in cs] + [('RECEP ', s) for s in rs], key=lambda t: t[1]['s']):
            print(f"  {s['s']:6.1f}-{s['e']:6.1f} {who} {s['text']}")
    if '--json' in sys.argv:
        p = Path(sys.argv[sys.argv.index('--json') + 1])
        p.write_text(json.dumps({'rows': rows, 'caller': cs, 'recep': rs}, indent=1))
        os.chmod(p, 384)
if __name__ == '__main__':
    main()
