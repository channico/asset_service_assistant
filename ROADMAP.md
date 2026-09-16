# Roadmap

This file collects possible improvements. Nothing here should be read as an
implemented feature, commitment, or validated production design.

## Candidate usability improvements

- Improve source and tool presentation for non-technical stakeholders without
  hiding evidence gaps or run limitations.
- Consider clearer first-run diagnostics for a missing `.env`, unavailable
  model, or stale manual index.
- Explore optional export of a demonstration result while preserving synthetic
  data and credential boundaries.

## Reliability and deterministic-routing hardening

- Add a `--runs` option to the live evaluator and report per-case reliability,
  such as `4/5 passed`, instead of treating one run as stable.
- Decide which explicit user intents require deterministic tool coverage.
- Add a post-run coverage check that rejects or marks an answer incomplete when
  an explicitly requested evidence source was skipped.
- Decide whether missing required coverage should trigger one controlled retry
  or return an explicit limitation.
- Preserve the current code-enforced invariants: exact asset validation before
  dependent tools, sequential dependent calls, read-only behavior, citation
  validation, and deterministic safety escalation.

## Evaluation improvements

- Record model, model settings, fixture version, corpus/index fingerprint, and
  timestamp in every saved evaluation report.
- Expand synthetic cases around ambiguity, conflicting sources, tool outages,
  and safety-critical wording.
- Recalibrate retrieval after any embedding model, chunking, corpus, or
  representative-question change; do not treat `0.40` as a universal value.
- Separate factual/safety acceptability, complete requested evidence coverage,
  citation validity, and response quality in evaluation reports.

## Possible data-source and deployment evolution

The following require separate validation and threat, privacy, access-control,
and operational design before implementation:

- Replace local JSON with a governed read-only data adapter.
- Add authenticated, role-aware access to a deployed demonstration.
- Introduce observability for tool latency, failures, routing, and abstention.
- Define data retention, audit, and human-review requirements.
- Evaluate a controlled integration environment before considering any live
  maintenance platform or telemetry source.

## Explicit non-goals for this POC

- Writing, approving, closing, or dispatching service records.
- Controlling, configuring, resetting, or isolating equipment.
- Automated diagnosis, repair prescription, or return-to-service approval.
- Production deployment, enterprise authentication, or operational monitoring.
- Use of real customer, employee, asset, maintenance, or telemetry data.

## Decisions still requiring evidence

- Which maintenance workflow and user group would own a production use case.
- Which data sources are authoritative and how conflicts should be resolved.
- Which tool calls must be deterministic rather than model-selected.
- What reliability, latency, security, privacy, and safety thresholds would be
  required for a controlled pilot.
- What qualified-human review is needed for each answer category.

Relevant completed foundations and follow-ups are tracked in Jira under the
ASA epic, including ASA-10 (evaluation), ASA-15 (dependent tool ordering),
ASA-16/ASA-17 (stakeholder UI), and ASA-18 (documentation reorganisation).
