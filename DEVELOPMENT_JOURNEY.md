# Development journey

This is the chronological learning record for Asset Service Assistant. It
explains why each increment was introduced and how later work built on it.
Current operation belongs in [SETUP.md](SETUP.md), the implemented system in
[ARCHITECTURE.md](ARCHITECTURE.md), and unimplemented ideas in
[ROADMAP.md](ROADMAP.md).

## 1. Establish a safe POC scope — ASA-2

**Purpose.** Define a useful maintenance service-desk scenario without implying
access to real systems or authority to make maintenance decisions.

**Implementation.** The project fixed three supported question types—asset
lookup, service-history lookup, and manual guidance—and documented synthetic
data, read-only operation, abstention, escalation, and qualified-technician
boundaries.

**Learning outcome.** Safety and evidence rules need to be part of the design,
not disclaimers added after an agent is built.

**Resulting capability.** Every later repository, tool, answer, UI, and
evaluation could be checked against one stable scope.

## 2. Create a replaceable synthetic asset foundation — ASA-2

**Purpose.** Begin with inspectable data and deterministic Python before adding
models or retrieval.

**Implementation.** `data/assets/assets.json` became the replaceable source;
`asset_repository.py` validates and queries it; `main.py` provides a small list
and exact-lookup interface.

**Learning outcome.** Separating source data, repository logic, and the user
interface lets later agent tools reuse validated functions without knowing
whether records came from JSON, a database, or another adapter.

**Resulting capability.** The POC can load and inspect a synthetic asset
inventory without an API call or agent.

The original learning exercise was to add a valid asset and observe the count,
then deliberately duplicate an `asset_id` to see validation fail before
restoring uniqueness. Extending the status vocabulary requires changing both
the data and `VALID_STATUSES`, which makes the validation contract visible.

## 3. Link maintenance events and service tickets — ASA-3

**Purpose.** Give asset questions useful service context while preserving
record relationships and validation.

**Implementation.** `service_repository.py` introduced maintenance-event and
ticket schemas. Each child record references one exact `asset_id`, and loading
checks required identifiers, ISO dates, allowed statuses, uniqueness, and
missing parents. `validate_data.py` validates all datasets together.

**Learning outcome.** Treating asset IDs like foreign keys prevents plausible
but orphaned service history from entering the evidence base.

**Resulting capability.** Ten assets, fifteen maintenance events, and ten
service tickets form a coherent synthetic service dataset.

## 4. Add exact asset lookup — ASA-4

**Purpose.** Give a future agent a deterministic way to establish identity
before using asset-dependent evidence.

**Implementation.** `get_asset_details(asset_id)` in `asset_tools.py` returns a
plain `found` or `not_found` dictionary. It trims whitespace and ignores case
but rejects unknown, partial, blank, and non-text identifiers; it never uses
fuzzy or semantic matching.

**Learning outcome.** Identity resolution and semantic relevance are different
problems. Exact identity should not be delegated to a language model.

**Resulting capability.** A caller can validate one stored asset and receive
serializable evidence or an explicit error.

## 5. Retrieve ordered maintenance history — ASA-5

**Purpose.** Answer historical questions only after resolving an exact asset.

**Implementation.** `get_maintenance_history(asset_id, limit)` filters events
to one asset, orders them newest first, validates an optional positive limit,
and distinguishes no history from malformed or unknown identity.

**Learning outcome.** Empty evidence is a valid result and should not be
confused with a failed lookup.

**Resulting capability.** The service desk can retrieve complete or limited
recorded history with returned and total counts.

## 6. Add ticket and related-incident evidence — ASA-6

**Purpose.** Support exact ticket questions and cautiously reuse resolved
history without presenting analogy as diagnosis.

**Implementation.** `get_ticket(ticket_id)` returns only an exact ticket.
`find_similar_incidents(asset_id, symptom)` considers resolved, closed tickets
for the same stored asset model and compares normalized symptom words with
stored tags. Returned records are labelled `related_incident`.

**Learning outcome.** Historical similarity can support investigation, but it
does not prove the cause of a current symptom or authorize a repair.

**Resulting capability.** The tool layer can retrieve an exact ticket and
inspect relevant historical evidence with an explicit non-diagnostic caveat.

## 7. Build a versioned manual corpus — ASA-11

**Purpose.** Create a grounded source for informational guidance before adding
embeddings or generated answers.

**Implementation.** Four short manuals under `data/manuals/` record stable IDs,
titles, manufacturer/model applicability, versions, current or superseded
status, and structured sections. `manual_repository.py` validates schema,
section uniqueness, non-empty text, and applicability to known assets. The Ford
Transit corpus deliberately includes current and superseded versions.

**Learning outcome.** Version status and applicability must be source metadata,
not guesses inferred from filenames, dates, or similarity scores.

**Resulting capability.** The project has a validated, inspectable corpus that
can retain history without confusing old guidance with current guidance.

## 8. Separate ingestion from query — ASA-12

**Purpose.** Avoid embedding the whole corpus during every user question and
make index state verifiable.

