"""Mine six public sources for realism only (area: safety, critic and eval; the KB uses its themes).

Run: .venv/Scripts/python.exe scripts/mine_public_data.py

What it writes (no public text is copied into the knowledge base):
  data/public/tone_exemplars.jsonl   15 CloudFlow-context paraphrases of angry/repeat-contact tweets
  eval/probes_tone.jsonl             the same 15 as must-escalate eval probes
  data/public/question_templates.txt question phrasing patterns counted over 5,000 MS MARCO queries
  eval/probes_oos.jsonl              20 general MS MARCO queries, expected out_of_scope
  data/public/themes.json            problem themes from GitHub Discussions + Stack Overflow titles
  data/public/manifest.csv           one row per source: licence, use, status (used / skipped:<reason>)
data/public/structure_templates.md is hand-written (Stripe/Twilio structure, our own words) and only
checked here. Raw downloads live in data/raw/ (gitignored) and are never copied elsewhere.

  --export-probes  writes only the runtime probe sets for eval/run_public.py into data/raw/probes/ (gitignored,
                   real third-party text, never committed): msmarco_500, twcs_300, twcs_pii_50, tech_titles_200.
Every source is optional: a failure (network, auth, missing file) is recorded as skipped, never fatal.
"""
import collections
import csv
import datetime
import html
import itertools
import json
import pathlib
import random
import re
import shutil
import subprocess
import sys

import requests

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))  # so "app.llm" imports when run as a plain script
RAW = ROOT / "data" / "raw"
PUBLIC = ROOT / "data" / "public"
EVAL = ROOT / "eval"
AS_OF = "2026-10-06"
ACCESSED_ON = datetime.date.today().isoformat()
CLAUDE = "paraphrased by Claude (claude-opus-5-5, Claude Code subagent)"
ACCOUNTS = [f"A{n}" for n in range(1001, 1009)]  # edge-case accounts A1001-A1008

# ---------------------------------------------------------------- shared helpers

SCRUB = [
    (re.compile(r"https?://\S+|www\.\S+"), "[URL]"),
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+"), "[EMAIL]"),
    (re.compile(r"@\w+"), "[HANDLE]"),
    (re.compile(r"\+?\d[\d\s().-]{7,}\d"), "[NUMBER]"),          # phones, card and order numbers
    (re.compile(r"\^[A-Z]{1,3}\b|(?i:my name is)\s+\w+(\s+\w+)?"), "[NAME]"),  # agent initials, self-intros
    (re.compile(r"\b((?i:by|agent|rep|manager|supervisor|named|called),?)\s+[A-Z][a-z]+(\s+[A-Z][a-z]+)?"), r"\1 [NAME]"),
]


# Remove handles, URLs, emails, phone/card numbers and simple name patterns from a raw text.
def scrub(text: str) -> str:
    for pattern, label in SCRUB:
        text = pattern.sub(label, text)
    return re.sub(r"\s+", " ", text).strip()


# Write a list of dicts as JSON Lines (one object per line).
def write_jsonl(path: pathlib.Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")


# Build one eval-set line in the eval case format (eval/README.md).
def probe(pid: str, account: str, message: str, category: str, answer_type: str, reasons: list[str]) -> dict:
    return {"id": pid, "account_id": account, "message": message, "as_of_date": AS_OF,
            "category": category, "expected_answer_type": answer_type, "expected_sources": [],
            "expected_contains": [], "expected_tool_outputs": {}, "expected_escalation_reasons": reasons}


# Fetch JSON from a URL and cache it under data/raw; if the network fails, reuse the cache.
def fetch_cached(cache: pathlib.Path, fetch) -> object:
    try:
        data = fetch()
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(data), encoding="utf-8")
        return data
    except Exception as exc:  # network, auth, rate limit: fall back to the last good copy
        if cache.exists():
            print(f"  fetch failed ({exc}); using cached {cache.name}")
            return json.loads(cache.read_text(encoding="utf-8"))
        raise


# ---------------------------------------------------------------- 1. Customer Support on Twitter

TWCS_CSV = RAW / "twcs" / "twcs" / "twcs.csv"
CUES = ["again", "third time", "charged", "refund", "cancel", "manager", "worst"]
CUE_RE = re.compile(r"\b(" + "|".join(CUES) + r")\b", re.I)
FRUSTRATION = re.compile(r"!|\b(still|never|no one|nobody|ridiculous|unacceptable|not acceptable|how many times|"
                         r"sick of|fed up|worst|manager|supervisor|terrible|awful|joke|again)\b", re.I)
