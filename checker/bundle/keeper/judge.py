from __future__ import annotations
import array
import importlib.util
import json
import re
import wave
from datetime import datetime, timezone
from pathlib import Path
from . import dates, events as evmod, lines as linemod, refuse, tools
PROMISES = ('P1', 'P2', 'P3', 'P4', 'P5', 'P6', 'P7')
PICKUP_SLOW = 4.0
AGENT_LATE = 3.0
BYE_GAP = 3.0
CHECKS = [('^1 ', 'P7', 'stock-opening', 'used a stock opening line'), ('^2 ', 'P7', 'calendar-slow', 'kept the caller waiting on the calendar'), ('^3 ', 'P3', 'wrong-date-held', 'held the wrong date'), ('^4 ', 'P7', 'said-twice', 'said the same sentence twice'), ('^5 ', 'P1', 'greeting', 'did not say the full greeting'), ('^6 ', 'P7', 'two-questions', 'asked two questions at once'), ('^7a ', 'P7', 'spelling-twice', 'asked for the spelling more than once'), ('^7b ', 'P2', 'caller-id', "did not have the caller's number"), ('^7c ', 'P2', 'number-asked', "did not take the caller's number the right way"), ('^7d ', 'P2', 'name-readback', 'read the name back wrong'), ('^7e ', 'P2', 'name-confirm', 'read the name back without asking if it was right'), ('^8 ', 'P2', 'intake', 'missed some of the job questions'), ('^10 ', 'P2', 'owner-email', "the owner's email missed something"), ('^11 ', 'P7', 'no-hangup', 'did not hang up after the goodbye'), ('^12 a refused', 'P3', 'refused-day-again', 'offered a day the calendar had turned down'), ('^12 ', 'P3', 'date-unbacked', 'said a date the calendar never gave'), ('^13 a card', 'P3', 'card-date-unheld', 'told the owner a date was held when it was not'), ('^13 ', 'P3', 'booked-unheld', 'told the caller a date was booked when it was not'), ('^14 ', 'P7', 'long-number', 'read out a long number nobody gave'), ('^16 ', 'P7', 'date-words-same', 'opened two date answers with the same words')]
OWN = {'no-answer': ('P1', 'nobody answered the call'), 'never-joined': ('P1', 'the receptionist never joined the call'), 'no-record': ('P1', "the receptionist left no record of the call, so it can't be shown that it answered"), 'notice': ('P1', 'the greeting left out the recording or AI notice'), 'pickup-slow': ('P1', 'picked up slowly'), 'asleep': ('P1', 'picked up slowly because the receptionist was asleep'), 'emergency-no-ring': ('P4', 'an emergency did not ring the owner'), 'emergency-not-reached': ('P4', 'said the owner was reached when nobody pressed a key'), 'ring-failed': ('P4', "the owner's phone could not be rung"), 'down-silent': ('P5', 'the caller heard silence and the backup did not step in'), 'down-not-told': ('P5', 'the backup stepped in but the caller was not told'), 'down-not-rung': ('P5', 'the backup stepped in but the owner was not rung'), 'down-broke': ('P5', 'the backup path broke'), 'lineout-off': ('P5', 'the backup was switched off, so it did not step in when the receptionist went quiet'), 'no-email': ('P2', 'the owner got no email'), 'email-short': ('P2', "the owner's email is missing the name, number or job"), 'slow': ('P6', 'replies are too slow'), 'credit': ('P1', 'ran out of free model credit'), 'model-down': ('P7', 'the model service failed'), 'model-refused': ('P7', 'the model turned down what the receptionist sent'), 'site-down': ('P3', 'the booking calendar could not be reached'), 'site-error': ('P3', 'the booking calendar broke during the call'), 'no-key-press': ('P4', 'an emergency rang the owner but nobody pressed a key, so the owner may not know'), 'voice-lost': ('P1', 'the receptionist lost its voice, so the backup message played')}
CHECK_WRONG = {'check-11-caller-left': 'the hang-up check fails calls where the caller hung up first', 'check-broke': 'a call check could not read a call', 'speed-reader-broke': 'the speed reader could not read a recording', 'record-damaged': "part of a call's record could not be read, so the rest was judged without it", 'line-unknown': 'a call came for a business the watcher does not know, so its emergency words were not checked', 'judge-broke': 'the watcher could not judge a call'}
HONEST = re.compile("(?i)\\b(?:couldn't|could not|can't|cannot|wasn't able to|was not able to|unable to|didn't|did not|haven't|have not|hasn't|has not|not able to|no one|nobody|not yet)\\b|\\b(?:no answer|not answer|not pick|still trying|trying to reach|try to reach|keep trying|try again|i'm calling|i am calling|calling (?:\\w+ )?(?:now|right now)|sending (?:\\w+ )?(?:an )?urgent message|left (?:\\w+ )?(?:a )?(?:message|voicemail)|voicemail|stay on the line|please hold|one moment|as soon as (?:he|she|they) (?:can|sees|gets|hears)|when (?:he|she|they) (?:sees|gets|hears))\\b")
CLAIM_HELP = re.compile("(?i)\\b(?:help|someone|somebody|a crew|the crew|our team|a team)\\s+(?:is|are|will be|'s)\\s+(?:now\\s+|already\\s+)?(?:on (?:the|its|their) way|coming|heading|en route|there soon|being sent)\\b|\\b(?:sending|sent|dispatched|dispatching) (?:help|someone|a crew)\\b")
WE = re.compile("(?i)\\b(?:i|i've|i have|i'd|we|we've|we have)\\b")

