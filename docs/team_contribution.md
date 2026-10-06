# Team contribution statement

Hiring is individual, so each member fills in their own section: their name, their commits, and what they reviewed or changed **by hand**. The four roles and what each owns come from the problem statement's role table (P1–P4). The AI agents that produced the first version of each file are listed in [docs/ai_usage_disclosure.md](ai_usage_disclosure.md).

How the work reached Git: the first working version was pushed as one shared base commit. Every later improvement was split by role into four packages, and each member applied, tested, committed and pushed their own package from their own machine, on their own branch (`p1-api-orchestration`, `p2-knowledge-retrieval`, `p3-data-tools`, `p4-safety-critic-eval`). The branches were merged in the order P3 → P2 → P4 → P1, which keeps `main` green after every merge.

Fill in the commit counts from Git:

```bash
git shortlog -sn --all                         # commits per author
git log --author="<your name>" --oneline       # your own commits
```

---

## P1 · API and orchestration

| | |
| --- | --- |
| Name | |
| GitHub username | |
| Commits (`git shortlog -sn`) | |
| Owns | `schemas.py`, FastAPI endpoints, LangGraph graph, audit and conversations tables, docker-compose, `/health` |

**Files owned:**
- API: `app/schemas.py`, `app/main.py` (every endpoint, including `/health`, `/auth/login` and `/me`), `app/auth.py`, `app/config.py`.
- Pipeline: `app/graph/` (state, nodes, pipeline), `app/llm.py`, `app/prompts/classifier.txt`, `app/prompts/composer.txt`.
- Audit and conversations: `app/audit.py`, plus the `audit_log`, `conversations` and `messages` tables in `app/db.py`.
- Platform scripts: `Dockerfile`, `docker-compose.yml`, `.env.example`, `scripts/smoke_test.py`, `scripts/docker_safe_start.ps1`, `scripts/wsl_ollama_forward.py`, `scripts/reset_demo_state.py`, `scripts/make_samples.py`.
- Docs and samples: `docs/sample_audits/`, `docs/sample_handoffs/`, `README.md`.
- Tests: `tests/test_pipeline.py`, `tests/test_llm.py`, `tests/test_auth.py`.

Eval cases `E-M1-01` … `E-M1-08`.

- What I reviewed by hand:
- What I changed or wrote by hand:
- Parts I can explain end to end (Q&A):
- My role in the demo:

---

## P2 · Knowledge and retrieval

| | |
| --- | --- |
| Name | |
| GitHub username | |
| Commits (`git shortlog -sn`) | |
| Owns | Trap list, KB generation, source register, chunking and ingestion, `/ingest`, `/sources`, `apply_precedence()` |

**Files owned:** `scripts/generate_kb.py`, `data/generation/` (the KB batches, facts sheet with the trap list, prompts, `kb_check.txt`), `data/kb/`, `data/source_register.csv`, `data/public/`, `app/retrieval.py` (chunking, version parsing, ingest, search, the logic behind `/ingest` and `/sources`), `scripts/ingest_kb.py`, `app/precedence.py` (`apply_precedence()`), `docs/knowledge_base.md`, `tests/test_retrieval.py`, `tests/test_ingest.py`, `tests/test_precedence.py`. Eval cases `E-M2-01` … `E-M2-08`.

- What I reviewed by hand:
- What I changed or wrote by hand:
- Parts I can explain end to end (Q&A):
- My role in the demo:

---

## P3 · Data and tools

| | |
| --- | --- |
| Name | |
| GitHub username | |
| Commits (`git shortlog -sn`) | |
| Owns | SQLite schema, account generator, validator, loader, policy registry, all 8 tools |

**Files owned:**
- SQLite schema: `app/db.py`, meaning the Annex C tables plus `sources`. The audit and conversation tables are P1's.
- Account data: `scripts/generate_accounts.py`, `scripts/validate_accounts.py`, `scripts/load_accounts.py` (also behind `POST /admin/load-accounts`), `data/accounts/`, `data/generation/accounts_batches/`.
- Registry and tools: `scripts/seed_policy_registry.py`, `app/tools/` (8 tools plus `run_tool`).
- Docs and tests: `docs/data_card.md`, `tests/conftest.py`, `tests/test_tools.py`, `tests/test_accounts.py`.

Eval cases `E-M3-01` … `E-M3-08`.

- What I reviewed by hand:
- What I changed or wrote by hand:
- Parts I can explain end to end (Q&A):
- My role in the demo:

---

## P4 · Safety, critic and eval

| | |
| --- | --- |
| Name | |
| GitHub username | |
| Commits (`git shortlog -sn`) | |
| Owns | Redactor, guard checks, critic, policy gate, eval set and runner, Streamlit UI |

**Files owned:**
- Safety: `app/safety.py` (redactor, authorisation and secret-request guards, promise scan), `scripts/pii_scan.py`.
- Critic and policy gate: `app/prompts/critic.txt`, `app/escalation.py`.
- Eval: `eval/` (eval set, probes, `run_eval.py`, `run_public.py`, reports, results, critic sample), `scripts/mine_public_data.py` (public probe export).
- UI: `ui/streamlit_app.py`, `.streamlit/`, `requirements.txt`.
- Tests: `tests/test_safety.py`, `tests/test_escalation.py`, `tests/test_redteam.py`.

Eval cases `E-M4-01` … `E-M4-08`.

- What I reviewed by hand:
- What I changed or wrote by hand:
- Parts I can explain end to end (Q&A):
- My role in the demo:

---

## Shared work

| Item | Who | Notes |
| --- | --- | --- |
| Evaluation set (8 cases each) | all | |
| Critic-agreement labels (`eval/critic_labels.csv`, two labellers) | | |
| README sections | | |
| Demo rehearsal (twice before code freeze) | all | |
| Final review and `final` tag | | |

Every member confirms that the statement above is accurate by signing [docs/declaration.md](declaration.md).
