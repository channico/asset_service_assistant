# Setup and local operation

This is the authoritative guide for installing, configuring, validating, and
running Asset Service Assistant locally. Commands assume macOS or Linux and are
run from the repository root.

## Requirements

- Python 3.11 or later
- An OpenAI API key for manual-index ingestion and live agent runs
- Network access for dependency installation and live OpenAI API calls

The data validator, unit tests, and index check do not make live API calls. The
manual retrieval evaluation uses the existing generated index but embeds its
questions, so it requires the API key and network access.

## Create the environment

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e .
```

The project declares its runtime dependencies in `pyproject.toml`, including
the OpenAI Python library, OpenAI Agents SDK, Pydantic, python-dotenv, and
Streamlit.

## Configure local credentials

Create the ignored environment file from the safe template:

```bash
cp .env.example .env
```

Edit `.env` locally:

```dotenv
OPENAI_API_KEY=your-key-here
ASA_AGENT_MODEL=gpt-4.1-mini
```

Never commit, paste into source code, or share the key. `.gitignore` excludes
`.env` and other `.env.*` files while retaining `.env.example`. Use an explicit
model for recorded evaluations because model behavior can change over time.

## Validate the synthetic source data

```bash
.venv/bin/python validate_data.py
```

The current fixtures contain 10 assets, 15 maintenance events, 10 service
tickets, and 4 manuals. Validation checks schemas, identifier uniqueness,
allowed statuses, dates, cross-record asset references, and manual
applicability.

## Build and check the manual index

Ingestion chunks and embeds the current manual corpus with
`text-embedding-3-small`, then writes the rebuildable and ignored
`data/manual_index.json`:

```bash
.venv/bin/python manual_index.py ingest
.venv/bin/python manual_index.py check
```

The check is offline. It verifies index format, embedding and chunking settings,
dimensions, and SHA-256 fingerprints of the manual source files. Re-run
ingestion after changing the corpus, embedding model, or chunking configuration.

## Run the command-line interfaces

List all assets or retrieve one exact asset without a model call:

```bash
.venv/bin/python main.py
.venv/bin/python main.py VEH-1001
.venv/bin/python main.py VEH-9999
```

Ask the agent a question:

```bash
.venv/bin/python assistant_agent.py \
  "Show asset VEH-1001 and its recorded maintenance history."
```

Override the configured agent model for one run with `--model`:

```bash
.venv/bin/python assistant_agent.py \
  --model gpt-4.1-mini \
  "For VEH-1001, how should I inspect the sliding door?"
```

## Run the Streamlit UI

```bash
.venv/bin/streamlit run streamlit_app.py
```

The UI calls the same `run_assistant()` backend as the agent CLI and evaluator.
Each submitted message starts an independent run; displayed history is not
model conversation memory. See [DEMO_GUIDE.md](DEMO_GUIDE.md) for the
recommended presentation flow.

## Run tests and evaluations

Run deterministic validation and all offline unit tests first:

```bash
.venv/bin/python validate_data.py
.venv/bin/python -m unittest discover -s tests -v
```

Run the manual retrieval evaluation against the frozen fixture and threshold:

```bash
.venv/bin/python evaluate_manual_search.py
```

This command makes live embedding calls for the evaluation questions. The
recorded calibration and held-out results are in
`evaluation/manual_search_results.md`.

Run all 12 live assistant cases using the model in `.env`:

```bash
.venv/bin/python evaluate_assistant.py
```

Run one case or save a machine-readable report:

```bash
.venv/bin/python evaluate_assistant.py \
  --model gpt-4.1-mini \
  --case conflicting-ticket-claim

.venv/bin/python evaluate_assistant.py \
  --model gpt-4.1-mini \
  --json-output evaluation/assistant_evaluation_run.json
```

Live agent results can vary. A passing run demonstrates capability, not a
reliability guarantee. The current recorded snapshot is in
`evaluation/assistant_evaluation_results.md`.

## Common local problems

### `python` is not found or uses the wrong interpreter

Create the environment with `python3`, then use `.venv/bin/python` for project
commands. This avoids depending on a global `python` alias.

### Import errors

Confirm that the editable installation completed in this environment:

```bash
.venv/bin/python -m pip install -e .
```

### Missing API key

Confirm that `.env` exists at the repository root and contains a valid
`OPENAI_API_KEY`. Do not print the key while troubleshooting.

### Missing or stale manual index

Run the check for an actionable error, then rebuild when requested:

```bash
.venv/bin/python manual_index.py check
.venv/bin/python manual_index.py ingest
```

### A live evaluation passes or fails inconsistently

Keep the model and fixture fixed, record the exact output, and separate a safe
answer from complete tool coverage. The agent's routing and prose are
probabilistic; the Python repositories, tool guards, schemas, and unit tests are
deterministic.