def _owner_res(owner_names, pronoun):
    names = [re.escape(n) for n in owner_names if n]
    pro = {'he': ('he', 'him'), 'she': ('she', 'her'), 'they': ('they', 'them')}.get(str(pronoun or '').lower(), ('he|she', 'him|her'))
    subj = '(?:' + '|'.join(names + ['the owner', 'the boss', 'our owner', pro[0]]) + ')'
    obj = '(?:' + '|'.join(names + ['the owner', 'the boss', 'our owner', pro[1]]) + ')'
    who = re.compile('(?i)\\b' + '(?:' + '|'.join(names + ['the owner', 'owner', 'the boss', pro[0], pro[1]]) + ')\\b')
    claim = re.compile(f"(?i)\\b(?:reached|got (?:hold|ahold) of|got through to|got in touch with|spoke (?:to|with)|spoken (?:to|with)|talked (?:to|with)|connected (?:with|to)|caught|let|told|informed|notified|alerted|filled in|updated)\\s+{obj}\\b|\\b{subj}(?:'s|\\s+is|\\s+has|\\s+will|'ll|\\s+was|\\s+knows|\\s+already|\\s+now|\\s+just)*\\s*(?:now\\s+|already\\s+|just\\s+|been\\s+)?(?:knows|aware|told|informed|notified|alerted|got (?:the|your) message|(?:has|got) (?:the|your) (?:details|message|info)|on (?:his|her|their|the) way|coming|heading (?:over|out|there|your way)|en route|be there|be right there|be over|on it|handling it|taking care of it|picked up|answered|confirmed|said|says|called back|here)\\b")
    return (who, claim)
OWNER_BY = re.compile('\\b(?:calling|call|reach|reaching|reached|ring|ringing|contact|contacting|message|messaging|text|texting|alert|alerting|let|tell|telling|told|notify|notifying)\\s+([A-Z][a-z]+)\\b')
NOT_A_NAME = {'You', 'Your', 'The', 'Our', 'Back', 'Me', 'Us', 'Them', 'Him', 'Her', 'It', 'That', 'This', 'Someone', 'Anyone'}
BYE = re.compile('(?i)\\b(?:goodbye|bye|thanks for calling|thank you for calling|take care|have a (?:good|great|nice) (?:day|night|evening))\\b')
ACK = re.compile("(?i)^\\W*(?:(?:ok(?:ay)?|alright|all right|got it|i see|i understand|i hear you|oh no|oh|sure|of course|yes|no|right|thank you|thanks|i'm (?:so |very )?sorry(?: to hear that)?|that sounds (?:urgent|scary|serious|stressful|awful|terrible|bad|frightening)|(?:please )?(?:stay on the line|hold on|hang on|one moment|bear with me)(?: please)?)\\W*)+$")

def owner_kind(s: str, owner_names=(), pronoun=None) -> str | None:
    who, claim = _owner_res(owner_names, pronoun)
    kinds = set()
    asks_or_bye = s.rstrip().endswith('?') or bool(BYE.search(s))
    for part in re.split('[,;:]\\s*|\\s(?:but|and|so)\\s', s):
        if not part.strip(' .!?'):
            continue
        if CLAIM_HELP.search(part) and (not HONEST.search(part)):
            kinds.add('claim')
        elif HONEST.search(part) and (who.search(part) or WE.search(part)):
            kinds.add('honest')
        elif claim.search(part):
            kinds.add('claim')
        elif who.search(part) and (not BYE.search(part)):
            kinds.add('unclear')
        elif not (asks_or_bye or ACK.match(part)):
            kinds.add('unclear')
    for k in ('claim', 'unclear', 'honest'):
        if k in kinds:
            return k
    return None
