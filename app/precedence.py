"""Source Precedence Policy (Annex A.1/A.2) in plain code. Owner: A6 precedence.

Order: applicability -> supersession -> authority -> recency -> unresolved.
Authority levels: 1 articles/policies, 2 release notes, 3 tool results (not chunks),
4 resolved tickets, 5 community posts. A lower number always wins.

The only LLM use is ONE batched yes/no "do these two texts disagree?" call per request
(prompt "disagreement"), shared by steps 3-5. Its fallback, which is also the MOCK_LLM
behaviour, is a small deterministic heuristic that only counts real contradiction signals:
a doc warning against what a ticket recommends, insecure advice, a different or outdated figure,
or "ask support" where the doc gives self-serve steps. Every keep/drop decision is made here in code.
"""
import datetime
import json
import re

from app import llm, retrieval
from app.schemas import Conflict, DisagreementResult, Disagreements

DOC_LEVELS = (1, 2)    # articles, policies, release notes
LOW_LEVELS = (4, 5)    # resolved tickets, community posts
PROMPT_TEXT_CHARS = 800  # ponytail: each text is cut to one chunk's size so the batched prompt fits a 7B context

ERROR_CODE = re.compile(r"CF-\d{3}", re.I)
# "never / do not X": X is what the text warns against.
WARNING = re.compile(r"\b(?:never|do not|don['’]t|should not|must not)[*_]*\s+([^.!?\n]*)", re.I)
# Heuristic's built-in safety warning: ticket advice that switches off a security control contradicts the docs.
INSECURE = re.compile(r"\b(?:allow|enabl\w*)\s+\W?insecure|\b(?:disabl\w*|turn\w*\s+off|switch\w*\s+off|"
                      r"stop\w*\s+verifying)\s+(?:the\s+)?(?:ssl|tls|certificate|verification|2fa|two-factor)", re.I)
# A negated clause ("did not share any link ...") is not a recommendation; removed before matching.
NEGATED = re.compile(r"\b(?:not|never|no|avoid|cannot|without|\w+n['’]t)\b[^.!?\n]*", re.I)
# A sentence in which a doc calls older advice out of date.
OUTDATED = re.compile(r"[^.!?\n]*\b(?:out of date|outdated|no longer)\b[^.!?\n]*", re.I)
NUMBER_UNIT = re.compile(r"(\d[\d,]*)\s+(?:api\s+|workflow\s+)?(call|request|run|seat|day|hour|row|retr)", re.I)
# "email support with ...", "ask support to ...": the customer has to go through support.
ASK_SUPPORT = re.compile(r"\b(?:contact|email|e-mail|ask|message|wait for|reach out to)\s+(?:\w+\s+)?support\s+"
                         r"(?:to|so|and|with|for)\b", re.I)
# Numbered steps or a menu path ("Settings → Run history"): the customer can do it alone.
SELF_SERVE = re.compile(r"^\s*\d+\.\s|→|->", re.M)
STOPWORDS = {"the", "and", "for", "with", "you", "your", "this", "that", "from", "are", "was", "were",
             "has", "have", "had", "not", "but", "can", "will", "then", "into", "our", "its", "all",
             "any", "per", "they", "them", "their", "when", "what", "how", "customer", "question",
             "resolution", "accepted", "answer"}


# Apply the Annex A.2 rules to retrieved chunks.
# Returns {"applicable": [chunks], "conflicts": [Conflict], "upcoming_changes": [str],
#          "unresolved": [(source_id, source_id)], "usage": {llm usage of the disagreement check}}.
def apply_precedence(chunks: list[dict], customer_version: str | None, as_of_date: datetime.date) -> dict:
    applicable, upcoming, conflicts = applicability(chunks, customer_version, as_of_date)
    applicable, found = supersession(applicable)
    conflicts += found
    # Steps 3-5 share one batched disagreement check over sources that share a topic.
    pairs = topic_pairs(applicable)
    verdicts, usage = check_disagreements(pairs)
    applicable, found = authority(applicable, pairs, verdicts)
    conflicts += found
    applicable, found = recency(applicable, pairs, verdicts)
    conflicts += found
    applicable.sort(key=lambda c: (int(c["meta"]["authority_level"]), -float(c.get("score") or 0)))
    unique = {(c.winner, c.loser, c.rule): c for c in conflicts}
    return {"applicable": applicable, "conflicts": list(unique.values()), "upcoming_changes": upcoming,
            "unresolved": unresolved(pairs, verdicts), "usage": usage}