# Profanity and positive words: such tweets are not useful or safe tone exemplars.
SKIP_WORDS = re.compile(r"\b(thanks|thank you|lucky|love|great|f+u+c+k\w*|shit\w*|bitch\w*|ass(hole)?|damn|wtf|crap|hell|ffs)\b", re.I)

# Paraphrases of the 15 sampled tweets into CloudFlow context, written by Claude because Ollama was not
# available on the build machine. Index i matches sample i of sample_tweets() (fixed seed, same CSV).
# Each one keeps the source tweet's tone and situation (frustration, repeat contact, asking for a person)
# but none of its words, names or brands. Every one must escalate under Annex A.3 of the guide.
PARAPHRASES = [
    {"text": "Once again your update broke my workflows and your support team blamed my setup for it. The supervisor I spoke to cut me off. I want a manager to review this properly.",
     "sentiment": "angry", "repeated_contact": True, "wants_human": True},
    {"text": "Third time now that I'm sending you my workspace details for the same problem. Fix it now, I am not explaining it a fourth time.",
     "sentiment": "angry", "repeated_contact": True, "wants_human": False},
    {"text": "My workflow never ran because the connector was down, I cancelled the upgrade, and I was still charged. This is my second message and nobody has replied. I want someone from billing on this.",
     "sentiment": "angry", "repeated_contact": True, "wants_human": True},
    {"text": "The run history export I paid for came out broken and I'm not happy. Can I get refunded without redoing everything? I've already asked twice.",
     "sentiment": "negative", "repeated_contact": True, "wants_human": False},
    {"text": "Your scheduled workflows accept the trigger and then never run, so my team keeps cancelling jobs by hand. I've reported this before. Escalate it to a person who can actually fix it.",
     "sentiment": "angry", "repeated_contact": True, "wants_human": True},
    {"text": "I was told a support manager would call me back about my paused workflows. Three days later, still nothing. I want to speak to that manager today.",
     "sentiment": "angry", "repeated_contact": True, "wants_human": True},
    {"text": "Worst support I have ever had. A simple connector problem has been open for 27 days and I've chased it again and again.",
     "sentiment": "angry", "repeated_contact": True, "wants_human": False},
    {"text": "For the third time I'm being told to just pay the invoice. I never agreed to the Business upgrade on it. No. Put me through to a person.",
     "sentiment": "angry", "repeated_contact": True, "wants_human": True},
    {"text": "My scheduled workflows ran more than two hours late again last night. I'm reporting it for the third time in four months. Not acceptable.",
     "sentiment": "angry", "repeated_contact": True, "wants_human": False},
    {"text": "Why was I charged so much more than my plan price this month? I've asked twice and still have no explanation. I want a human to go through my invoice with me.",
     "sentiment": "angry", "repeated_contact": True, "wants_human": True},
    {"text": "The 4.4 update broke my webhooks and my customers' orders went nowhere. I've written in twice already. Just refund this month and get me a manager.",
     "sentiment": "angry", "repeated_contact": True, "wants_human": True},
    {"text": "I've been a CloudFlow customer for three years and every release breaks something again. I've complained before and nothing changes. Have a manager call me or I'm cancelling.",
     "sentiment": "angry", "repeated_contact": True, "wants_human": True},
    {"text": "Terrible experience with your support chat today. The agent was dismissive and closed my ticket without fixing anything. Please have a real person contact me.",
     "sentiment": "negative", "repeated_contact": False, "wants_human": True},
    {"text": "Your support is the worst. Nothing gets answered on time and it's impossible to reach an actual person. I want to talk to someone now.",
     "sentiment": "angry", "repeated_contact": False, "wants_human": True},
    {"text": "After the last upgrade broke my workflows I don't trust CloudFlow to upgrade again. I've asked twice how to roll back and got no real answer. I want to talk to a person.",
     "sentiment": "negative", "repeated_contact": True, "wants_human": True},
]


# Download the Kaggle dataset into data/raw/twcs if the CSV is not there yet (needs kaggle CLI auth).
def ensure_twcs() -> None:
    if TWCS_CSV.exists():
        return
    kaggle = shutil.which("kaggle") or str(ROOT / ".venv" / "Scripts" / "kaggle.exe")
    subprocess.run([kaggle, "datasets", "download", "-d", "thoughtvector/customer-support-on-twitter",
                    "-p", str(RAW / "twcs"), "--unzip"], check=True, timeout=900)