**Implementation.** `manual_index.py` chunks each manual section, embeds the
batch with `text-embedding-3-small`, and writes ignored
`data/manual_index.json`. Records retain passages, citations, applicability,
version metadata, dimensions, chunking settings, and SHA-256 source
fingerprints. The offline `check` command detects missing, stale, or
incompatible indexes.

**Learning outcome.** Generated retrieval data needs provenance and a
rebuildability check just as source data needs schema validation.

**Resulting capability.** A persistent nine-chunk index can be built once and
verified before use.

## 9. Filter manual retrieval by the validated asset — ASA-13

**Purpose.** Prevent a semantically similar passage for the wrong equipment
model from becoming evidence.

**Implementation.** `search_manual(asset_id, question)` resolves the stored
asset, filters index candidates to its manufacturer and model, then calculates
and deterministically sorts cosine similarities. Results retain document,
section, file, passage, similarity, version, and current/superseded labels.
Unit tests inject deterministic embeddings and make no API call.

**Learning outcome.** Metadata filtering should constrain semantic search
before ranking, especially when applicability matters more than wording.

**Resulting capability.** A Ford Transit query cannot retrieve a Toyota
forklift passage merely because the text sounds similar.

## 10. Calibrate retrieval abstention — ASA-14

**Purpose.** Stop low-relevance passages from being displayed as supporting
evidence.

**Implementation.** The project froze a `0.40` cosine threshold and default
top-three result limit after calibration, before running held-out cases. All
five held-out cases passed without changing the threshold. When nothing
qualifies, search returns `status: "abstained"`, no results, and no citation.
Fixtures and recorded scores live in
[`evaluation/manual_search_cases.json`](evaluation/manual_search_cases.json)
and
[`evaluation/manual_search_results.md`](evaluation/manual_search_results.md).

**Learning outcome.** A threshold is evidence tied to one corpus, model,
chunking strategy, and question set—not a universal semantic-search constant.

**Resulting capability.** Relevant current passages can be cited while
unsupported and wrong-model questions fail safely.

## 11. Let one agent orchestrate read-only tools — ASA-8 and ASA-15

**Purpose.** Move from individual tool demonstrations to natural-language
selection while keeping identity and dependency rules in code.

**Implementation.** `assistant_agent.py` registers five tools with one OpenAI
Agents SDK agent. `ToolExecutionContext` records validated asset IDs, calls,
results, and limitations. Asset-dependent tools refuse to run until
`get_asset_details` succeeds. ASA-15 disabled parallel tool calls after testing
showed that validation and a dependent lookup could otherwise run in the same
batch and race on shared state.

**Learning outcome.** Tool availability is not workflow enforcement. Dependent
operations need explicit state and ordering guarantees outside model prose.

**Resulting capability.** One question can use several tools sequentially, and
unknown identity stops dependent evidence retrieval instead of inviting a
guess.

## 12. Validate structured service answers — ASA-9

**Purpose.** Keep exact records, historical facts, manual recommendations,
uncertainty, and escalation distinguishable in every response.

**Implementation.** `service_answer.py` defines typed output and a Markdown
renderer. Manual recommendations require a complete current-source citation,
and citations are checked against the passages actually retrieved. Python
post-processing retains tool limitations and enforces required safety
escalation.

**Learning outcome.** A plausible citation generated by a model is not evidence
unless it matches a retrieved source; consistent sections also make missing
information visible.

**Resulting capability.** CLI answers separate asset identity, confirmed
history, manual guidance, evidence gaps, uncertainty, and qualified review.

## 13. Evaluate and demonstrate the complete POC — ASA-10, ASA-16, ASA-17

**Purpose.** Test the behavior a stakeholder sees and provide a usable demo
without creating a second backend.

**Implementation.** `evaluate_assistant.py` checks 12 versioned cases for tool
routing, validation order, structured evidence, citations, missing information,
refusals, and escalation. The recorded 12/12 result in
[`evaluation/assistant_evaluation_results.md`](evaluation/assistant_evaluation_results.md)
is one live-run snapshot. ASA-16 added `streamlit_app.py` over the same
`run_assistant()` function; ASA-17 made free-text entry the primary workflow
while retaining three demo shortcuts and inspectable tools and limitations.

**Learning outcome.** Deterministic unit tests, retrieval evaluation, and live
agent evaluation answer different questions. A safe answer can still fail an
evaluation when the model omits explicitly requested evidence, and one passing
live run demonstrates capability rather than reliability.

**Resulting capability.** The POC now has a deterministic asset CLI, an agent
CLI, a stakeholder-facing Streamlit interface, a repeatable demo flow, and
layered evaluation over one shared read-only backend.

## What the sequence demonstrated

The project evolved from validated data to deterministic tools, then retrieval,
orchestration, structured answers, evaluation, and UI. That order kept each
increment independently testable and made it possible to locate guarantees in
Python while treating model routing and prose honestly as probabilistic. The
current design and its boundaries are summarized in
[ARCHITECTURE.md](ARCHITECTURE.md).