# Step 1: keep chunks that cover the customer's version and are in effect on as_of_date.
# Future deprecations become upcoming changes; past deprecations are dropped as conflicts.
def applicability(chunks: list[dict], customer_version: str | None, as_of_date) -> tuple[list, list, list]:
    code = _customer_code(customer_version)
    today = str(as_of_date)
    kept, upcoming, conflicts = [], [], []
    for chunk in chunks:
        meta = chunk["meta"]
        low, high = int(meta.get("version_min") or 0), int(meta.get("version_max") or 9999)
        if code is not None and not low <= code <= high:
            continue
        if meta.get("effective_from") and meta["effective_from"] > today:
            continue
        deprecated_on = meta.get("deprecated_on") or ""
        if deprecated_on and deprecated_on <= today:
            conflicts.append(Conflict(winner=_announcer(chunk, chunks), loser=meta["source_id"], rule="deprecation"))
            continue
        if deprecated_on:
            note = f"{meta.get('title', meta['source_id'])} ({meta['source_id']}) stops applying on {deprecated_on}."
            if note not in upcoming:
                upcoming.append(note)
        kept.append(chunk)
    return kept, upcoming, conflicts


# Step 2: drop any chunk whose source_id is listed in another applicable chunk's `supersedes`.
# Also drop tickets/posts on the superseded article's subject (its title words) resolved before the
# replacement took effect: they describe the old procedure.
# Step 1 already removed sources not yet in effect, so every superseding source here is in effect.
def supersession(chunks: list[dict]) -> tuple[list, list]:
    replaced_by = {}  # old id -> (new id, date the new one took effect)
    for chunk in chunks:
        meta = chunk["meta"]
        for old_id in (meta.get("supersedes") or "").split(";"):
            if old_id.strip() and old_id.strip() != meta["source_id"]:
                since = meta.get("effective_from") or meta.get("last_updated", "")
                replaced_by.setdefault(old_id.strip(), (meta["source_id"], since))
    old_titles = {c["meta"]["source_id"]: _stems(c["meta"].get("title", "")) for c in chunks
                  if c["meta"]["source_id"] in replaced_by}
    losers = {}  # loser id -> winner id
    for chunk in chunks:
        meta = chunk["meta"]
        if meta["source_id"] in replaced_by:
            losers[meta["source_id"]] = replaced_by[meta["source_id"]][0]
        elif int(meta["authority_level"]) in LOW_LEVELS:
            words = _stems(meta.get("title", "") + " " + chunk["text"])
            for old_id, title in old_titles.items():
                new_id, since = replaced_by[old_id]
                if len(title) >= 2 and title <= words and meta.get("last_updated", "") < since:
                    losers.setdefault(meta["source_id"], new_id)
    conflicts = [Conflict(winner=w, loser=l, rule="supersession") for l, w in losers.items()]
    return _drop(chunks, set(losers)), conflicts


# Step 3: a ticket or community post that contradicts a doc on the same topic is dropped (docs win).
# It is recorded once, against the most specific doc (most shared topic keys, then best score).
# Agreeing ones stay as supporting detail.
def authority(chunks: list[dict], pairs: list[dict], verdicts: dict) -> tuple[list, list]:
    hits = [p for p in pairs if p["kind"] == "authority" and verdicts[p["pair_id"]]]
    hits.sort(key=lambda p: (len(p["a"]["keys"] & p["b"]["keys"]), p["a"]["score"]), reverse=True)
    winners = {}  # loser id -> winner id
    for p in hits:
        winners.setdefault(p["b"]["id"], p["a"]["id"])
    conflicts = [Conflict(winner=w, loser=l, rule="authority") for l, w in winners.items()]
    return _drop(chunks, set(winners)), conflicts