HAZARD_CLEAR = [re.compile(p) for p in ("(?i)\\bwater\\b[^.?!]{0,30}\\b(?:pouring|gushing|coming in|coming through|coming up|coming down|everywhere|leaking|rising|spraying|flooding|filling|all over|on the floor|dripping through|pooling|won't stop|running down)\\b", '(?i)\\b(?:fill(?:ing|ed)?|full|flooded|flooding|soaked)\\b[^.?!]{0,25}\\bwith water\\b|\\b(?:under ?water)\\b', "(?i)\\b(?:basement|kitchen|house|home|apartment|garage|floor|room|ceiling|bathroom|place)\\b[^.?!]{0,20}\\b(?:is |'s )?(?:flooding|flooded|filling up|under water|full of water|leaking|caving in)\\b", '(?i)\\b(?:smell(?:s|ing|ed)?|stinks?|reeks?)\\b[^.?!]{0,20}\\bgas\\b|\\bgas\\b[^.?!]{0,10}\\b(?:leak(?:ing|s)?|smell|line (?:broke|burst|cut|hit))\\b|\\bleaking gas\\b', "(?i)\\bsmoke\\b[^.?!]{0,25}\\b(?:coming|everywhere|pouring|filling|in the|from the|out of)\\b|\\b(?:there's|there is|i see|i smell|see|smell(?:s|ing)?)\\b[^.?!]{0,15}\\bsmoke\\b|\\bfull of smoke\\b|\\b(?:is|are|'s|'re|it's|started|starts|keeps?) smoking\\b", "(?i)\\bon fire\\b|\\bcaught fire\\b|\\b(?:a|the) fire (?:in|at|is|started|broke out|near)\\b|\\bthere'?s (?:a )?fire\\b|\\bflames?\\b|\\b(?:is|are|'s|'re) burning\\b(?! through)|\\bsmell(?:s|ing)? (?:something )?burning\\b|\\bburning smell\\b|\\bblaze\\b", '(?i)\\b(?:carbon monoxide|co)\\b[^.?!]{0,30}\\b(?:alarm|detector)s?\\b[^.?!]{0,25}\\b(?:going off|went off|goes off|beeping|sounding|ringing|blaring|keeps? going)\\b|\\bcarbon monoxide (?:leak|poisoning|in (?:the|my|our))\\b', "(?i)\\b(?:is|are|'s|'re) (?:flooding|flooded|filling up with water)\\b")]
HAZARD_TOPIC = re.compile('(?i)\\b(?:water|wet|leak\\w*|flood\\w*|gas|fumes?|smok\\w*|fires?|burn\\w*|flames?|sparks?|explo\\w+|pipes?|carbon monoxide|co (?:alarm|detector)s?)\\b')
HAZARD_DENIED = re.compile("(?i)\\b(?:no|not|never|nothing|isn't|aren't|wasn't|weren't|don't|doesn't|didn't|without)\\b")
HAZARD_NOT_NOW = re.compile('(?i)\\b(?:last (?:year|month|week|winter|summer|spring|fall|time)|\\w+ ago|used to|in case|if|what if|insurance|coverage|clean ?up|clean-up|restoration|ban|bans|drill|inspection|permit)\\b')
SOFT_EM = re.compile('(?i)\\b(?:smok\\w*|burn\\w*|fires?|flood\\w*|flames?|blaze)\\b')
HAZARD_PLAIN = re.compile('(?i)\\b(?:gas (?:station|money|mileage|prices?|tank|can|fee|card)|fire ?place|fire pit|firewood|fire escape|water ?bed|water bottles?|bottled water|water view|waterfront|smoke detectors?|smoke alarms?|no smoking|gas (?:stove|dryer|range|grill)s?|fired|ceasefire)\\b')

def hazard(text: str) -> str | None:
    t = HAZARD_PLAIN.sub(' ', text or '')
    for part in re.split('(?<=[.?!,;])\\s+|\\s(?:but|and)\\s', t):
        if any((p.search(part) for p in HAZARD_CLEAR)) and (not HAZARD_DENIED.search(part)) and (not HAZARD_NOT_NOW.search(part)):
            return 'clear'
    return 'unclear' if HAZARD_TOPIC.search(t) else None
OUTAGE_CAUSED = {'model': {'intake', 'owner-email', 'no-email', 'email-short', 'no-hangup', 'said-twice', 'stock-opening', 'caller-id', 'number-asked', 'two-questions'}, 'site': {'calendar-slow', 'date-unbacked', 'wrong-date-held', 'card-date-unheld', 'refused-day-again', 'owner-email', 'no-email', 'email-short'}}

def _right_side_sound(wav: Path) -> bool | None:
    try:
        with wave.open(str(wav)) as w:
            ch, width = (w.getnchannels(), w.getsampwidth())
            if ch < 2 or width != 2:
                return None
            loud = 0
            while True:
                fr = w.readframes(16000)
                if not fr:
                    break
                a = array.array('h', fr)[1::ch]
                loud += sum((1 for i in range(0, len(a), 160) if max(a[i:i + 160], default=0) > 1000 or min(a[i:i + 160], default=0) < -1000))
                if loud >= 50:
                    return True
            return False
    except (OSError, wave.Error, EOFError, ValueError):
        return None

