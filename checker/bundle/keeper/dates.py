from __future__ import annotations
import json
import re
MONTHS = 'January February March April May June July August September October November December'.split()
_ORDS = 'first second third fourth fifth sixth seventh eighth ninth tenth eleventh twelfth thirteenth fourteenth fifteenth sixteenth seventeenth eighteenth nineteenth twentieth'.split()
ORD = {w: i + 1 for i, w in enumerate(_ORDS)}
ORD.update({f'twenty {w}': 21 + i for i, w in enumerate(_ORDS[:9])})
ORD.update({f'twenty-{w}': 21 + i for i, w in enumerate(_ORDS[:9])}, thirtieth=30, **{'thirty first': 31, 'thirty-first': 31})
DAY = '(\\d{1,2}(?:st|nd|rd|th)|(?:twenty[ -])?(?:%s)|thirtieth|thirty[ -]first)' % '|'.join(_ORDS)
DAY_NUM = '(\\d{1,2}(?:st|nd|rd|th)?|(?:twenty[ -])?(?:%s)|thirtieth|thirty[ -]first)' % '|'.join(_ORDS)
WEEKDAY = '(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)'
MONTH = '|'.join(MONTHS)
MONTH_DAY = re.compile(f'(?i)\\b({MONTH})\\s+(?:the\\s+)?{DAY_NUM}\\b')
DAY_OF_MONTH = re.compile(f'(?i)\\b(?:the\\s+)?{DAY}\\s+of\\s+({MONTH})\\b')
WD_DAY = re.compile(f'(?i)\\b{WEEKDAY},?\\s+(?:the\\s+)?{DAY}\\b(?!\\s+of\\b)')
ON_THE = re.compile(f'(?i)\\b(?:on|for|by|until|about|after|before)\\s+the\\s+{DAY}\\b(?!\\s+of\\b)(?=\\s*(?:[.,?!;]|$|is\\b|works\\b|would\\b|then\\b|at\\b|or\\b|and\\b|instead\\b|okay\\b|ok\\b))')
THE_NTH = re.compile('(?i)\\bthe\\s+(\\d{1,2}(?:st|nd|rd|th))\\b(?!\\s+of\\b)')
WORD_DAY = '((?:twenty[ -])?(?:%s)|thirtieth|thirty[ -]first)' % '|'.join(_ORDS)
THE_WORD = re.compile(f'(?i)\\bthe\\s+{WORD_DAY}\\b(?!\\s+of\\b)(?=\\s*(?:[.,?!;]|$|is\\b|works?\\b|would\\b|could\\b|suits?\\b|then\\b|at\\b|or\\b|and\\b|instead\\b|okay\\b|ok\\b|good\\b|fine\\b|be\\b|do\\b|does\\b|sounds?\\b|in the (?:morning|afternoon)\\b|morning\\b|afternoon\\b|for (?:you|the move|your move)\\b))')
NOT_A_DAY = re.compile('(?i)\\b(?:floors?|stor(?:y|ies|ey|eys)|levels?|bedrooms?|rooms?|stairs?|steps?|units?|apartments?|times?|tries|try|attempts?|items?|boxes|trucks?|ones?|things?|questions?|letters?|digits?|names?|places?|half)\\b')
ISO = re.compile('\\b(20\\d\\d)-(\\d\\d)-(\\d\\d)\\b')
CLAIM = re.compile("(?i)\\b(?:got you down|have you down|put you down|you're down for|you are down for|pencil(?:l)?ed (?:you |it |that |this )?(?:in|down)|(?:you're|you are|you've been|you have been)\\s+(?:all\\s+)?(?:booked|set|scheduled|confirmed|reserved|locked in|on the (?:calendar|schedule|books))|(?:it's|it is|that's|that is|this is|which is|date is|day is|move is)\\s+(?:all\\s+)?(?:booked|reserved|confirmed|scheduled|locked in|held|on hold|on the (?:calendar|schedule|books)|pencil(?:l)?ed in)|(?:is|are)\\s+(?:booked|reserved|confirmed|scheduled|locked in|pencil(?:l)?ed in|on hold)\\b|(?:i've|i have|we've|we have|i|we)\\s+(?:just\\s+|now\\s+)?(?:booked|reserved|scheduled|held|locked in|pencil(?:l)?ed(?: in)?|put a hold on|placed a hold on|saved)\\b|booked you|reserved (?:it |that |the date |the day )?for you|locked (?:you |it |that )?in|all set for|(?:have|got) you (?:booked|scheduled|reserved|on the (?:calendar|schedule|books))|(?:holding|have a hold on|got a hold on) (?:it|that|the date|the day|\\w+day)\\b)")
CLAIM_MORE = re.compile("(?i)\\b(?:(?:we'll|we will|they'll|they will|sam will|he'll|she'll|the crew will|our crew will|the movers will|our movers will)\\s+(?:be there|see you|arrive|come|show up)|see you (?:on|then|that)|it's a date|you're on for|(?:the |our )?(?:crew|movers|truck|team) (?:is|are) (?:coming|booked|scheduled|set)|booked in)\\b")
NEGATED = re.compile("(?i)\\b(?:not|never|no longer|isn't|aren't|wasn't|weren't|haven't|hasn't|hadn't|didn't|couldn't|can't|cannot|won't|wouldn't|unable)\\b")
CONDITION = re.compile('(?i)\\b(?:if|once|until|before|whether|unless|when|after|as soon as)\\b')
LATER = re.compile("(?i)\\b(?:i'll|i will|we'll|we will|i'm going to|we're going to|going to|gonna|let me|let's|want me to|like me to|shall i|should i|can i|could i|may i|i can|we can|i could|we could|try(?:ing)? to|able to|need to|have to|happy to|ready to|want to|like to)\\s+(?:\\w+\\s+){0,3}?(?:book|hold|reserve|schedule|pencil|lock|put|get|set|confirm|save|place|keep|add)\\w*\\b")
MAYBE_BE = re.compile('(?i)\\b(?:would|could|should|might|may|will)\\s+(?:\\w+\\s+)?be\\b')
TAKEN = re.compile('(?i)\\b(?:already|fully|booked up|taken|full|unavailable|sorry|unfortunately|afraid)\\b')
THIRD = re.compile("(?i)^(?:it's|it is|that's|that is|this is|which is|date is|day is|move is|is|are)\\b")
BOOKWORD = re.compile('(?i)\\b(?:book|hold|held|reserv|schedul|pencil|lock|confirm)\\w*')
CUT = {'is', 'are', 'was', 'also', 'already', 'still', 'and', 'but', 'then', 'that'}
CLAUSE = re.compile('[,;:]|\\s(?:but|so)\\s|\\s-\\s')
NOT_CLAIM = re.compile("(?i)^(?:would|should|shall|do|does|did|can|could|is|are|will|want|how about|what about)\\b|\\b(?:is|are|'s)\\s+(?:also\\s+|already\\s+|still\\s+)?(?:free|open|available|taken|full|booked up|fully booked|unavailable|closed|a (?:saturday|sunday|holiday|weekend))\\b|\\b(?:we|i|sam|he|she|they)\\s+(?:also\\s+)?(?:have|has|had|'ve got|got)\\s+(?!you\\b)|\\bfree (?:on|dates?|days?)\\b|\\bfirst free\\b|\\bweekdays only\\b|\\bno moves\\b|\\b(?:noted|i've written|wrote down|will confirm|to confirm|confirm (?:it|the date|that)|can't (?:pencil|hold|book|see)|couldn't (?:pencil|hold|book)|check(?:ing)? (?:the calendar|that date|if|whether|availability))\\b|\\b(?:works? for you|work best|suit you|i can offer|we can do|instead)\\b")
DATEISH = re.compile(f"(?i)\\b(?:{MONTH}|{WEEKDAY}|the|on|for|of|\\d{{1,2}}(?:st|nd|rd|th)?|(?:twenty[ -])?(?:{'|'.join(_ORDS)})|thirtieth|thirty[ -]first|okay|ok|so|great|alright|sure|yes|perfect|that's|got it)\\b")