# Pick 15 scrubbed inbound tweets with frustration cues: deterministic, spread across cue words.
def sample_tweets(scan_rows: int = 400_000, per_cue: int = 3, keep: int = 15) -> list[dict]:
    by_cue: dict[str, list[str]] = {c: [] for c in CUES}
    with TWCS_CSV.open(encoding="utf-8", newline="") as f:
        for row in itertools.islice(csv.DictReader(f), scan_rows):
            text = row["text"]
            match = CUE_RE.search(text)
            if (row["inbound"] != "True" or not match or SKIP_WORDS.search(text) or not 60 <= len(text) <= 280
                    or len(FRUSTRATION.findall(text)) < 2):  # cue plus at least one more frustration signal
                continue
            by_cue[match.group(1).lower()].append(scrub(html.unescape(text)))
    rng = random.Random(2026)
    pools = {cue: rng.sample(texts, min(per_cue, len(texts))) for cue, texts in by_cue.items()}
    picked = [{"cue": cue, "clean_text": pools[cue][r]}  # round-robin so every cue is represented
              for r in range(per_cue) for cue in CUES if r < len(pools[cue])]
    return picked[:keep]


# Paraphrase one scrubbed tweet into CloudFlow context: LLM when available, else the stored paraphrase.
def paraphrase(clean_text: str, stored: dict) -> tuple[dict, str]:
    prompt_file = ROOT / "app" / "prompts" / "paraphrase_tone.txt"
    if prompt_file.exists():  # optional path: needs that prompt and a running Ollama
        try:
            from pydantic import BaseModel

            from app.llm import call_json

            class Tone(BaseModel):
                text: str
                sentiment: str
                repeated_contact: bool
                wants_human: bool

            obj, usage = call_json("paraphrase_tone", {"tweet": clean_text}, Tone, lambda: Tone(**stored))
            if usage.get("calls"):
                return obj.model_dump(), f"paraphrased by {usage['model']} via app.llm.call_json"
        except Exception as exc:
            print(f"  LLM paraphrase failed ({exc}); using stored paraphrase")
    return stored, CLAUDE


# Expected escalation reasons for a tone probe, following Annex A.3 / decide().
def tone_reasons(ex: dict) -> list[str]:
    reasons = []
    if re.search(r"refund|charged|invoice", ex["text"], re.I):
        reasons.append("billing_dispute")
    if ex["wants_human"]:
        reasons.append("explicit_human_request")
    if ex["sentiment"] in ("negative", "angry") and ex["repeated_contact"]:
        reasons.append("repeated_contact")
    return reasons


# Source 1: sample, scrub, paraphrase; write tone exemplars and must-escalate probes.
def mine_twitter() -> str:
    ensure_twcs()
    sample = sample_tweets()
    write_jsonl(RAW / "twcs" / "tone_sample.jsonl", sample)  # scrubbed originals stay in gitignored raw/
    exemplars, probes = [], []
    for i, (row, stored) in enumerate(zip(sample, PARAPHRASES), start=1):
        ex, prov = paraphrase(row["clean_text"], stored)
        exemplars.append({**ex, "source": "twcs",
                          "provenance": f"{prov}; from one anonymised inbound tweet (cue '{row['cue']}'); original text not stored"})
        reasons = tone_reasons(ex)
        assert "explicit_human_request" in reasons or "repeated_contact" in reasons, ex["text"]
        probes.append(probe(f"TONE-{i:02d}", ACCOUNTS[(i - 1) % 8], ex["text"], "must_escalate", "escalated", reasons))
    write_jsonl(PUBLIC / "tone_exemplars.jsonl", exemplars)
    write_jsonl(EVAL / "probes_tone.jsonl", probes)
    return f"used ({len(exemplars)} exemplars from {len(sample)} sampled tweets)"


# ---------------------------------------------------------------- 2. MS MARCO

