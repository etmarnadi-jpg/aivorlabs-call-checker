import difflib, json, os, re, sys
MAIL = os.path.expanduser('~/.call-checker/mail-captured.jsonl')
DATE_WORDS = '\\b(today|tomorrow|week|weekend|month|monday|tuesday|wednesday|thursday|friday|saturday|sunday|january|february|march|april|may|june|july|august|september|october|november|december|\\d+(st|nd|rd|th)?)\\b'
ANSWERS = [('everything or just', '\\b(everything|big|few|furniture|whole|all of it)\\b'), ('when (were|are) you (thinking|planning|moving)', DATE_WORDS), ('from where to where|where is the move|where are you moving', '\\b(from|to)\\s+[a-z]{3,}'), ('(best|good) (one|number) to reach|this number', "\\b(yes|yeah|yep|sure|this number|that's right)\\b"), ('how many trees', '\\b(one|two|three|four|five|six|couple|few|several|\\d+)\\b'), ('how close', '\\b(feet|foot|yards?|house|power|lines?|far|close|near)\\b'), ('truck|get to it', '\\b(yes|yeah|yep|no|gate|driveway|access|back ?yard)\\b'), ('stump', '\\b(yes|yeah|yep|no|sure|grind|ground)\\b'), ('what town|which town', '\\b[a-z]{4,}\\b')]
OPEN_RE = re.compile('^\\s*(thanks|thank you)\\b[.!,]?', re.I)
BYE_RE = re.compile('\\b(goodbye|good bye|bye|have a (great|good|nice) (day|night|evening|one)|take care)\\b', re.I)
_MO = 'January February March April May June July August September October November December'.split()
_ORDS = 'first second third fourth fifth sixth seventh eighth ninth tenth eleventh twelfth thirteenth fourteenth fifteenth sixteenth seventeenth eighteenth nineteenth twentieth'.split()
ORD_DAY = {w: i + 1 for i, w in enumerate(_ORDS)}
ORD_DAY.update({'twenty ' + w: 21 + i for i, w in enumerate(_ORDS[:9])}, thirtieth=30, **{'thirty first': 31})
SAID_DATE = re.compile('\\b(%s)\\s+(?:the\\s+)?(\\d{1,2}(?:st|nd|rd|th)?|(?:twenty[ -])?(?:%s)|thirtieth|thirty[ -]first)\\b' % ('|'.join(_MO), '|'.join(_ORDS)), re.I)

def month_day(m):
    d = m.group(2).lower().replace('-', ' ')
    return (m.group(1).title(), int(re.sub('\\D', '', d)) if d[0].isdigit() else ORD_DAY[d])

def dates_faults(evs):
    known, refused, loose, again = (set(), set(), [], [])
    for e in evs:
        ty = e.get('type')
        if ty in ('tool', 'slot', 'siteearly'):
            blob = json.dumps(e)
            known |= {month_day(m) for m in SAID_DATE.finditer(blob)}
            for y, mo, d in re.findall('(\\d{4})-(\\d\\d)-(\\d\\d)', blob):
                if 1 <= int(mo) <= 12:
                    known.add((_MO[int(mo) - 1], int(d)))
            try:
                res = json.loads(e.get('result') or '') if ty == 'tool' else {}
            except (TypeError, ValueError):
                res = {}
            asked = str((e.get('arguments') or {}).get('date') or '')[:10]
            if isinstance(res, dict) and res.get('reason') in ('taken', 'past', 'soon', 'far', 'weekend', 'urgent') and re.fullmatch('\\d{4}-\\d\\d-\\d\\d', asked):
                refused.add((_MO[int(asked[5:7]) - 1], int(asked[8:])))
        elif ty == 'turn' and e.get('role') == 'user':
            known |= {month_day(m) for m in SAID_DATE.finditer(e.get('text') or '')}
        elif ty == 'turn' and e.get('role') == 'assistant':
            for s in sentences(e.get('text')):
                days = {month_day(m) for m in SAID_DATE.finditer(s)}
                loose += [s for k in days if k not in known]
                again += [s for k in days if k in refused and len(days) == 1 and s.rstrip().endswith('?')]
    return (loose, again)