def _import_check(cfg):
    spec = importlib.util.spec_from_file_location('elijah_check_ro', cfg.elijah_check)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

def check_info(name: str):
    for pat, promise, slug, words in CHECKS:
        if re.search(pat, name):
            return (promise, slug, words)
    return None

def _num(v, default=None):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default

def mail_for(cfg, call_ids, at=None) -> list:
    p = Path(cfg.mail)
    if not p.exists():
        return None
    try:
        if at is not None and cfg.mail_fresh and (at - p.stat().st_mtime > cfg.mail_fresh):
            return None
    except OSError:
        return None
    rows, newest = ([], None)
    try:
        for line in p.read_text(errors='replace').splitlines():
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if not isinstance(r, dict):
                continue
            try:
                t = datetime.strptime(str(r.get('at') or '')[:19], '%Y-%m-%dT%H:%M:%S').replace(tzinfo=timezone.utc).timestamp()
                newest = t if newest is None else max(newest, t)
            except ValueError:
                pass
            if str(r.get('callId') or '') in call_ids:
                rows.append(r)
    except OSError:
        return None
    if not rows and at is not None and cfg.mail_fresh and (newest is not None) and (at - newest > cfg.mail_fresh):
        return None
    return rows

def _field(text: str, name: str) -> str:
    m = re.search(f'(?m)^{name}:\\s*(.*)$', text or '')
    return m.group(1).strip() if m else ''