# (template, regex, CloudFlow-style example written by us). Counts show how people phrase questions.
TEMPLATES = [
    ("how do i {action}", r"^how do (i|you) ", "how do i export my workflow run history"),
    ("how to {action}", r"^how to ", "how to reconnect the salesforce connector"),
    ("why does/is {thing} {problem}", r"^why (does|do|is|are|won't|can't|isn't) ", "why does my schedule run an hour late"),
    ("what does {term} mean / define {term}", r"\bmean(s|ing)?\b|^define\b|^definition\b", "what does error cf-503 mean"),
    ("what is/are {term}", r"^what (is|are) ", "what is a webhook signature"),
    ("can i {action}", r"^can (i|you) ", "can i keep my data after cancelling"),
    ("how long does {process} take", r"^how long (does|do|is|will|until) ", "how long does a duplicate charge reversal take"),
    ("how much does {thing} cost", r"^how much (does|do|is|are) ", "how much does the business plan cost"),
    ("how many {unit} {limit}", r"^how many ", "how many api calls per minute on pro"),
    ("when does/is {event}", r"^when (does|do|is|are|will|did) ", "when do webhooks v1 stop working"),
    ("where is/do i find {setting}", r"^where (is|are|do|can) ", "where do i find my invoices"),
    ("what happens if/when {event}", r"^what happens (if|when) ", "what happens when i go over my run limit"),
    ("difference between {a} and {b}", r"difference between ", "difference between webhooks v1 and v2"),
    ("is it possible to {action}", r"^is it possible to ", "is it possible to retry a failed step automatically"),
    ("{noun phrase} (keyword-only query)", r"^(?!(how|what|why|when|where|who|which|is|are|can|do|does|did)\b)", "salesforce connector cf-503 fix"),
]
# Words that make a query CloudFlow-like or sensitive; such queries are never used as out-of-scope probes.
OOS_EXCLUDE = re.compile(
    r"\b(account|password|login|log in|sign in|email|error|app|apps|software|api|server|cloud|workflow|integrat\w*|"
    r"export|bill\w*|invoice|refund|charge\w*|payment|subscription|plan|token|webhook|data|computer|excel|windows|"
    r"iphone|android|google|microsoft|salesforce|slack|jira|hubspot|stripe|sap|ariba|code|program\w*|network|"
    r"router|wifi|website|online|internet|download|update|install|support|customer|limit|rate|sql|"
    r"laptop|modem|phone\w*|pc|mac|tv|"
    r"drug\w*|dose|dosage|medic\w*|blood|stool\w*|symptom\w*|pain|disease\w*|cancer|infection|virus|doctor|"
    r"hospital|surgery|tattoo|pregnan\w*|diet|calori\w*|vitamin\w*|iron|test\w*|sex\w*|death|die|kill|suicide|"
    r"gun|weapon|religio\w*|church|sisters?|prison|divorc\w*|married|wife|husband|born|dating|"
    r"quizlet|who|did|he|she|his|her|my|i|salary|stock|dividend|invest\w*|loan|tax|pension|bank|insurance|"
    r"credit|mortgage|therap\w*|transplant|clinic\w*|laborator\w*|nervous|weight|nail\w*|safe|related|file\w*|"
    r"green card|visa|immigra\w*|fast|lose|cells?|plasma|navy|army|war|fix\w*|operation|laxative|elbow)\b", re.I)
OOS_START = re.compile(r"^(what|how|why|where|when|is|are|can|does|do)\b")
# Allowlist of plainly general-knowledge topics (geography, nature, food, sport, history, language):
# a probe must hit one of these so it is unmistakably unrelated to CloudFlow support.
OOS_TOPIC = re.compile(
    r"\b(country|countries|capital|language|county|city|river|mountain|ocean|sea|island|lake|desert|climate|"
    r"animal|species|bird|fish|dog|cat|horse|whale|shark|rhino\w*|insect|planet|moon|sun|star|earth|volcano|rock|"
    r"mineral|plant|tree|flower|moss|recipe|bake|cook|food|fruit|cheese|bread|soup|coffee|tea|sport|basketball|"
    r"football|soccer|baseball|olympic\w*|tennis|golf|chess|painting|instrument|guitar|piano|ancient|roman|"
    r"greek|empire|castle|pyramid|invented|synonyms?|miles)\b")


# Stream 5,000 MS MARCO validation queries (query strings only; every 12th of the first 60,000, because
# the split is grouped by topic), cached in data/raw.
def load_msmarco(n: int = 5000) -> list[str]:
    cache = RAW / "msmarco_queries.json"
    if cache.exists():
        return json.loads(cache.read_text(encoding="utf-8"))
    import datasets  # imported here so the other sources still run if it is missing
    ds = datasets.load_dataset("microsoft/ms_marco", "v2.1", split="validation", streaming=True,
                               columns=["query"])  # skip the large passages column
    queries = [r["query"].strip().lower() for r in itertools.islice(ds, 0, n * 12, 12)]
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(queries), encoding="utf-8")
    return queries