CLAIM = re.compile("(?i)\\b(?:got you down|have you down|you're down for|you are down for|pencilled (?:you )?in|penciled (?:you )?in|you're booked|you are booked|is booked|locked (?:you )?in|you're all set for)\\b")
CLAIM_NOT = re.compile("(?i)\\b(?:not|never|can't|cannot|couldn't|unable|yet|want|would|should|shall|may|can i|once|if|until|before)\\b|n't\\b")
DIGIT_WORDS = {w: str(i) for i, w in enumerate('zero one two three four five six seven eight nine'.split())}
DIGIT_WORDS['oh'] = '0'

def digit_runs(t):
    out, run = ([], '')
    for w in re.findall('[a-z]+|\\d+|[.?!]', (t or '').lower()):
        d = w if w.isdigit() else DIGIT_WORDS.get(w)
        if d is None:
            if len(run) >= 7:
                out.append(run)
            run = ''
        else:
            run += d
    return out + ([run] if len(run) >= 7 else [])

def held_faults(evs):
    held, said, cards = (set(), [], [])
    for e in evs:
        ty = e.get('type')
        if ty == 'tool':
            name, res = (str(e.get('name')), str(e.get('result') or '').replace(' ', ''))
            args = e.get('arguments') or {}
            if name.endswith('_hold_date') and '"ok":true' in res and ('"held":""' not in res):
                held.add(str(args.get('date'))[:10])
            if name.endswith('_call_card') and str(args.get('held') or '').strip() and (not held):
                cards.append(str(args['held'])[:10])
        elif ty == 'turn' and e.get('role') == 'assistant' and (not held):
            said += [s for s in sentences(e.get('text')) if CLAIM.search(s) and SAID_DATE.search(s) and (not CLAIM_NOT.search(s)) and (not s.endswith('?'))]
    return (said, cards)
AREA_SAID = re.compile("(?i)\\boutside the area\\b|\\btoo far out for\\b|\\bcan't get out to\\b")
AREA_BACK = re.compile('(?i)\\bconfirm\\b[^.?!]*\\bcovers?\\b')
AREA_MOVED = re.compile("(?i)\\b(?:actually|sorry|no|i meant|i mean|wait)\\b[^.?!]*\\b(?:in|near|around|at)\\s+[A-Z]|\\bit'?s (?:actually )?in\\s+[A-Z]")
DATE_ASK = re.compile('(?i)\\b(?:what|which) (?:date|day)\\b|\\bpencil\\b|\\bfirst free date\\b|\\bwhen (?:would|do|are) you\\b')

def area_faults(evs):
    out, after = ([], False)
    for e in evs:
        ty, t = (e.get('type'), str(e.get('text') or '').replace('’', "'"))
        if ty == 'turn' and e.get('role') == 'assistant':
            if AREA_SAID.search(t):
                after = True
            elif AREA_BACK.search(t):
                after = False
            elif after and DATE_ASK.search(t):
                out.append(t[:70])
        elif ty == 'turn' and AREA_MOVED.search(t):
            after = False
        elif ty == 'tool' and after and str(e.get('name')).endswith(('_check_date', '_hold_date')) and ('"reason":"outside-area"' not in str(e.get('result')).replace(' ', '')):
            out.append(str(e.get('name')).rsplit('_', 2)[-2] + ' date')
    return out

def flags(name):
    return [sys.argv[i + 1] for i, a in enumerate(sys.argv[:-1]) if a == name]

def load(p):
    out = []
    for l in open(p):
        r = json.loads(l)
        e = r.get('ev')
        if isinstance(e, str):
            try:
                e = json.loads(e)
            except Exception:
                continue
        if isinstance(e, dict):
            e['_rt'] = r.get('rt')
            out.append(e)
    return out

