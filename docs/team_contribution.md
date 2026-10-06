# Team contribution statement

Hiring is individual, so each member fills in their own section: what they reviewed or changed **by hand**, what they can explain, and their part in the demo. The four roles come from the problem statement's role table (P1–P4); the same split, with each member's files, tests and commits, is in the README section [Team and individual contributions](../README.md#team-and-individual-contributions). AI assistance is described in [docs/ai_usage_disclosure.md](ai_usage_disclosure.md).

| Member | Role |
| --- | --- |
| Mrinal Sharma | P1 · API and orchestration |
| Dev Singh | P2 · Knowledge and retrieval |
| Abhinav | P3 · Data and tools |
| Bhavesh | P4 · Safety, critic and eval |

**How the work reached Git.** The first working version went in as a series of commits, one per area, from 11:15 to 13:44 on 2026-10-06. Later improvements were split by role into one package per member. The P2 package was pushed from its own account (`fc58fb8`). The P1, P3 and P4 commits were pushed from Mrinal's account (`grizzleyyybear`) while the build was being integrated on one machine. Every commit message names its area, and each one touches only that area's files, apart from the early integration commits. The commits for each role are listed below.

```bash
git shortlog -sn --all              # commits per account
git show --stat <commit>            # what a listed commit changed
```

---

## P1 · API and orchestration: Mrinal Sharma

| | |
| --- | --- |
| Name | Mrinal Sharma |
| GitHub username | grizzleyyybear |
| Commits with this role's work | `a0f5d3b`, `3b33e71`, `6e1f447` (Docker part), `d947c9f`, `d724461`, `c576c47`, `b77a5a2`, `10739b0`, `aa3fa22`, `00617a1`, `dfe7e48`, `1d0dd2f` |
| Owns | `schemas.py`, FastAPI endpoints, LangGraph graph, audit and conversations tables, docker-compose, `/health` |

**Files owned:**
- API: `app/schemas.py`, `app/main.py` (every endpoint, including `/health`, `/auth/login` and `/me`), `app/auth.py`, `app/config.py`.
- Pipeline: `app/graph/` (state, nodes, pipeline), `app/llm.py`, `app/prompts/classifier.txt`, `app/prompts/composer.txt`.
- Audit and conversations: `app/audit.py`, plus the `audit_log`, `conversations` and `messages` tables in `app/db.py`.
- Platform scripts: `Dockerfile`, `docker-compose.yml`, `.env.example`, `scripts/smoke_test.py`, `scripts/docker_safe_start.ps1`, `scripts/wsl_ollama_forward.py`, `scripts/make_samples.py`.
- Docs and samples: `docs/sample_audits/`, `docs/sample_handoffs/`, `docs/pitch/`, `docs/diagrams/`, `README.md`.
- Tests: `tests/test_pipeline.py`, `tests/test_llm.py`, `tests/test_auth.py`.

Eval cases `E-M1-01` … `E-M1-08`.

- What I reviewed by hand:
- What I changed or wrote by hand:
- Parts I can explain end to end (Q&A):
- My role in the demo:

---

## P2 · Knowledge and retrieval: Dev Singh

| | |
| --- | --- |
| Name | Dev Singh |
| GitHub username | |
| Commits with this role's work | `0742d4c` (knowledge base), `ac70af1`, `fc58fb8` |
| Owns | Trap list, KB generation, source register, chunking and ingestion, `/ingest`, `/sources`, `apply_precedence()` |

**Files owned:** `scripts/generate_kb.py`, `data/generation/` (the KB batches, the facts sheet with the trap list, prompts, `kb_check.txt`), `data/kb/`, `data/source_register.csv`, `app/retrieval.py` (chunking, version parsing, ingest including PDF, search, and the logic behind `/ingest` and `/sources`), `scripts/ingest_kb.py`, `app/precedence.py` (`apply_precedence()`), `app/prompts/disagreement.txt`, `docs/knowledge_base.md`, `tests/test_retrieval.py`, `tests/test_ingest.py`, `tests/test_precedence.py`.

Eval cases `E-M2-01` … `E-M2-08`.

- What I reviewed by hand:
- What I changed or wrote by hand:
- Parts I can explain end to end (Q&A):
- My role in the demo:

---

## P3 · Data and tools: Abhinav

| | |
| --- | --- |
| Name | Abhinav |
| GitHub username | |
| Commits with this role's work | `5ef97c7`, `ca990fe` (tools and registry part), `0742d4c` (public-data mining), `32d9d44`, `7d42edc`, `2cb5db9` |
| Owns | SQLite schema, account generator, validator, loader, policy registry, all 8 tools, public-dataset mining |

**Files owned:**
- SQLite schema: `app/db.py` (the Annex C tables plus `sources`; the audit and conversation tables are P1's), and `scripts/reset_demo_state.py`.
- Account data: `scripts/generate_accounts.py`, `scripts/validate_accounts.py`, `scripts/load_accounts.py` (also behind `POST /admin/load-accounts`), `data/accounts/`, `data/generation/accounts_batches/`.
- Registry and tools: `scripts/seed_policy_registry.py`, `app/tools/` (8 tools plus `run_tool`).
- Public datasets: `scripts/mine_public_data.py`, `data/public/` (licences, anonymised tone exemplars, question templates, themes).
- Docs and tests: `docs/data_card.md`, `docs/data_card_details.md`, `tests/conftest.py`, `tests/test_tools.py`, `tests/test_accounts.py`.

Eval cases `E-M3-01` … `E-M3-08`.

- What I reviewed by hand:
- What I changed or wrote by hand:
- Parts I can explain end to end (Q&A):
- My role in the demo:

---

## P4 · Safety, critic and eval: Bhavesh

| | |
| --- | --- |
| Name | Bhavesh |
| GitHub username | |
| Commits with this role's work | `ca990fe` (safety and escalation part), `188f0b3`, `6e1f447` (UI part), `1c0fbef`, `8829d4f`, `c817ad7` |
| Owns | Redactor, guard checks, critic, policy gate, eval set and runner, Streamlit UI |

**Files owned:**
- Safety: `app/safety.py` (redactor, authorisation and secret-request guards, promise scan), `scripts/pii_scan.py`.
- Critic and policy gate: `app/prompts/critic.txt`, `app/escalation.py`.
- Eval: `eval/` (eval set, probes, fixtures, `run_eval.py`, `run_public.py`, reports, results, critic sample).
- UI: `ui/streamlit_app.py`, `.streamlit/`.
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
| Evaluation set (8 cases each) | all | `E-M1` Mrinal, `E-M2` Dev Singh, `E-M3` Abhinav, `E-M4` Bhavesh |
| Critic-agreement labels (`eval/critic_labels.csv`, two labellers) | | |
| README sections | all | each member's area section and contribution entry |
| Demo rehearsal (twice before code freeze) | all | |
| Final review and `final` tag | | |

Every member confirms that the statement above is accurate by signing [docs/declaration.md](declaration.md).