# Source 2: count question templates and sample 20 clearly non-CloudFlow queries as OOS probes.
def mine_msmarco() -> str:
    queries = load_msmarco()
    lines = ["# Question phrasing templates counted over MS MARCO v2.1 validation queries",
             f"# Queries scanned: {len(queries)}. Licence: non-commercial research only. No query text is stored here;",
             "# the example column is our own CloudFlow wording. Used to vary phrasing in eval cases and tickets.",
             "# template\tcount\tshare\tcloudflow_example"]
    for template, pattern, example in TEMPLATES:
        count = sum(1 for q in queries if re.search(pattern, q))
        lines.append(f"{template}\t{count}\t{count / len(queries):.1%}\t{example}")
    (PUBLIC / "question_templates.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")

    candidates = sorted({" ".join(q.rstrip(" ?.").split()) for q in queries
                         if OOS_START.search(q) and OOS_TOPIC.search(q) and not OOS_EXCLUDE.search(q)
                         and 15 <= len(q) <= 70 and q.isascii() and not any(ch.isdigit() for ch in q)})
    random.Random(2026).shuffle(candidates)
    picked, per_opening = [], collections.Counter()
    for q in candidates:  # at most 2 probes per opening ("what county", ...) for variety
        opening = " ".join(q.split()[:2])
        if per_opening[opening] < 2 and len(picked) < 20:
            picked.append(q)
            per_opening[opening] += 1
    probes = [probe(f"OOS-{i:02d}", ACCOUNTS[(i - 1) % 8], q[0].upper() + q[1:] + "?", "out_of_scope", "out_of_scope", [])
              for i, q in enumerate(picked, start=1)]
    write_jsonl(EVAL / "probes_oos.jsonl", probes)
    return f"used ({len(queries)} queries, {len(candidates)} OOS candidates, {len(picked)} sampled)"


# ---------------------------------------------------------------- 3 + 4. GitHub Discussions and Stack Overflow

GH_REPOS = ["apache/airflow", "dagster-io/dagster", "PrefectHQ/prefect", "windmill-labs/windmill"]  # all verified: Discussions on
SO_TAGS = ["webhooks", "oauth-2.0", "rate-limiting", "salesforce"]  # "salesforce-api" has 0 questions on SO; closest existing tag
THEMES = {
    "auth expiry and token refresh": r"token|oauth|expir|refresh|\b401\b|unauthori[sz]ed|credential|authenticat",
    "webhook retries and signatures": r"webhook|signature|hmac|callback|retr(y|ies)",
    "timeouts and stuck runs": r"time ?out|timed out|hang(s|ing)?\b|stuck",
    "rate limits and quotas": r"rate.?limit|\b429\b|throttl|quota|too many requests",
    "scheduling and time zones": r"schedul|\bcron\b|time ?zone|daylight|\bdst\b|catchup|backfill",
    "upgrade breakage and deprecations": r"upgrad|migrat|deprecat|breaking|after updat",
    "pagination and large results": r"paginat|next page|cursor|offset|large (result|data|file)|batch",
    "connection and SSL failures": r"\bssl\b|certificate|connection (refused|reset|error|failed)|proxy",
}
GQL = """query($owner:String!,$name:String!){repository(owner:$owner,name:$name){
  discussions(first:100, answered:true, orderBy:{field:UPDATED_AT,direction:DESC}){
    nodes{title url category{name}}}}}"""


# Source 3: titles, categories and URLs of answered discussions (no usernames, no bodies) via gh.
def fetch_github() -> list[dict]:
    items = []
    for repo in GH_REPOS:
        owner, name = repo.split("/")

        # One read-only GraphQL call for this repo; keeps only title, category and URL.
        def call():
            out = subprocess.run(["gh", "api", "graphql", "-f", f"query={GQL}", "-f", f"owner={owner}",
                                  "-f", f"name={name}"], capture_output=True, text=True, encoding="utf-8", check=True, timeout=120)
            nodes = json.loads(out.stdout)["data"]["repository"]["discussions"]["nodes"]
            return [{"title": n["title"], "category": n["category"]["name"], "url": n["url"]} for n in nodes]

        items += [{**d, "repo": repo} for d in fetch_cached(RAW / "github" / f"{owner}_{name}.json", call)]
    return items