def key(s):
    return ' '.join(re.sub('[^a-z0-9 ]', ' ', s.lower()).split())

def sentences(t):
    return [x.strip() for x in re.findall('[^.?!]+[.?!]', t or '') if len(x.strip()) > 2]

def spelled_letters(text):
    out, run = ([], [])
    for w in re.findall("[A-Za-z]+(?:['’][A-Za-z]+)*", text or ''):
        if len(w) == 1:
            run.append(w)
            continue
        if len(run) >= 3:
            out += run
        run = []
    if len(run) >= 3:
        out += run
    return ''.join(out).upper()

def hangup_verdict(evs, ours):
    byes = [e for e in ours if BYE_RE.search(e.get('text') or '') and '?' not in (e.get('text') or '')]
    end = next((e for e in evs if e.get('type') in ('end', 'byehang') and e.get('done', True)), None)
    if byes and end:
        gap = end['_rt'] - byes[-1]['_rt']
        return (gap <= 2.5, f"{gap:.1f} s from the goodbye's record to the end ({end.get('type')})")
    if byes and (not end) and (byes[-1] is ours[-1]) and (not byes[-1].get('interrupted')):
        times = [e['_rt'] for e in evs if isinstance(e.get('_rt'), (int, float))]
        left = max(times) - byes[-1]['_rt'] if times else 99.0
        if left <= 2.5:
            return (True, f"caller left {left:.1f} s after the whole goodbye, before the line's own hang-up")
    if not byes and (not end) and any((e.get('type') == 'lineout' and e.get('state') == 'ended' for e in evs)) and (not any((e.get('type') == 'lineout' and e.get('by') for e in evs))):
        return (True, "the caller left before the line's goodbye: nothing to hang up after")
    return (False, f'goodbye said: {bool(byes)}; end event: {end}')