def claim_kind(s: str) -> str:
    if s.endswith('?'):
        return 'no'
    claimed, excused = (False, False)
    for part in CLAUSE.split(s):
        part = part.strip()
        m = CLAIM.search(part) or CLAIM_MORE.search(part)
        if not m:
            continue
        before = part[:m.start()]
        third = bool(THIRD.match(m.group(0)))
        if NEGATED.search(part) or CONDITION.search(before) or LATER.search(part) or MAYBE_BE.search(before) or (third and TAKEN.search(s)):
            excused = True
            continue
        claimed = True
    if claimed:
        return 'unclear' if CONDITION.match(s) else 'claim'
    if excused or NOT_CLAIM.search(s) or (BOOKWORD.search(s) and (NEGATED.search(s) or LATER.search(s) or TAKEN.search(s))):
        return 'no'
    left = re.sub("[^a-z']+", ' ', DATEISH.sub(' ', s.lower())).split()
    if all((w in CUT for w in left)):
        return 'no'
    return 'unclear'
SITE_TYPES = ('tool', 'slot', 'siteearly', 'offered', 'offerhold', 'rehold', 'datememory')

def _day(s: str) -> int | None:
    s = s.lower().replace('-', ' ')
    if s[0].isdigit():
        n = int(re.sub('\\D', '', s))
        return n if 1 <= n <= 31 else None
    return ORD.get(s)