# Source 4: titles, tags and links of top-voted Stack Overflow questions per tag (owner fields dropped).
def fetch_stackoverflow() -> tuple[list[dict], set[str]]:
    items, licences = [], set()
    for tag in SO_TAGS:
        # One API call for this tag (no key needed, 300 calls/day per IP); keeps title, tags and link only.
        def call():
            r = requests.get("https://api.stackexchange.com/2.3/questions",
                             params={"site": "stackoverflow", "sort": "votes", "order": "desc",
                                     "tagged": tag, "pagesize": 50}, timeout=60)
            r.raise_for_status()
            return [{"title": html.unescape(q["title"]), "tags": q["tags"], "link": q["link"],
                     "content_license": q.get("content_license", "")} for q in r.json()["items"]]

        for q in fetch_cached(RAW / "stackoverflow" / f"{tag}.json", call):
            items.append(q)
            licences.add(q["content_license"])
    return items, licences - {""}


# Count how many titles (plus SO tags) hit each theme; keep up to 6 URLs per theme as attribution.
def build_themes(gh: list[dict], so: list[dict]) -> list[dict]:
    themes = []
    for theme, pattern in THEMES.items():
        gh_hits = [d["url"] for d in gh if re.search(pattern, d["title"], re.I)]
        so_hits = [q["link"] for q in so if re.search(pattern, q["title"] + " " + " ".join(q["tags"]), re.I)]
        themes.append({"theme": theme, "count": len(gh_hits) + len(so_hits),
                       "github_count": len(gh_hits), "stackoverflow_count": len(so_hits),
                       "example_urls": gh_hits[:3] + so_hits[:3]})
    return sorted(themes, key=lambda t: -t["count"])


# Sources 3 + 4: fetch both, merge themes into data/public/themes.json; return (gh_status, so_status, so_licences).
def mine_themes() -> tuple[str, str, set[str]]:
    gh, so, licences, gh_status, so_status = [], [], set(), "", ""
    try:
        gh = fetch_github()
        gh_status = f"used ({len(gh)} answered discussions from {len(GH_REPOS)} repos)"
    except Exception as exc:
        gh_status = f"skipped:{type(exc).__name__} {str(exc)[:80]}"
    try:
        so, licences = fetch_stackoverflow()
        so_status = f"used ({len(so)} questions over {len(SO_TAGS)} tags)"
    except Exception as exc:
        so_status = f"skipped:{type(exc).__name__} {str(exc)[:80]}"
    if gh or so:
        sources = []
        if gh:
            sources.append({"source": "GitHub Discussions (answered)", "repos": GH_REPOS, "items": len(gh),
                            "kept_fields": ["title", "category", "url"]})
        if so:
            sources.append({"source": "Stack Overflow (Stack Exchange API, sort=votes)", "tags": SO_TAGS,
                            "items": len(so), "kept_fields": ["title", "tags", "link"],
                            "note": "tag salesforce used because salesforce-api has 0 questions; "
                                    "counts are biased toward the four queried tags"})
        out = {"accessed_on": ACCESSED_ON, "method": "keyword regex over titles (and SO tags); counts are items matched",
               "themes": build_themes(gh, so), "sources": sources}
        (PUBLIC / "themes.json").write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    return gh_status, so_status, licences


# ---------------------------------------------------------------- probe export (robustness eval at scale)

PROBES = RAW / "probes"  # gitignored: these files hold real third-party text and must never be committed
# CloudFlow-support vocabulary: an MS MARCO query with one of these words could be a real CloudFlow question,
# so it is left out to keep the "never answered" label clean. Deliberately narrower than app/llm.py's domain
# list, so words such as "run", "error", "status" or "limit" stay in and the probes really test the pipeline.
CLOUDFLOW_TOPIC = re.compile(
    r"\b(cloudflow|workflows?|webhooks?|api|apis|connectors?|integrat\w*|salesforce|hubspot|slack|jira|zendesk|"
    r"stripe|invoices?|refunds?|bill|billing|billed|subscriptions?|passwords?|log ?in|sign ?in|accounts?|tokens?|"
    r"oauth|sso|saml|2fa|rate limits?|quotas?|429|cf-\d+|automation|software|app|apps|payments?|charges?|"
    r"charged|pricing|price plans?)\b", re.I)