def judge(cfg, call, lines: dict, default: str, now: float, account: str | None=None) -> dict | None:
    ec = _import_check(cfg)
    evs, good, bad, blank = evmod.read(call.events) if call.events.exists() else (None, [], 0, 0)
    events_path = call.events
    if (bad or blank) and evs:
        events_path = evmod.clean_copy(cfg.state, call.label, good)
    if not evs:
        evs = None
    prompt = next((e for e in evs or [] if e.get('type') == 'prompt'), {})
    if refuse.refused(prompt.get('line'), prompt.get('business')):
        return None
    line_id = str(prompt.get('line') or '')
    unknown = bool(line_id) and line_id not in lines
    line = None if unknown else lines.get(line_id) or lines.get(default)
    line_from = None
    if unknown:
        line = linemod.template_for(prompt.get('business'), lines)
        unknown = line is None
        line_from = line and line['fromTemplate']
    res = {p: {'result': 'pass', 'why': []} for p in PROMISES}
    problems, ears = ([], ['how the call sounds next to other receptionists'])
    names = []
    if bad:
        problems.append({'slug': 'record-damaged', 'sort': 'CHECK IS WRONG', 'promise': None, 'words': CHECK_WRONG['record-damaged'], 'heard': False, 'bad': bad})
    if unknown:
        problems.append({'slug': 'line-unknown', 'sort': 'CHECK IS WRONG', 'promise': None, 'words': CHECK_WRONG['line-unknown'], 'heard': False})

    def fail(slug, sort, promise=None, words=None, heard=True):
        promise = promise or OWN[slug][0]
        words = words or OWN[slug][1]
        problems.append({'slug': slug, 'sort': sort, 'promise': promise, 'words': words, 'heard': heard})
        if heard:
            res[promise]['result'] = 'FAIL'
            res[promise]['why'].append(words)

    def ear(promise, words):
        if res[promise]['result'] == 'pass':
            res[promise]['result'] = 'needs ears'
        res[promise]['why'].append(words)
        ears.append(words)
    note = call.note or {}
    tracks = note.get('tracks') or []
    cal_t = [t.get('subscribedSec') for t in tracks if t.get('who') == 'caller' and t.get('subscribedSec') is not None]
    rec_t = [t.get('subscribedSec') for t in tracks if t.get('who') == 'receptionist' and t.get('subscribedSec') is not None]
    if evs is None and call.events.exists() and (not bad):
        v = _no_rows(cfg, call, res, problems, ears, fail, ear, rec_t, now, line)
        v.update(damaged=0, account=account, quota=False, failovers=0, lineKnown=not unknown and str(line_id or default) in lines)
        return v
    if evs is None:
        sp = tools.speed(cfg, call)
        if sp.get('running'):
            return dict(_done(call, res, problems, ears, sp, names, now, pending=True, line=line), speedRunning=True)
        for p in ('P1', 'P2', 'P3', 'P4', 'P5', 'P7'):
            ear(p, 'this call has no record of what the receptionist did')
        _speed(res, sp, fail, problems, outside=False)
        v = _done(call, res, problems, ears, sp, names, now, pending=False, line=line)
        v.update(damaged=bad, account=account, quota=False, failovers=0, lineKnown=not unknown and str(line_id or default) in lines)
        return v
    turns = [e for e in evs if e.get('type') == 'turn']
    ours = [e for e in turns if e.get('role') == 'assistant']
    users = [e for e in turns if e.get('role') == 'user']
    names = [e.get('name') for e in evs if e.get('type') in ('namenote', 'rehold') and e.get('name')]
    ready = next((e for e in evs if e.get('type') == 'ready'), {})
    blob = '\n'.join((json.dumps(e) for e in evs))
    quota = 'inference_quota_exceeded' in blob or any((e.get('type') == 'llmerror' and '429' in str(e.get('error')) for e in evs))
    llm_other = [e for e in evs if e.get('type') == 'llmerror' and 'inference_quota_exceeded' not in str(e.get('error')) and ('429' not in str(e.get('error')))]
    site_down = any((e.get('type') == 'siteslow' or (e.get('type') == 'holdfail' and _num(e.get('status'), 0) in (0, 502, 503, 504, 530)) or (e.get('type') == 'tool' and _num(e.get('status'), 200) in (0, 502, 503, 504, 530)) for e in evs))
    site_err = any((e.get('type') == 'holdfail' and _num(e.get('status'), 0) >= 500 and (_num(e.get('status')) not in (502, 503, 504, 530)) or (e.get('type') == 'tool' and _num(e.get('status'), 200) >= 500 and (_num(e.get('status')) not in (502, 503, 504, 530))) for e in evs))
    outside = quota or site_down or any(('Error code: 400' not in str(e.get('error')) for e in llm_other))
    caused = (OUTAGE_CAUSED['model'] if quota or any(('Error code: 400' not in str(e.get('error')) for e in llm_other)) else set()) | (OUTAGE_CAUSED['site'] if site_down else set())
    blame = lambda slug: 'OUTSIDE' if outside and slug in caused else 'CODE'
    if quota:
        problems.append({'slug': f'credit-{account}' if account else 'credit', 'sort': 'OUTSIDE', 'promise': 'P1', 'heard': True, 'words': f'ran out of free model credit on {account}' if account else OWN['credit'][1], 'account': account})
        res['P1']['result'] = 'FAIL'
        res['P1']['why'].append(OWN['credit'][1])
    for e in llm_other:
        if 'Error code: 400' in str(e.get('error')):
            fail('model-refused', 'CODE')
        else:
            fail('model-down', 'OUTSIDE')
    if site_down:
        fail('site-down', 'OUTSIDE')
    elif site_err:
        fail('site-error', 'CODE')
    if any((e.get('type') == 'hedgefail' and 'Error code: 400' in str(e.get('error')) for e in evs)):
        fail('model-refused', 'CODE', heard=False)
    blips = sum((e.get('type') == 'llmfailover' for e in evs))
    hang_note = None

    def out(v):
        v['line'] = line_id or str((line or {}).get('id') or '')
        v['lineKnown'] = not unknown and (str(line_id or default) in lines or line_from is not None)
        if line_from:
            v['lineFrom'] = line_from
        if hang_note:
            v['hangup'] = hang_note
        v['failovers'] = 0 if quota else blips
        v['quota'] = quota
        v['quotaMark'] = 'inference_quota_exceeded' in blob
        v['damaged'] = bad
        v['account'] = account
        return v
    lost = [e for e in evs if e.get('type') == 'rescue' and e.get('why') == 'voice' or (e.get('type') == 'voicefeed' and e.get('via') == 'lost')]
    t_lost = min((e['_rt'] for e in lost)) if lost else None
    if lost:
        refused_voice = any((e.get('type') == 'voicefeed' and re.search('\\b(401|402|403|429)\\b|quota|credit', str(e.get('error'))) for e in evs))
        fail('voice-lost', 'OUTSIDE' if refused_voice else 'CODE')
    lo = [str(e.get('state')) for e in evs if e.get('type') == 'lineout']
    lo_rings = [str(e.get('state')) for e in evs if e.get('type') == 'ringowner' and str(e.get('reason', '')).startswith('line out')]
    joined = any((e.get('type') in ('prompt', 'ready') for e in evs))
    spoke = bool(ours) or any((e.get('type') in ('say1', 'speech') for e in evs))
    fired = 'fire' in lo
    if fired:
        if 'error' in lo:
            fail('down-broke', 'CODE')
        if 'noclip' in lo or 'clip' not in lo:
            fail('down-not-told', 'CODE')
        if 'off' in lo or not (set(lo_rings) & {'ringing', 'answered', 'told', 'noanswer'} or 'ring' in lo):
            fail('down-not-rung', 'CODE')
    elif not spoke:
        fail('down-silent', 'OUTSIDE' if quota or not joined else 'CODE')
    elif 'error' in lo:
        fail('down-broke', 'CODE', heard=False)
    else:
        res['P5']['result'] = 'no need'
    if 'off' in lo:
        fail('lineout-off', 'OUTSIDE')
    if not spoke:
        fail('no-answer' if joined else 'never-joined', 'OUTSIDE' if quota or not joined else 'CODE')
        for p in ('P2', 'P3', 'P4', 'P7'):
            res[p] = {'result': 'no need', 'why': ['the receptionist never spoke in this call']}
        res['P6'] = {'result': 'no need', 'why': ['the receptionist never spoke in this call']}
        return out(_done(call, res, problems, ears, {'n': 0}, names, now, pending=False, line=line))
    elif ours and (not (t_lost is not None and t_lost <= ours[0]['_rt'])):
        g = ours[0].get('text') or ''
        before_q = g.split('?')[0]
        if not (re.search('(?i)\\brecord(ed|ing)\\b', before_q) and re.search('\\bAI\\b|(?i:artificial)', before_q)):
            fail('notice', 'CODE')
        s1 = next((e.get('_rt') for e in evs if e.get('type') in ('say1', 'speech', 'turn') and e.get('role', 'assistant') == 'assistant'), None)
        if cal_t and s1 is not None and (s1 - cal_t[0] > PICKUP_SLOW):
            fail('asleep' if rec_t and rec_t[0] - cal_t[0] > AGENT_LATE else 'pickup-slow', 'OUTSIDE' if rec_t and rec_t[0] - cal_t[0] > AGENT_LATE else 'CODE')
    sp = {'n': 0, 'skipped': 'credit'} if quota else tools.speed(cfg, call, until=t_lost)
    if sp.get('running'):
        return out(dict(_done(call, res, problems, ears, sp, names, now, pending=True, line=line), speedRunning=True))
    em = [e for e in evs if e.get('type') == 'emergency']
    down_rings = [e for e in evs if e.get('type') == 'ringowner' and str(e.get('reason', '')).startswith('line trouble')]
    if down_rings and (not fired):
        if not {str(e.get('state')) for e in down_rings} & {'ringing', 'answered', 'told', 'noanswer'}:
            fail('down-not-rung', 'CODE')
        elif res['P5']['result'] == 'no need':
            res['P5']['result'] = 'pass'
    rings = [e for e in evs if e.get('type') == 'ringowner' and (not str(e.get('reason', '')).startswith('line '))]
    states = {str(e.get('state')) for e in rings}
    ring_win = (min((e['_rt'] for e in rings)), max((e['_rt'] for e in rings)) + 8.0) if rings else None
    pats = [re.compile(p) for p in (line or {}).get('emergency') or []]
    if unknown:
        ear('P4', "this call's business is not known to the watcher, so its emergency words were not checked")
    never = (line or {}).get('never') or []
    owner_names = [w for w in re.findall('[A-Z][a-z]+', str((line or {}).get('owner') or ''))]
    for e in ours:
        owner_names += [w for w in OWNER_BY.findall(e.get('text') or '') if w not in NOT_A_NAME and w not in str((line or {}).get('business') or '') and (w not in ' '.join(map(str, names)).split())]
    said_em, danger = (False, set())
    for e in users:
        t = (e.get('text') or '').lower()
        for n in never:
            t = t.replace(n, ' ')
        for sent in re.split('(?<=[.?!])\\s+', t):
            hz = hazard(sent)
            danger.add(hz)
            if any((p.search(sent) for p in pats)):
                soft = hz == 'unclear' and (not any((p.search(SOFT_EM.sub(' ', sent)) for p in pats)))
                said_em = said_em or not soft
    if em:
        if any((e.get('ring') is True or str(e.get('ring')).lower() == 'true' for e in em)):
            if not states & {'ringing', 'answered', 'told', 'noanswer'}:
                fail('ring-failed' if states & {'refused', 'off'} else 'emergency-no-ring', 'OUTSIDE' if states == {'refused'} else 'CODE')
            elif not states & {'answered', 'told'}:
                fail('no-key-press', 'OUTSIDE', heard=False)
                t_ring = min((e['_rt'] for e in rings))
                kinds = {owner_kind(x, owner_names, (line or {}).get('ownerPronoun')) for e in ours if e['_rt'] >= t_ring for x in ec.sentences(e.get('text'))}
                if 'claim' in kinds:
                    fail('emergency-not-reached', 'CODE')
                elif 'unclear' in kinds:
                    ear('P4', "after a ring nobody pressed a key on, the receptionist said something the watcher can't read as plainly honest about the owner; listen whether it said the owner knows")
        elif all((str(e.get('why')) != 'again' for e in em)):
            ear('P4', 'an emergency was heard but the owner was not rung on purpose; listen to why')
    elif rings:
        res['P4']['result'] = 'pass'
    elif said_em and (not unknown):
        if 'clear' in danger:
            fail('emergency-no-ring', 'CODE')
        elif any((e.get('type') == 'sensenot' for e in evs)):
            ear('P4', 'the caller used an emergency word and the receptionist judged it was no emergency')
        else:
            fail('emergency-no-ring', 'CODE')
    elif 'clear' in danger and (not unknown):
        fail('emergency-no-ring', 'CODE')
    elif 'unclear' in danger and (not unknown):
        ear('P4', "the caller spoke of water, gas, smoke or fire in words the watcher can't read either way; listen whether it was an emergency")
    elif not unknown:
        res['P4']['result'] = 'no need'
    caller_left_early = not any((e.get('type') in ('end', 'byehang') for e in evs)) and (not any((ec.BYE_RE.search(e.get('text') or '') for e in ours)))
    no_booking = bool(em) or caller_left_early or (not any((e.get('type') == 'namenote' for e in evs)) and (not any((e.get('type') == 'tool' and str(e.get('name')).endswith('_hold_date') for e in evs))))
    chk = tools.elijah_check(cfg, events_path, no_booking=no_booking)
    if 'error' in chk:
        problems.append({'slug': 'check-broke', 'sort': 'CHECK IS WRONG', 'promise': None, 'words': CHECK_WRONG['check-broke'], 'heard': False})
        for p in ('P2', 'P3', 'P7'):
            ear(p, 'the call check could not read this call')
    else:
        byes = [e for e in ours if ec.BYE_RE.search(e.get('text') or '') and '?' not in (e.get('text') or '')]
        end = any((e.get('type') in ('end', 'byehang') for e in evs))
        secs = _num(note.get('seconds'))
        hung_checked = False
        for ok, name in chk['checks']:
            info = check_info(name)
            if info is not None and info[1] == 'no-hangup':
                hung_checked = True
                if ok and (not end) and byes and (secs is not None) and (secs - byes[-1]['_rt'] > BYE_GAP):
                    ok = False
                elif ok and (not end) and (not byes or secs is not None):
                    hang_note = 'the caller hung up first, {:.1f} s after the goodbye'.format(secs - byes[-1]['_rt']) if byes else 'the caller hung up first, before any goodbye'
            if ok or info is None:
                continue
            promise, slug, words = info
            if slug == 'no-hangup':
                left = any((e.get('type') == 'end' and e.get('why') == 'caller_left' for e in evs))
                if left or (not end and (not byes or (secs is not None and secs - byes[-1]['_rt'] <= BYE_GAP))):
                    hang_note = 'the caller hung up first, {:.1f} s after the goodbye'.format(secs - byes[-1]['_rt']) if byes else 'the caller hung up first, before any goodbye'
                    continue
                if end and (not byes) and down_rings:
                    ear('P7', 'the receptionist ended a call with line trouble without a goodbye; listen whether that was right')
                    continue
            if slug == 'said-twice' and ring_win and (not _repeats_outside(ec, ours, ring_win)):
                ear('P7', "a line was said again while the owner's phone rang; listen whether that was right")
                continue
            fail(slug, blame(slug), promise, words)
        have = {p['slug'] for p in problems}
        own = dates.faults(evs)
        for slug in ('booked-unheld', 'date-unbacked', 'card-date-unheld'):
            if own[slug] and slug not in have:
                promise, _, words = next((i for i in (check_info(n) for n in ('13 ', '12 ', '13 a card')) if i and i[1] == slug))
                fail(slug, blame(slug), promise, words)
        if own['date-unclear'] and res['P3']['result'] == 'pass' and (not have & {'booked-unheld', 'date-unbacked'}):
            ear('P3', "a date was said before anything was held, in words the watcher can't read either way; listen whether it was said as booked")
        if no_booking:
            for p in ('P2', 'P3'):
                if res[p]['result'] == 'pass' and (not _p3_evidence(evs, p)):
                    res[p]['result'] = 'no need'
    if not em and (not caller_left_early) and any((e.get('type') == 'namenote' for e in evs)):
        ids = {str(ready.get('callId') or ''), str(note.get('room') or '').replace('+', ''), str(note.get('room') or '')} - {''}
        rows = mail_for(cfg, ids, call.hung_up)
        if rows is None:
            ear('P2', "the owner's email could not be read here")
        elif not rows:
            if now - call.hung_up < cfg.mail_wait:
                return out(_done(call, res, problems, ears, sp, names, now, pending=True, line=line))
            fail('no-email', blame('no-email'))
        else:
            t = rows[-1].get('text') or ''
            got = {'name': _field(t, 'Caller') not in ('', 'not given'), 'number': bool(re.search('\\d{4}', _field(t, 'Call back on'))), 'job': _field(t, 'What') not in ('', 'not said')}
            if not all(got.values()):
                fail('email-short', blame('email-short'))
    if any((e.get('type') == 'ttsrunaway' for e in evs)):
        ear('P7', 'the voice ran long once in this call')
    _speed(res, sp, fail, problems, outside=quota)
    if t_lost is not None and (not sp.get('n')) and ('error' not in sp) and (not quota):
        res['P6'] = {'result': 'no need', 'why': ['the receptionist lost its voice before any reply; the caller heard backup clips']}
    if res['P7']['result'] == 'pass':
        res['P7']['result'] = 'needs ears'
        res['P7']['why'].append('everything code can check passed; how it sounds next to rivals needs ears')
    return out(_done(call, res, problems, ears, sp, names, now, pending=False, line=line))

