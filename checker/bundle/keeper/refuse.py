from __future__ import annotations
import hashlib
import hmac
import os
import re
NAMES = ('luterson', 'rl-pub', 'luterson-cloud')
NUMBER_HASHES = {'04bfe8df075a942a', 'e893d69284bafe78'}
SALT = os.environ.get('REFUSE_SALT', '').encode()

def _hash(d: str) -> str:
    return hmac.new(SALT, d.encode(), hashlib.sha256).hexdigest()[:16]

def refused(*texts) -> bool:
    for t in texts:
        s = str(t or '')
        if any((n in s.lower() for n in NAMES)):
            return True
        for run in re.findall('\\+?\\d[\\d ().-]{8,16}\\d', s):
            d = re.sub('\\D', '', run)
            if len(d) == 11 and d[0] == '1':
                d = d[1:]
            if len(d) == 10 and (not SALT or _hash(d) in NUMBER_HASHES):
                return True
    return False
