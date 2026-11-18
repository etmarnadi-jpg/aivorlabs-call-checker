from __future__ import annotations
import re
PHONE = re.compile('\\+\\d[\\d ().-]{6,16}\\d|\\(?\\b[2-9]\\d{2}\\)?[ .-]\\d{3}[ .-]\\d{4}\\b|\\b1?[2-9]\\d{9}\\b')
EMAIL = re.compile('\\b[\\w.+-]+@[\\w-]+\\.[\\w.-]+\\b')
SPELLED = re.compile('(?:\\b[A-Za-z]\\b[,.\\- ]{1,3}){3,}\\b[A-Za-z]\\b')
DIGIT_WORD = '(?:zero|oh|one|two|three|four|five|six|seven|eight|nine)'
SAID_NUMBER = re.compile(f'(?i)\\b{DIGIT_WORD}(?:[\\s,.-]+{DIGIT_WORD}){{6,}}\\b')
ROOM_PHONE = re.compile('_\\+?\\d{6,15}_')

def label(stem: str) -> str:
    s = ROOM_PHONE.sub('phone-', stem)
    return PHONE.sub('number', s)

def scrub(text: str, names=()) -> str:
    t = str(text)
    for n in sorted({w for n in names for w in re.findall("[A-Za-z']{3,}", str(n or ''))}, key=len, reverse=True):
        t = re.sub(f'(?i)\\b{re.escape(n)}\\b', '(name)', t)
    t = EMAIL.sub('(email)', t)
    t = SAID_NUMBER.sub('(number)', t)
    t = SPELLED.sub('(spelled)', t)
    t = ROOM_PHONE.sub('phone-', t)
    t = PHONE.sub('(number)', t)
    return t

def clean(text: str, names=()) -> bool:
    if PHONE.search(text) or EMAIL.search(text) or SPELLED.search(text) or SAID_NUMBER.search(text):
        return False
    return not any((re.search(f'(?i)\\b{re.escape(w)}\\b', text) for n in names for w in re.findall("[A-Za-z']{3,}", str(n or ''))))