def _no_rows(cfg, call, res, problems, ears, fail, ear, rec_t, now, line) -> dict:
    sound = _right_side_sound(call.wav) if call.wav.exists() else None
    if not rec_t or sound is False:
        fail('never-joined', 'OUTSIDE')
        fail('down-silent', 'OUTSIDE')
        for p in ('P2', 'P3', 'P4', 'P7'):
            res[p] = {'result': 'no need', 'why': ['the receptionist never spoke in this call']}
        res['P6'] = {'result': 'no need', 'why': ['the receptionist never spoke in this call']}
        return _done(call, res, problems, ears, {'n': 0}, [], now, pending=False, line=line)
    fail('no-record', 'CODE')
    for p in ('P2', 'P3', 'P4', 'P5', 'P7'):
        ear(p, 'the receptionist left no record of this call; listen to the recording')
    sp = tools.speed(cfg, call)
    if sp.get('running'):
        return dict(_done(call, res, problems, ears, sp, [], now, pending=True, line=line), speedRunning=True)
    _speed(res, sp, fail, problems, outside=False)
    return _done(call, res, problems, ears, sp, [], now, pending=False, line=line)

def _repeats_outside(ec, ours, win) -> bool:
    seen = set()
    for e in ours:
        for s in ec.sentences(e.get('text')):
            k = ec.key(s)
            if len(s.split()) >= 4 and k in seen and (not win[0] <= (e.get('_rt') or 0) <= win[1]):
                return True
            seen.add(k)
    return False

