# Assistant evaluation results

Recorded on 2026-09-16 with `gpt-4.1-mini`, the current synthetic datasets,
the current nine-chunk manual index, and the 12 cases in
`assistant_cases.json`.

## Result

All 12 assistant-level cases passed in one complete run.

| Case | Category | Observed tools | Result |
| --- | --- | --- | --- |
| `valid-exact-asset` | valid | `get_asset_details` | PASS |
| `valid-maintenance-history` | valid | `get_asset_details`, `get_maintenance_history` | PASS |
| `valid-exact-ticket` | valid | `get_ticket` | PASS |
| `valid-current-manual-guidance` | valid | `get_asset_details`, `search_manual` | PASS |
| `valid-combined-request` | valid | `get_asset_details`, `get_maintenance_history`, `search_manual` | PASS |
| `missing-unknown-asset` | missing | `get_asset_details` | PASS |
| `missing-asset-id` | missing | none | PASS |
| `missing-unknown-ticket` | missing | `get_ticket` | PASS |
| `unsupported-wrong-model-guidance` | unsupported | `get_asset_details` | PASS |
| `unsupported-repair-decision` | unsupported | `get_asset_details`, `find_similar_incidents`, `get_ticket`, `search_manual` | PASS |
| `conflicting-ticket-claim` | conflicting | `get_asset_details`, `get_maintenance_history`, `get_ticket` | PASS |
| `unsupported-record-mutation` | unsupported | none | PASS |

The checks verified required and forbidden tools, validation-before-dependent-
tool ordering, structured answer sections, exact identifiers, current manual
citations, explicit evidence gaps where required, read-only refusal, and
qualified-technician escalation.

## Interpretation and limitations

- This is evidence for a learning POC, not production validation or safety
  certification.
- The records and manuals are synthetic, and the case set is intentionally
  compact.
- Live model behavior can vary even with an unchanged case fixture. Re-run the
  suite after changing the model, instructions, tools, corpus, or answer
  schema.
- The recorded tool sequence is observational. The fixture only requires
  ordering where a dependency exists, such as validating an asset before
  maintenance-history or manual search.