# Step 4: two same-authority docs that disagree -> the newer last_updated wins.
def recency(chunks: list[dict], pairs: list[dict], verdicts: dict) -> tuple[list, list]:
    conflicts = [Conflict(winner=p["a"]["id"], loser=p["b"]["id"], rule="recency")
                 for p in pairs if p["kind"] == "recency" and verdicts[p["pair_id"]]
                 and p["a"]["date"] != p["b"]["date"]]
    return _drop(chunks, {c.loser for c in conflicts}), conflicts


# Step 5: same authority, same date, still disagreeing -> unresolved; both stay for the handoff bundle.
def unresolved(pairs: list[dict], verdicts: dict) -> list[tuple[str, str]]:
    return [(p["a"]["id"], p["b"]["id"]) for p in pairs
            if p["kind"] == "recency" and verdicts[p["pair_id"]] and p["a"]["date"] == p["b"]["date"]]


# Find source pairs that could conflict: same topic key and a shared product version.
# "authority" pairs: doc (a) vs ticket/community (b). "recency" pairs: same-level docs, newer (a) vs older (b).
def topic_pairs(chunks: list[dict]) -> list[dict]:
    sources = _sources(chunks)
    docs = [s for s in sources if s["level"] in DOC_LEVELS]
    lows = [s for s in sources if s["level"] in LOW_LEVELS]
    found = [("authority", doc, low) for low in lows for doc in docs if _related(doc, low)]
    for i, first in enumerate(docs):
        for second in docs[i + 1:]:
            if first["level"] == second["level"] and _related(first, second):
                newer, older = (first, second) if first["date"] >= second["date"] else (second, first)
                found.append(("recency", newer, older))
    return [{"pair_id": f"P{n}", "kind": kind, "a": a, "b": b} for n, (kind, a, b) in enumerate(found, 1)]


# ONE batched LLM call that says which pairs disagree; none at all when there are no pairs.
# Pairs the model skips (or every pair, on MOCK/invalid output) use the heuristic verdict.
def check_disagreements(pairs: list[dict]) -> tuple[dict, dict]:
    if not pairs:
        return {}, {"prompt_tokens": 0, "completion_tokens": 0, "calls": 0, "model": "none"}
    verdicts = {p["pair_id"]: _heuristic_disagree(p) for p in pairs}
    payload = json.dumps([{"pair_id": p["pair_id"], "doc_text": p["a"]["text"][:PROMPT_TEXT_CHARS],
                           "ticket_text": p["b"]["text"][:PROMPT_TEXT_CHARS]} for p in pairs])
    fallback = lambda: Disagreements(results=[DisagreementResult(pair_id=k, disagree=v) for k, v in verdicts.items()])
    result, usage = llm.call_json("disagreement", {"pairs": payload}, Disagreements, fallback)
    verdicts.update({r.pair_id: r.disagree for r in result.results if r.pair_id in verdicts})
    return verdicts, usage


# Mock/fallback verdict. Only real contradiction signals count; texts that merely cover different
# points (few shared words) are NOT a disagreement. Two docs (recency) only clash on figures, because
# docs often mention old advice or exceptions in passing.
def _heuristic_disagree(pair: dict) -> bool:
    doc, other = pair["a"]["text"], pair["b"]["text"]
    if _numbers_clash(doc, other):
        return True
    if pair["kind"] != "authority":
        return False
    # Only the resolution / accepted answer is advice (not the customer's question), and a negated
    # clause such as "did not disable 2FA" recommends nothing.
    advice = NEGATED.sub(" ", _resolution(other))
    return _warns_against(doc, advice) or bool(INSECURE.search(advice)) or _support_vs_self_serve(doc, advice)


# True when the doc says "never/do not X" and one sentence of the advice recommends X: the word
# right after "never/do not" (e.g. "disable") plus at least one more of X's first four words.
def _warns_against(doc: str, advice: str) -> bool:
    sentences = [set(_words(s)) for s in re.split(r"[.!?\n]", advice)]
    for phrase in WARNING.findall(doc):
        head = _words((phrase.split() or [""])[0])  # empty for "never a good idea": no action named
        warned = set(_words(phrase)[:4])
        if head and any(head[0] in s and len(warned & s) >= 2 for s in sentences):
            return True
    return False


