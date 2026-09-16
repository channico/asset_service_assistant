# Asset Service Assistant

Asset Service Assistant is a learning proof of concept for a maintenance
service-desk coordinator. It combines exact synthetic asset and service records,
versioned maintenance manuals, semantic retrieval, and one OpenAI Agents SDK
agent that selects read-only tools and returns a structured, evidence-based
answer.

The POC supports three use cases:

1. Look up a synthetic vehicle or equipment record by exact asset ID.
2. Retrieve synthetic maintenance history or a service ticket by exact ID.
3. Retrieve informational manual guidance with an inspectable current-source
   citation.

## Boundaries

- All records, manuals, and evaluation questions are synthetic.
- Every project tool is read-only. The assistant cannot operate equipment or
  create, change, approve, close, or dispatch work.
- The assistant does not diagnose faults, prescribe repairs, authorize
  continued operation, certify safety, or replace a qualified technician.
- Missing, ambiguous, conflicting, or safety-critical evidence triggers
  abstention or escalation rather than a guessed answer.
- This is a local learning POC, not a production maintenance system or safety
  authority, and it has no connection to live equipment or operational data.

## Capabilities

- Validated JSON repositories for assets, maintenance events, service tickets,
  and versioned manuals.
- Deterministic exact-ID lookup tools and same-model incident retrieval.
- Asset-model-filtered manual search with a persistent embedding index,
  calibrated abstention, version labels, and citations.
- Sequential Agents SDK orchestration with exact asset validation before
  dependent tools.
- Typed `ServiceAnswer` validation and consistent Markdown/Streamlit rendering.
- A command-line assistant, stakeholder-facing Streamlit UI, offline tests, and
  retrieval and live-agent evaluation suites.

## Quick start

Python 3.11 or later is required. From the repository root:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e .
cp .env.example .env
```

Add `OPENAI_API_KEY` and `ASA_AGENT_MODEL` to the ignored `.env` file, then
build the generated manual index and start the UI:

```bash
.venv/bin/python manual_index.py ingest
.venv/bin/streamlit run streamlit_app.py
```

See [SETUP.md](SETUP.md) for complete installation, validation, CLI, UI, test,
and evaluation instructions.

## Documentation

- [Setup and local operation](SETUP.md)
- [Stakeholder demo guide](DEMO_GUIDE.md)
- [Development journey](DEVELOPMENT_JOURNEY.md)
- [Current architecture](ARCHITECTURE.md)
- [Roadmap and non-goals](ROADMAP.md)

Recorded evaluation results are snapshots of the current small synthetic POC,
not guarantees of future model behavior or evidence of production reliability.