def _p3_evidence(evs, p) -> bool:
    if p == 'P3':
        return any((e.get('type') in ('tool', 'slot') for e in evs))
    return any((e.get('type') == 'namenote' or (e.get('type') == 'tool' and re.search('(read_number|call_card)$', str(e.get('name')))) for e in evs))

def _speed(res, sp, fail, problems, outside: bool) -> None:
    if outside:
        res['P6'] = {'result': 'not judged', 'why': ['the model ran out of credit in this call, so its speed is not judged']}
    elif 'error' in sp:
        res['P6'] = {'result': 'not judged', 'why': ['the recording could not be read for speed']}
        problems.append({'slug': 'speed-reader-broke', 'sort': 'CHECK IS WRONG', 'promise': None, 'words': CHECK_WRONG['speed-reader-broke'], 'heard': False})
    elif not sp.get('n'):
        res['P6'] = {'result': 'no need', 'why': ['no reply after the caller spoke']}
    elif sp['over']:
        fail('slow', 'WALL')
        res['P6']['why'] = [f"slowest reply {sp['worst']:.2f} s at our end, {sp['over']} of {sp['n']} over 0.5 s"]

def _done(call, res, problems, ears, sp, names, now, pending, line) -> dict:
    return {'call': call.label, 'robot': call.robot, 'hungUp': call.hung_up, 'judgedAt': now, 'judgedAfter': round(now - call.hung_up, 1), 'pending': pending, 'promises': res, 'problems': problems, 'ears': sorted(set(ears)), 'speed': {k: v for k, v in sp.items() if k != 'late'} if 'error' not in sp else {'error': sp['error'], **({'ran': True} if sp.get('ran') else {})}, 'late': sp.get('late') or [], '_names': names, 'line': (line or {}).get('id', '')}

def apply_skip(v, skip) -> dict:
    if not v or not skip or (not v.get('problems')):
        return v
    gone = [p for p in v['problems'] if p.get('slug') in skip]
    if not gone:
        return v
    v['problems'] = [p for p in v['problems'] if p.get('slug') not in skip]
    words = {p.get('words') for p in gone}
    for r in (v.get('promises') or {}).values():
        if words & set(r.get('why') or []):
            r['why'] = [w for w in r['why'] if w not in words]
            if r.get('result') == 'FAIL' and (not r['why']):
                r['result'] = 'pass'
    v.setdefault('ears', []).extend(('not checked on this line: ' + w for w in sorted((w for w in words if w))))
    return v
