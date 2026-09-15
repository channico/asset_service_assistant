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

### Try it yourself

- Add one new asset to the JSON file and confirm that the list shows five.
- Give two records the same `asset_id` and observe the validation error.
- Restore unique IDs, then add a new valid status in both the data and
  `VALID_STATUSES`.