def month_days(text: str) -> set:
    out = set()
    for m in MONTH_DAY.finditer(text or ''):
        d = _day(m.group(2))
        if d:
            out.add((m.group(1).title(), d))
    for m in DAY_OF_MONTH.finditer(text or ''):
        d = _day(m.group(1))
        if d:
            out.add((m.group(2).title(), d))
    for y, mo, d in ISO.findall(text or ''):
        if 1 <= int(mo) <= 12 and 1 <= int(d) <= 31:
            out.add((MONTHS[int(mo) - 1], int(d)))
    return out

def bare_days(text: str) -> set:
    t = text or ''
    covered = [m.span() for r in (MONTH_DAY, DAY_OF_MONTH) for m in r.finditer(t)]
    out = set()
    for r in (WD_DAY, ON_THE, THE_NTH, THE_WORD):
        if r is THE_WORD and NOT_A_DAY.search(t):
            continue
        for m in r.finditer(t):
            if any((a <= m.start(1) < b for a, b in covered)):
                continue
            d = _day(m.group(1))
            if d:
                out.add(d)
    return out

def sentences(text: str) -> list:
    return [s.strip() for s in re.split('(?<=[.?!])\\s+', text or '') if s.strip()]

def _held_dates(e: dict) -> set:
    ty = e.get('type')
    if ty == 'tool' and str(e.get('name')).endswith('_hold_date'):
        res = str(e.get('result') or '').replace(' ', '')
        if '"ok":true' in res and '"held":""' not in res:
            got = month_days(json.dumps((e.get('arguments') or {}).get('date'))) | month_days(_held_field(res))
            return got
    if ty == 'slot' and str(e.get('kind')) == 'hold' and (str(e.get('ok')) in ('True', 'true', '1')):
        return month_days(str(e.get('said') or '')) | month_days(str(e.get('date') or ''))
    if ty == 'rehold':
        res = str(e.get('result') or '').replace(' ', '')
        if '"ok":true' in res:
            return month_days(_held_field(res))
    return set()

def _held_field(res: str) -> str:
    m = re.search('"held":"([^"]*)"', res)
    return m.group(1) if m else ''

def faults(evs: list) -> dict:
    held, known_md, known_days = (set(), set(), set())
    out = {'booked-unheld': [], 'date-unbacked': [], 'card-date-unheld': [], 'date-unclear': []}
    for e in evs:
        ty = e.get('type')
        if ty in SITE_TYPES:
            blob = json.dumps({k: v for k, v in e.items() if k != '_rt'})
            md = month_days(blob)
            known_md |= md
            known_days |= {d for _, d in md} | bare_days(blob)
            held |= _held_dates(e)
            if ty == 'tool' and str(e.get('name')).endswith('_call_card'):
                h = str((e.get('arguments') or {}).get('held') or '').strip()
                said = month_days(h)
                if said and (not said & held):
                    out['card-date-unheld'].append(h[:10])
        elif ty == 'turn' and e.get('role') == 'user':
            t = e.get('text') or ''
            md = month_days(t)
            known_md |= md
            known_days |= {d for _, d in md} | bare_days(t)
        elif ty == 'turn' and e.get('role') == 'assistant':
            last = (set(), set())
            for s in sentences(e.get('text')):
                md, bare = (month_days(s), bare_days(s))
                if any((d not in known_days for d in bare)):
                    out['date-unbacked'].append(s)
                kind = claim_kind(s) if md or bare or CLAIM.search(s) or CLAIM_MORE.search(s) else 'no'
                if kind == 'claim' and (not (md or bare)):
                    md, bare = last
                if (md or bare) and kind == 'claim':
                    held_days = {d for _, d in held}
                    if not held or any((k not in held for k in md)) or any((d not in held_days for d in bare)):
                        out['booked-unheld'].append(s)
                elif (md or bare) and kind == 'unclear' and (not held):
                    out['date-unclear'].append(s)
                if md or bare:
                    last = (md, bare)
    return out