PII_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
PII_DIGITS = re.compile(r"(?<!\d)\+?\d(?:[ ().-]{0,2}\d){9,18}(?!\d)")  # 10-19 digits: phone-, order- or card-like
BRAND = re.compile(r"@([A-Za-z]\w*)")  # TWCS anonymised customers to numeric handles; brand handles have letters


# Read cached GitHub + Stack Overflow titles (fetch only when a cache file is missing, so the sample is stable).
def cached_titles() -> tuple[list[dict], list[dict]]:
    gh_files = [RAW / "github" / f"{r.replace('/', '_')}.json" for r in GH_REPOS]
    so_files = [RAW / "stackoverflow" / f"{t}.json" for t in SO_TAGS]
    gh = ([{**d, "repo": r} for r, p in zip(GH_REPOS, gh_files) for d in json.loads(p.read_text(encoding="utf-8"))]
          if all(p.exists() for p in gh_files) else fetch_github())
    so = ([q for p in so_files for q in json.loads(p.read_text(encoding="utf-8"))]
          if all(p.exists() for p in so_files) else fetch_stackoverflow()[0])
    return gh, so


# Pick 300 inbound TWCS tweets addressed to a brand: 250 opening tweets plus 50 that carry PII-like text
# (emails, 10-19 digit numbers). All 300 are scrubbed; the 50 are also written unscrubbed to stress-test
# the pipeline's own redaction. Returns (scrubbed_300, raw_50).
def twcs_probes(general: int = 250, with_pii: int = 50) -> tuple[list[dict], list[dict]]:
    ensure_twcs()
    openers, pii_pool = [], []
    with TWCS_CSV.open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):  # full file (~2.8M rows, ~30 s): PII-like tweets are rare
            text = html.unescape(row["text"])
            brand = BRAND.search(text)
            if row["inbound"] != "True" or not brand or not 40 <= len(text) <= 280:
                continue
            kinds = (["email"] if PII_EMAIL.search(text) else []) + (["digits"] if PII_DIGITS.search(text) else [])
            if kinds:
                pii_pool.append({"brand": brand.group(1), "text": text, "pii_kinds": kinds})
            elif not row["in_response_to_tweet_id"] and len(openers) < 200_000:
                openers.append({"brand": brand.group(1), "text": text, "pii_kinds": []})
    rng = random.Random(2026)
    emails = [p for p in pii_pool if "email" in p["pii_kinds"]]  # only a handful exist in the whole dataset
    rest = [p for p in pii_pool if "email" not in p["pii_kinds"]]
    picked_pii = emails[:with_pii] + rng.sample(rest, with_pii - min(len(emails), with_pii))
    picked = rng.sample(openers, general) + picked_pii
    scrubbed = [{"id": f"TW-{i:03d}", "brand": p["brand"], "pii_kinds": p["pii_kinds"], "message": scrub(p["text"])}
                for i, p in enumerate(picked, start=1)]
    raw = [{"id": f"TWP-{i:02d}", "pair_id": s["id"], "brand": s["brand"], "pii_kinds": s["pii_kinds"],
            "message": re.sub(r"\s+", " ", p["text"]).strip()}
           for i, (s, p) in enumerate(zip(scrubbed[general:], picked_pii), start=1)]
    return scrubbed, raw


# Write the three runtime probe sets for eval/run_public.py into data/raw/probes/ (gitignored).
def export_probes() -> None:
    queries = sorted({q for q in load_msmarco() if not CLOUDFLOW_TOPIC.search(q)})
    marco = [{"id": f"MM-{i:03d}", "message": q} for i, q in enumerate(random.Random(2026).sample(queries, 500), 1)]
    write_jsonl(PROBES / "msmarco_500.jsonl", marco)
    print(f"  msmarco_500.jsonl: 500 of {len(queries)} non-CloudFlow queries")

    tweets, raw = twcs_probes()
    write_jsonl(PROBES / "twcs_300.jsonl", tweets)
    write_jsonl(PROBES / "twcs_pii_50.jsonl", raw)
    print(f"  twcs_300.jsonl: {len(tweets)} scrubbed tweets; twcs_pii_50.jsonl: {len(raw)} unscrubbed")

    gh, so = cached_titles()
    rng = random.Random(2026)
    gh_pick = rng.sample(gh, min(100, len(gh)))
    so_pick = rng.sample(so, min(200 - len(gh_pick), len(so)))
    titles = ([{"source": "github", "repo": d["repo"], "url": d["url"], "message": d["title"]} for d in gh_pick]
              + [{"source": "stackoverflow", "tags": q["tags"], "url": q["link"], "message": q["title"]} for q in so_pick])
    titles = [{"id": f"TT-{i:03d}", **t, "themes": [name for name, pattern in THEMES.items()
                                                    if re.search(pattern, t["message"], re.I)]}
              for i, t in enumerate(titles, start=1)]
    write_jsonl(PROBES / "tech_titles_200.jsonl", titles)
    print(f"  tech_titles_200.jsonl: {len(gh_pick)} GitHub + {len(so_pick)} Stack Overflow titles")


