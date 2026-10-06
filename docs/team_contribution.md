# Team contribution statement

Hiring is individual, so each member fills in their own section: their name, their commits, and what they reviewed or changed **by hand**. The areas and files come from the agent roster in [BUILD_PLAN.md](../BUILD_PLAN.md) section 2. The AI agents that produced the first version of each file are listed in [docs/ai_usage_disclosure.md](ai_usage_disclosure.md).

Fill in the commit counts from Git:

```bash
git shortlog -sn --all                         # commits per author
git log --author="<your name>" --oneline       # your own commits
```

---

## Member 1: Data and knowledge base

| | |
| --- | --- |
| Name | |
| GitHub username | |
| Commits (`git shortlog -sn`) | |
| Agents owned | A1 public-data, A2 kb-author, A3 account-data, A16 docs |

**Files owned:** `scripts/mine_public_data.py`, `scripts/generate_kb.py`, `scripts/generate_accounts.py`, `scripts/validate_accounts.py`, `scripts/load_accounts.py`, `data/public/`, `data/generation/`, `data/kb/`, `data/source_register.csv`, `data/accounts/`, `eval/probes_oos.jsonl`, `eval/probes_tone.jsonl`, `docs/data_card.md`, `docs/knowledge_base.md`, `docs/ai_usage_disclosure.md`, `docs/team_contribution.md`, `docs/declaration.md`. Eval cases `E-M1-01` … `E-M1-08`.

- What I reviewed by hand:
- What I changed or wrote by hand:
- Parts I can explain end to end (Q&A):
- My role in the demo:

---

## Member 2: Retrieval, precedence and evaluation

| | |
| --- | --- |
| Name | |
| GitHub username | |
| Commits (`git shortlog -sn`) | |
| Agents owned | A4 retrieval-core, A5 ingest-api, A6 precedence, A13 eval-runner, sample audits/handoffs |

**Files owned:** `app/retrieval.py`, `scripts/ingest_kb.py`, `app/precedence.py`, `eval/run_eval.py`, `eval/report.md`, `eval/results/`, `docs/sample_audits/`, `docs/sample_handoffs/`, `tests/test_retrieval.py`, `tests/test_ingest.py`, `tests/test_precedence.py`. Eval cases `E-M2-01` … `E-M2-08`.

- What I reviewed by hand:
- What I changed or wrote by hand:
- Parts I can explain end to end (Q&A):
- My role in the demo:

---

## Member 3: Tools, policy and safety

| | |
| --- | --- |
| Name | |
| GitHub username | |
| Commits (`git shortlog -sn`) | |
| Agents owned | A7 tools-policy, A8 safety, A9 escalation, A14 red-team |

**Files owned:** `app/tools/` (8 tools + `run_tool`), `scripts/seed_policy_registry.py`, `app/safety.py`, `app/escalation.py`, `scripts/pii_scan.py`, `tests/conftest.py`, `tests/test_tools.py`, `tests/test_safety.py`, `tests/test_escalation.py`, `tests/test_redteam.py`. Eval cases `E-M3-01` … `E-M3-08`.

- What I reviewed by hand:
- What I changed or wrote by hand:
- Parts I can explain end to end (Q&A):
- My role in the demo:

---

## Member 4: Pipeline, API and platform (orchestrator)

| | |
| --- | --- |
| Name | |
| GitHub username | |
| Commits (`git shortlog -sn`) | |
| Agents owned | A0 orchestrator, A10 llm-client, A11 pipeline, A12 api-platform |

**Files owned:** `app/config.py`, `app/db.py`, `app/schemas.py`, `app/main.py`, `app/llm.py`, `app/prompts/`, `app/graph/`, `app/audit.py`, `ui/streamlit_app.py`, `Dockerfile`, `docker-compose.yml`, `requirements.txt`, `.env.example`, `README.md`, `tests/test_llm.py`, `tests/test_pipeline.py`. Merges at every gate. Eval cases `E-M4-01` … `E-M4-08`.

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