def main():
    evs = load(sys.argv[1])
    want = sys.argv[sys.argv.index('--expect-date') + 1] if '--expect-date' in sys.argv else None
    turns = [e for e in evs if e.get('type') == 'turn']
    ours = [e for e in turns if e.get('role') == 'assistant']
    res = []
    prompt = next((e for e in evs if e.get('type') == 'prompt'), {})
    GREETING = f"Thanks for calling {prompt.get('business') or 'Harbor Moving'}"
    no_booking = '--no-booking' in sys.argv

    def line(name, ok, detail=''):
        res.append(ok)
        print(f"{('OK  ' if ok else 'FAIL')} {name}{(': ' + detail if detail else '')}")
    n_open = sum((1 for e in evs if e.get('type') in ('opening', 'opendirect', 'openframe')))
    canned = [e['text'][:50] for e in ours[1:] if OPEN_RE.match(e.get('text') or '') and (not BYE_RE.search(e.get('text') or ''))]
    line('1 no canned opening', n_open == 0 and (not canned), f'{n_open} opening events; replies starting Thanks/Okay: {canned}')
    tools = [e for e in evs if e.get('type') == 'tool']
    slow = [(e['name'], e.get('ms')) for e in tools if (e.get('ms') or 0) > 2000 or e.get('status') not in (200, None)]
    line('2 every calendar answer under 2 s', not slow, f"{[(e['name'], e.get('ms')) for e in tools]}")
    if want:
        dates = [str((e.get('arguments') or {}).get('date') or '') for e in tools if e['name'].endswith('_hold_date')]
        line('3 the right date held', want in dates, f'held {dates}, expected {want}')
    unsaid4 = {id(t) for t in turns if t.get('role') == 'assistant' and any((u.get('type') == 'unsaid' and (u.get('text') or '') and (t.get('text') or '').strip().endswith((u.get('text') or '').strip()) and (0 <= u.get('_rt', -9) - t.get('_rt', 0) <= 2.0) for u in evs))}
    seen, asks, rep, again = ({}, {}, [], [])
    for i, e in enumerate(turns):
        if e.get('role') != 'assistant' or id(e) in unsaid4:
            continue
        for s in sentences(e.get('text')):
            k = key(s)
            if len(s.split()) >= 4 and k in seen and (not k.startswith(key(GREETING))) and (not re.match('is that (right|correct)\\b', k)) and (k != 'are you still there'):
                between = [t for t in turns[seen[k]:i] if t.get('role') == 'user' or 'still there' in (t.get('text') or '')]
                heard = ' '.join((t.get('text') or '' for t in between if t.get('role') == 'user')).lower()
                asks[k] = asks.get(k, 1) + 1
                answered = any((re.search(q, k) and re.search(a, heard) for q, a in ANSWERS))
                if s.endswith('?') and between and (asks[k] < 3) and (not answered):
                    again.append(s)
                elif k in ('let me check that date', 'checking the calendar now') and between:
                    pass
                else:
                    rep.append(s)
            if len(s.split()) >= 4:
                seen[k] = i
    line('4 no sentence said twice', not rep, f'{rep}')
    if again:
        print(f'     asked again, no answer in between (no fault): {again}')
    g = ours[0]['text'] if ours else ''
    line('5 full greeting', bool(ours) and g.startswith(GREETING) and g.rstrip().endswith('?') and (not ours[0].get('interrupted')), g[:120])
    gw = [e for e in evs if e.get('type') == 'greetwait']
    if gw:
        print(f"     greeting wait {gw[0].get('ms')} ms, caller audio {gw[0].get('audio')}")
    two = [e['text'] for e in ours if (e.get('text') or '').count('?') > 1]
    line('6 one question per reply', not two, f'{two}')
    spell_asks, got = ([], True)
    for e in turns:
        if e.get('role') == 'user':
            got = got or len(str(spelled_letters(e.get('text') or ''))) >= 3
        elif re.search('\\bspell\\b', e.get('text') or '', re.I):
            if got or not spell_asks:
                spell_asks.append(e['text'])
            got = False
    line('7a spelling asked at most once', len(spell_asks) <= 1, f'{spell_asks}')
    bad_back = []
    truth = [''.join(re.findall('[A-Z]', x.upper())) for x in flags('--spelled')]
    for k, e in enumerate(turns):
        got = re.findall('(?:\\b[A-Z]\\b[,.\\- ]*){3,}', e.get('text') or '') if e.get('role') == 'assistant' else []
        prev = [t for t in turns[:k] if t.get('role') == 'user']
        if got and prev:
            spelled = spelled_letters(prev[-1].get('text') or '')
            back = ''.join(re.findall('[A-Z]', ' '.join(got)))
            if truth:
                if not any((back == t or (e.get('interrupted') and t.startswith(back)) for t in truth)):
                    bad_back.append((prev[-1].get('text'), e.get('text')))
                continue
            noted = ''.join(re.findall('[A-Za-z]', ' '.join((x.get('name') or '' for x in evs if x.get('type') == 'namenote')))).upper()
            rest = iter(back)
            fills = back.endswith(spelled) and noted.endswith(back) or (back == noted and all((c in rest for c in spelled)))
            after = next((t.get('text') or '' for t in turns[k + 1:] if t.get('role') == 'user'), '')
            fills = fills or (back == noted and difflib.SequenceMatcher(None, back, spelled).ratio() >= 0.75 and (not re.match('\\W*(no|nope|not)\\b', after, re.I)))
            lead = [w.upper() for w in re.findall('[A-Za-z]{2,}', re.split('\\b[A-Z](?:,| -|\\.|-)', e.get('text') or '', maxsplit=1)[0])]
            fills = fills or (bool(spelled) and len(lead) >= 2 and (''.join(lead[-2:]) == spelled) and (back in lead[-2:]) and (not re.match('\\W*(no|nope|not)\\b', after, re.I)))
            fills = fills or (bool(spelled) and len(spelled) >= 3 and (len(back) > len(spelled)) and back.endswith(spelled) and bool(re.search('(?i)\\b(?:last|first) name\\b', prev[-1].get('text') or '')) and (not re.match('\\W*(no|nope|not)\\b', after, re.I)))
            if (spelled and len(spelled) >= 3 and (back != spelled[-len(back):]) or (len(back) < len(spelled) and spelled)) and (not fills):
                bad_back.append((prev[-1].get('text'), e.get('text')))
    line('7d read-back letters = the letters spelled', not bad_back, f'{bad_back}')
    no_ask = [str(e.get('text'))[:60] for e in ours if not e.get('interrupted') and len(re.findall('\\b[A-Z](?:,| -|\\.)\\s', e.get('text') or '')) >= 4 and (not re.search('\\d', e.get('text') or '')) and (not re.search('is that (right|correct)', e.get('text') or '', re.I))]
    line('7e every name read-back asks if it is right', not no_ask, f'{no_ask}' if no_ask else '')
    line('7b caller ID known in the prompt', bool(prompt.get('callerKnown')), f'{prompt}')
    whatis = [e['text'] for e in ours if re.search("\\bwhat is it\\b|\\bwhat'?s the number\\b", e.get('text') or '', re.I)]
    numtool = [e for e in tools if e['name'].endswith('_read_number')]
    if not no_booking:
        line("7c 'this number' used, not asked again", not whatis and bool(numtool), f'asked again {whatis}; read_number calls {len(numtool)}')
    allq = ' '.join((e.get('text') or '' for e in ours)).lower()
    callers = ' '.join((e.get('text') or '' for e in turns if e.get('role') == 'user')).lower()
    asked = {'bedrooms': 'bedroom' in allq, 'everything or big items': 'everything' in allq or 'big item' in allq, 'floor': 'floor' in allq or 'apartment' not in callers, 'stairs/elevator': 'stairs' in allq or 'elevator' in allq or 'apartment' not in callers, 'morning/afternoon': 'morning' in allq and 'afternoon' in allq or 'morning' in callers or 'afternoon' in callers, 'told who calls back': any((re.search('\\bestimator\\b|\\bwill call\\b|\\bcalls? (?:you )?back\\b|\\bhear from\\b|\\bbe in touch\\b', e.get('text') or '', re.I) for e in ours[-6:])), "never 'what exactly are you moving'": 'what exactly' not in allq}
    tree = re.search('\\btree\\b', str(prompt.get('business') or ''), re.I)
    if tree:
        for k in ('bedrooms', 'everything or big items', 'floor', 'stairs/elevator'):
            del asked[k]
        said = ' '.join((e.get('text') or '' for e in turns if e.get('role') == 'user'))
        gave_count = bool(re.search('(?i)\\b(?:a|an|one|two|three|four|five|six|couple of|few|several|\\d+) (?:\\w+ ){0,3}(?:trees?|stumps?|maples?|cedars?|birch(?:es)?|oaks?|firs?|pines?)\\b|\\b(?:one|two|three|four|five|six|\\d+) of them\\b', said))
        gave_town = bool(re.search('\\b(?:in|from|near|outside) (?!(?:January|February|March|April|May|June|July|August|September|October|November|December|Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\\b)[A-Z][a-z]{3,}', said))
        asked.update({'how many trees': 'how many' in allq or gave_count, 'how close to the house or power lines': 'how close' in allq or 'power line' in allq, 'truck access': 'truck' in allq or 'access' in allq, 'stump': 'stump' in allq, 'town': 'town' in allq or 'where' in allq or gave_town})
    skip8 = ''
    if tree:
        seq = [e for e in turns if e.get('text')]
        pen = next((i for i, e in enumerate(seq) if e.get('role') != 'user' and re.search('(?i)pencil+ed in', e.get('text') or '')), None)
        after = seq[pen + 1:] if pen is not None else []
        went_on = any((e.get('role') == 'user' and any((o.get('role') != 'user' and (not o.get('interrupted')) for o in after[i + 1:])) for i, e in enumerate(after)))
        if not went_on:
            asked['morning/afternoon'] = True
        if re.search('(?i)\\b(?:trimm?\\w*|prun\\w*|too tall|limbs?|branch(?:es)?|hedges?)\\b', said) and (not re.search('(?i)\\b(?:down|remov\\w*|fell|fallen|dead|clear\\w*|stumps?)\\b', said)):
            asked['stump'] = True
        if re.search('(?i)marking this urgent|calling \\w+ right now|outside the area', allq):
            for k in ('morning/afternoon', 'told who calls back'):
                asked[k] = True
        if re.search('(?i)marking this urgent|calling \\w+ right now', allq):
            skip8 = 'the emergency ring ended the intake'
        elif not re.search('(?i)\\b(?:trees?|stumps?|limbs?|branch(?:es)?|trimm?\\w*|prun\\w*|hedges?|maples?|pines?|firs?|oaks?|cedars?|alders?|birch(?:es)?)\\b', said):
            skip8 = 'the caller named no tree job'
    if skip8:
        line('8 tree intake asked', True, skip8)
    elif not no_booking:
        line(f"8 {('tree' if tree else 'moving')} intake asked", all(asked.values()), f'{asked}')
    said = ' '.join((e.get('text') or '' for e in ours))
    for w in flags('--must'):
        line(f'9 said: {w}', w in said)
    for w in flags('--must-not'):
        line(f'9 never said: {w}', w not in said)
    if flags('--mail-has'):
        rows = [l for l in open(MAIL)] if os.path.exists(MAIL) else []
        mail = next((l for l in reversed(rows) if flags('--caller') and flags('--caller')[0] in l), '')
        line("10 owner's email arrived", bool(mail))
        for w in flags('--mail-has'):
            line(f'10 email has: {w}', w.lower() in mail.lower())
    line('11 hung up after the goodbye', *hangup_verdict(evs, ours))
    dates = [e.get('text') for e in evs if e.get('type') == 'clip' and str(e.get('kind')).startswith('date')]
    if len(dates) > 1:
        line('16 date turns in turn', all((a != b for a, b in zip(dates, dates[1:]))), str(dates))
    for d in flags('--never-held'):
        line(f'12 busy day not held: {d}', not [e for e in tools if e['name'].endswith('_hold_date') and f'"held":"{d}"' in str(e.get('result')).replace(' ', '')])
    loose, again = dates_faults(evs)
    line("12 every date said has a site answer or the caller's words behind it", not loose, str(loose) if loose else '')
    line('12 a refused day is never offered again', not again, str(again) if again else '')
    said, cards = held_faults(evs)
    line('13 a date said as booked has a hold behind it', not said, str(said) if said else '')
    line("13 a card's held date has a hold behind it", not cards, str(cards) if cards else '')
    allowed = ''.join((re.sub('\\D', '', json.dumps(e)) for e in tools)) + re.sub('\\D', '', str(next((e.get('caller') for e in evs if e.get('caller')), '')))
    allowed += ''.join((''.join(digit_runs(e.get('text')) + re.findall('\\d', e.get('text') or '')) for e in turns if e.get('role') == 'user'))
    long_said = [s for e in ours for s in digit_runs(e.get('text')) if s[-7:] not in allowed]
    line('14 no long number nobody gave', not long_said, str(long_said) if long_said else '')
    area = area_faults(evs)
    line('15 no date goes ahead after the outside-the-area line', not area, str(area) if area else '')
    print('PASS' if all(res) else 'FAIL')
    for e in turns:
        print(f"  {e['_rt']:7.1f} {('US ' if e['role'] == 'assistant' else 'CAL')} {('(cut) ' if e.get('interrupted') else '')}{e.get('text')}")
if __name__ == '__main__':
    main()