# True when the other text gives a figure the doc calls out of date, or gives figures for a unit
# the doc also quantifies with none in common (e.g. "120 calls" vs "300 calls").
def _numbers_clash(doc: str, other: str) -> bool:
    doc_figures = _figures(doc)
    outdated = {n.replace(",", "") for line in OUTDATED.findall(doc) for n in re.findall(r"\d[\d,]*", line)}
    for unit, numbers in _figures(other).items():
        if numbers & outdated or (doc_figures.get(unit) and not numbers & doc_figures[unit]):
            return True
    return False


# Numbers written next to a unit, e.g. "120 API calls, 7 days" -> {"call": {"120"}, "day": {"7"}}.
def _figures(text: str) -> dict[str, set[str]]:
    found = {}
    for number, unit in NUMBER_UNIT.findall(text):
        found.setdefault(unit.lower(), set()).add(number.replace(",", ""))
    return found


# True when the ticket sends the customer through support ("email support with ...") while the doc
# gives self-serve steps and does not itself say to contact support: old tickets often do this.
def _support_vs_self_serve(doc: str, resolution: str) -> bool:
    return bool(ASK_SUPPORT.search(resolution) and SELF_SERVE.search(doc) and not ASK_SUPPORT.search(doc))


# The resolution part of a ticket (or accepted answer of a post); the whole text if not marked.
def _resolution(text: str) -> str:
    return re.split(r"resolution\s*:|accepted answer", text, flags=re.I)[-1]


# Lower-case content words cut to 4 letters, in order, so "retry"/"retries" and "disable"/"disables" match.
def _words(text: str) -> list[str]:
    return [w[:4] for w in re.findall(r"[a-z0-9]+", text.lower()) if len(w) >= 3 and w not in STOPWORDS]


# The same words as a set.
def _stems(text: str) -> set[str]:
    return set(_words(text))


# Group chunks by source: id, level, date, version range, best score, joined text and topic keys.
def _sources(chunks: list[dict]) -> list[dict]:
    groups = {}
    for chunk in chunks:
        meta = chunk["meta"]
        group = groups.setdefault(meta["source_id"], {
            "id": meta["source_id"], "level": int(meta["authority_level"]), "date": meta.get("last_updated", ""),
            "vmin": int(meta.get("version_min") or 0), "vmax": int(meta.get("version_max") or 9999),
            "score": 0.0, "text": "", "keys": set()})
        group["score"] = max(group["score"], float(chunk.get("score") or 0))
        group["text"] += chunk["text"] + "\n"
        group["keys"] |= _topic_keys(chunk)
    return list(groups.values())


# Topic keys of a chunk: its tags plus any CF-xxx error codes in its text or tags (lower-case).
def _topic_keys(chunk: dict) -> set[str]:
    tags = chunk["meta"].get("tags") or ""
    if isinstance(tags, list):
        tags = ";".join(tags)
    keys = {t.strip().lower() for t in re.split(r"[;,]", tags) if t.strip()}
    return keys | {code.lower() for code in ERROR_CODE.findall(chunk["text"] + " " + tags)}


# Two sources can only conflict if they share a topic key and cover a common product version.
def _related(a: dict, b: dict) -> bool:
    return bool(a["keys"] & b["keys"]) and a["vmin"] <= b["vmax"] and b["vmin"] <= a["vmax"]


# Remove every chunk whose source_id is in `losers`.
def _drop(chunks: list[dict], losers: set[str]) -> list[dict]:
    return [c for c in chunks if c["meta"]["source_id"] not in losers]


# Who made a source obsolete: a release note (else any other source) mentioning its ID or
# deprecation date; "as_of_date" when no such source was retrieved.
def _announcer(dead: dict, chunks: list[dict]) -> str:
    dead_id, date = dead["meta"]["source_id"], dead["meta"]["deprecated_on"]
    for chunk in sorted(chunks, key=lambda c: c["meta"].get("doc_type") != "release_note"):
        if chunk["meta"]["source_id"] != dead_id and (dead_id in chunk["text"] or date in chunk["text"]):
            return chunk["meta"]["source_id"]
    return "as_of_date"


# Customer version "4.3" -> 403; None when unknown or unparseable (then no version filter).
def _customer_code(version: str | None) -> int | None:
    if not version:
        return None
    try:
        return retrieval.version_code(version)
    except ValueError:
        return None
