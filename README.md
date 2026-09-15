# Asset Service Assistant

A small learning project that combines structured asset records, maintenance
history, service tickets, manual retrieval, and agent tool selection.

## POC scope

### Primary user

The primary user is a **maintenance service-desk coordinator** who needs to
find reliable information while triaging an asset-related question. The
assistant supports the coordinator; it does not replace a qualified technician
or make maintenance decisions on the coordinator's behalf.

### Supported question types

The POC supports exactly three question types:

1. **Asset lookup:** retrieve a synthetic vehicle or equipment record by its
   exact asset ID, including its location and current recorded status.
2. **Service-history lookup:** retrieve synthetic maintenance history and
   service tickets associated with an exact asset or ticket ID.
3. **Manual guidance:** answer informational maintenance questions using the
   supplied short manuals, with citations to the supporting text.

Answers must be based on retrieved project data. The assistant must distinguish
facts in that evidence from any general explanation it provides.

### Boundaries and non-goals

- All asset, maintenance, and ticket records are synthetic. Real operational,
  customer, employee, telemetry, or production data is outside the POC.
- Every tool is read-only. The assistant cannot create, update, close, approve,
  or dispatch service work.
- The assistant cannot connect to or control a live vehicle, machine, sensor,
  diagnostic system, or maintenance platform.
- It cannot start, stop, isolate, reset, configure, or otherwise operate
  equipment.
- It does not diagnose faults, authorize continued operation, prescribe an
  automatic repair, certify safety, or replace inspection by a qualified
  technician.

## Safety and escalation rules

The assistant must abstain or escalate whenever any rule below applies. These
rules are deterministic: if the condition is present, the assistant must not
provide a speculative answer or operational instruction.

1. **Missing or unknown identifier:** If a required asset or ticket ID is
   absent or has no exact match, ask for a valid ID; do not guess a likely
   record.
2. **Ambiguous identity:** If records conflict or more than one record could
   identify the asset, stop and ask the coordinator to resolve the identity.
3. **Missing or conflicting evidence:** If the project data does not support an
   answer, or sources disagree, say what is missing and escalate to the record
   owner or a qualified technician.
4. **Safety-critical symptom:** If the question mentions fire, smoke, fuel or
   chemical leakage, exposed electrical parts, brake or steering failure,
   uncontrolled movement, or serious-injury risk, advise the user to stop using
   the asset when safe to do so and contact the appropriate emergency process
   and a qualified technician.
5. **Live control or data mutation:** Refuse requests to operate equipment or to
   create, alter, approve, close, or dispatch records or work orders.
6. **Repair or return-to-service decision:** Do not provide a definitive fault
   diagnosis, authorize a repair, confirm that a repair succeeded, or declare
   an asset safe to use. Escalate to a qualified technician.
7. **Safety-control bypass:** Refuse instructions to disable guards, alarms,
   interlocks, lockout/tagout measures, or manufacturer safety procedures.

When escalating, the response should identify the triggering rule, summarize
the available evidence, state what remains unknown, and name the appropriate
next step. It must not invent measurements, records, citations, or conclusions.

## Planned learning stages

1. Create and query synthetic asset data.
2. Add deterministic lookup tools.
3. Reuse the existing RAG concepts for manual search.
4. Let one agent select the appropriate tools.
5. Add evaluation cases for correct routing, missing IDs, and safe abstention.

## Run

```bash
python main.py
python main.py VEH-1001
python main.py VEH-9999
```

## Lesson 1: synthetic asset data

This first increment deliberately has only three layers:

1. `data/assets/assets.json` is the replaceable data source.
2. `asset_repository.py` validates, loads, and queries that source.
3. `main.py` is a small user interface over the repository functions.

The separation matters: later, an agent tool can call `find_asset()` without
knowing whether the records came from JSON, a database, or an external system.
The data is synthetic, so experiments cannot expose or modify real asset data.

Run the tests with Python's built-in test runner:

```bash
python -m unittest discover -s tests -v
```

Validate all four datasets directly:

```bash
python validate_data.py
```

### Try it yourself

- Add one new asset to the JSON file and confirm that the list shows eleven.
- Give two records the same `asset_id` and observe the validation error.
- Restore unique IDs, then add a new valid status in both the data and
  `VALID_STATUSES`.

## Lesson 2: linked service data

ASA-3 adds two child record types to the asset data model:

- A maintenance event records its `maintenance_id`, parent `asset_id`, service
  date, maintenance type, reported symptom, action, repair outcome, and status.
- A service ticket records its `ticket_id`, parent `asset_id`, opened and closed
  dates, status, priority, symptom, and optional repair outcome.

The `asset_id` values act like foreign keys: they connect each event or ticket
to exactly one asset. `service_repository.py` validates required identifiers,
ISO-formatted dates, allowed status values, unique record IDs, and references
to missing assets. The validation command currently checks 10 assets, 15
maintenance events, and 10 service tickets.

## Lesson 3: exact asset-details lookup

ASA-4 adds `get_asset_details(asset_id)` in `asset_tools.py`. This is the
deterministic interface that a later agent can call for an asset lookup:

- A valid ID returns a `found` result containing the exact stored asset fields.
- An unknown, partial, blank, or non-text ID returns a structured `not_found`
  result instead of guessing a likely asset.
- Matching ignores letter case and surrounding whitespace, but does not use
  fuzzy or semantic similarity.

The response is a plain dictionary so it can be serialized as JSON. Successful
responses keep tool metadata outside the `asset` object; the object itself has
only fields loaded from the synthetic asset record.

## Lesson 4: maintenance-history lookup

ASA-5 adds `get_maintenance_history(asset_id, limit)` in `asset_tools.py` for
retrieving all recorded maintenance events for one exact asset ID:

- Results contain only events linked to that asset and are ordered newest first.
- An optional positive-integer limit returns the newest matching events while
  preserving both the returned and total event counts.
- A known asset with no history returns an empty event list with an explanation.
- Malformed IDs, unknown assets, and invalid limits return structured errors.

Like the asset-details lookup, this tool is deterministic, read-only, and
returns plain dictionaries suitable for later use by an agent.

## Lesson 5: ticket lookup and related incidents

ASA-6 adds two deterministic service-ticket tools in `asset_tools.py`:

- `get_ticket(ticket_id)` retrieves one exact ticket and labels the result as
  an `exact_ticket`; unknown, malformed, and near-match IDs are not guessed.
- `find_similar_incidents(asset_id, symptom)` considers only resolved tickets
  with a close date for the same stored asset model. It compares normalized
  words in the supplied symptom with the tickets' stored `symptom_tags`.

Each related incident is labeled `related_incident` and includes the asset
model, matching symptom tags, and close date as evidence. The response also
states that historical incidents do not prove the cause of a current symptom;
the tool is a retrieval aid, not a diagnostic system.

## Lesson 6: versioned maintenance-manual corpus

ASA-11 adds four short synthetic manuals under `data/manuals/` and validates
them through `manual_repository.py`. Each manual records a stable ID, title,
manufacturer, applicable asset model, version, version status, and structured
sections. Section IDs are unique within their manual, and every section has a
title and non-empty passage text.

The corpus deliberately contains both current and superseded versions of the
Ford Transit guide. Version status is explicit metadata rather than something
later retrieval code must infer from a filename or publication order.

`validate_manual_applicability()` also checks that every manual's manufacturer
and model pair exists in the synthetic asset data. Not every asset needs a
manual in this small POC, but an orphaned manual cannot silently enter the
search corpus.

This increment performs no embedding or generative-model calls. It establishes
the validated source records that the next increment will chunk and embed.
