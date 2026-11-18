# Call checker

Checks finished calls of the Aivor Labs test phone lines while the team's own computer is asleep. It runs on GitHub Actions
only when the site starts it (or someone starts it by hand); it has no timer.

What it holds: the judging code and the test lines' patterns. What it never holds: a key, a caller's words, a phone number.
The keys it needs live in this repository's locked Actions secrets (REC_DROP_URL, REC_DROP_READ_KEY, REC_SEAL_KEY, CHECKER_SENTRY_DSN, CHECKER_REFUSE_SALT), each read-only or send-only. The calls it
judges are read from a private drop with a key that can only list and read. Its results go to the team's error tracker.