# ---------------------------------------------------------------- manifest and main

# Run one source; any exception becomes "skipped:<reason>" so the other sources still run.
def run_source(name: str, fn) -> str:
    print(f"- {name}")
    try:
        status = fn()
    except Exception as exc:
        status = f"skipped:{type(exc).__name__} {str(exc)[:80]}"
    print(f"  {status}")
    return status


# Run all six sources and write data/public/manifest.csv (one row per source).
def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")  # Windows consoles default to cp1252
    if "--export-probes" in sys.argv:  # robustness probes only; data/public and the manifest are left alone
        print(f"- exporting probe sets to {PROBES}")
        export_probes()
        return
    PUBLIC.mkdir(parents=True, exist_ok=True)
    twcs = run_source("Customer Support on Twitter", mine_twitter)
    marco = run_source("MS MARCO", mine_msmarco)
    print("- GitHub Discussions + Stack Overflow")
    gh, so, so_licences = mine_themes()
    print(f"  github: {gh}\n  stackoverflow: {so}")
    structure = "used (structure only, no text copied)" if (PUBLIC / "structure_templates.md").exists() \
        else "skipped:structure_templates.md missing"
    so_licence = "; ".join(sorted(so_licences)) or "CC BY-SA (unverified)"
    rows = [
        ["Customer Support on Twitter (Kaggle thoughtvector/customer-support-on-twitter)",
         "https://www.kaggle.com/datasets/thoughtvector/customer-support-on-twitter",
         "CC BY-NC-SA 4.0 (confirmed: Kaggle dataset card via kaggle CLI)", ACCESSED_ON,
         "tone of angry / repeat-contact messages; 15 paraphrased CloudFlow exemplars and must-escalate probes",
         "data/public/tone_exemplars.jsonl; eval/probes_tone.jsonl", twcs],
        ["MS MARCO QnA v2.1 (validation split, streamed)", "https://huggingface.co/datasets/microsoft/ms_marco",
         "Non-commercial research purposes only (confirmed: microsoft.github.io/msmarco terms)", ACCESSED_ON,
         "question phrasing templates; 20 general queries as out-of-scope probes",
         "data/public/question_templates.txt; eval/probes_oos.jsonl", marco],
        ["GitHub Discussions (GraphQL API, read-only via gh)", "https://docs.github.com/en/graphql",
         "GitHub Terms of Service (confirmed: D.8 public content, H API terms); titles + URLs only", ACCESSED_ON,
         "topic mining for problem themes; seeds COM- community posts", "data/public/themes.json", gh],
        ["Stack Overflow (Stack Exchange API /2.3/questions)", "https://api.stackexchange.com/docs/questions",
         f"{so_licence} (confirmed: per-question content_license from the API); Stack Exchange API terms",
         ACCESSED_ON, "topic mining and real error phrasing; question links as attribution",
         "data/public/themes.json", so],
        ["Stripe docs (structure only)", "https://docs.stripe.com",
         "Proprietary, all rights reserved (unverified); structure modelled on public conventions, no text copied",
         ACCESSED_ON, "section skeleton, error-code table layout, rate-limit article pattern",
         "data/public/structure_templates.md", structure],
        ["Twilio Help Center (structure only)", "https://help.twilio.com",
         "Proprietary (confirmed: Twilio ToS s4.1 Twilio owns its Documentation); no text copied",
         ACCESSED_ON, "FAQ format for account and billing articles", "data/public/structure_templates.md", structure],
    ]
    with (PUBLIC / "manifest.csv").open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["source", "url", "licence", "accessed_on", "used_for", "output_files", "status"])
        writer.writerows(rows)
    print(f"wrote {PUBLIC / 'manifest.csv'} ({len(rows)} sources)")


if __name__ == "__main__":
    main()
