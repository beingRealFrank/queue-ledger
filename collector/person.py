"""Filter: owner names that look like a private individual are not republished (same rule as the Apify Actor)."""
import json
import os
import re

_w = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "person_words.json")))
ORG, GIVEN = set(_w["org"]), set(_w["given"])
NAME_WORD = re.compile(r"^[A-Z][a-z'’]+(-[A-Z][a-z'’]+)?$|^(Mc|Mac|O')[A-Z][a-z'’]+$")
INITIAL = re.compile(r"^[A-Z]\.?$")
SUFFIX = re.compile(r"^(jr|sr|ii|iii|iv)\.?$", re.I)


def looks_like_person(raw: str) -> bool:
    """Port of the Actor's person-name filter: owners that look like private individuals are not shown."""
    name = re.sub(r"\s+", " ", (raw or "").strip())
    if not name or re.search(r"[\d&/()@]", name):
        return False
    words = [w for w in re.split(r"[\s,]+", name.lower()) if w]
    if any(w.rstrip(".,") in ORG for w in words):
        return False
    m = re.match(r"^([^,]+),\s*(.+)$", name)
    if m:
        last, first = m.group(1).split(" "), [t for t in m.group(2).split(" ") if not SUFFIX.match(t)]
        return (len(last) == 1 and bool(NAME_WORD.match(last[0])) and 1 <= len(first) <= 2
                and first[0].lower() in GIVEN and all(INITIAL.match(t) or NAME_WORD.match(t) for t in first[1:]))
    toks = [t for t in name.split(" ") if not SUFFIX.match(t)]
    if len(toks) < 2 or len(toks) > 3 or not NAME_WORD.match(toks[-1]):
        return False
    head = toks[:-1]
    if all(INITIAL.match(t) for t in head):
        return True
    return head[0].lower() in GIVEN and all(INITIAL.match(t) or NAME_WORD.match(t) for t in head[1:])
