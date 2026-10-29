"""Password rules for new passwords (sign-up and the admin `seeing-create-user` command).

- at least MIN_LENGTH characters;
- at least 3 of the 4 kinds: lower-case letter, upper-case letter, digit, other character;
- not built on a common password or a keyboard run ("Azerty123456!", "P@ssw0rd2026" are refused):
  the letters of the password, with the usual digit/symbol substitutions undone, must not be a
  common word or a keyboard run, or be made of one repeated character;
- must not contain the part of the e-mail before the "@" (when it has 3 characters or more).

`password_problem()` returns a short code the web page turns into a message, or None.
"""

import re

MIN_LENGTH = 12

COMMON = frozenset(
    """
    password passwd motdepasse mdp azerty qwerty qwertz azertyuiop qwertyuiop asdfgh azertyui abcdef abcdefgh
    abc letmein welcome bienvenue bonjour salut soleil iloveyou jetaime admin administrator root user login
    test master dragon monkey football baseball soccer shadow sunshine princess superman batman starwars
    trustno hello coucou chouchou doudou loulou nicolas thomas camille marseille paris france chocolat
    secret changeme default seeing seeingthesky arome astro astronomie telescope etoile etoiles star stars
    galaxie nebuleuse jupiter saturne
    """.split()
)
KEYBOARD_RUNS = ("azertyuiopqsdfghjklmwxcvbn", "qwertyuiopasdfghjklzxcvbnm", "abcdefghijklmnopqrstuvwxyz")
LEET = str.maketrans({"0": "o", "1": "i", "3": "e", "4": "a", "5": "s", "7": "t", "8": "b", "@": "a", "$": "s", "!": "i"})


def kinds(password: str) -> int:
    """Number of character kinds used: lower, upper, digit, other."""
    return sum(
        (
            any(c.islower() for c in password),
            any(c.isupper() for c in password),
            any(c.isdigit() for c in password),
            any(not c.isalnum() for c in password),
        )
    )


def _letters(password: str) -> set[str]:
    """The letters of the password, as typed and with the digit/symbol substitutions undone."""
    low = password.lower()
    return {re.sub(r"[^a-z]", "", low), re.sub(r"[^a-z]", "", low.translate(LEET))}


def _weak(letters: str) -> bool:
    if not letters:  # no Latin letter at all (digits and symbols are already limited by kinds())
        return False
    if len(set(letters)) == 1 or letters in COMMON or _keyboard_run(letters):
        return True
    # a common word with a short decoration ("monkey2026!!", "2026soleil")
    return any((letters.startswith(w) or letters.endswith(w)) and len(letters) - len(w) <= 3 for w in COMMON if len(w) >= 4)


def _keyboard_run(s: str) -> bool:
    return len(s) >= 4 and any(s in run or s[::-1] in run for run in KEYBOARD_RUNS)


def password_problem(password: str, email: str | None = None) -> str | None:
    """None when the password follows the rules, else one of: too_short, too_simple, too_common,
    contains_email."""
    if len(password) < MIN_LENGTH:
        return "too_short"
    if kinds(password) < 3:
        return "too_simple"
    if any(_weak(v) for v in _letters(password)):
        return "too_common"
    local = (email or "").split("@", 1)[0].strip().lower()
    if len(local) >= 3 and local in password.lower():
        return "contains_email"
    return None
