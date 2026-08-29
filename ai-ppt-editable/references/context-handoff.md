# Context handoff

Read at batch close and session resume. Input is all current structured artifacts; output is a self-contained `handoff.json` and consistency report.

Persist project truth outside chat: `environment-report.json`, `deck-brief.md`, `source-inventory.json`, `outline.xlsx` or `outline.csv`, `design-system.yaml`, `material-inventory.json`, `route-decision.json`, `visual-intermediate-manifest.json` when the visual-creation route is used, `slide-manifest.json`, `manifest-validation.json`, `report-index.json`, `project-report.json`, `validation-report.json`, `issue-log.json`, `delivery-report.md`, and `handoff.json`. The slide manifest must retain per-object L0-L5 editability records and derived page summaries so a resumed session does not infer editability from chat memory. The aggregate report must be regenerated whenever an indexed report, deck, route decision or manifest changes.

`handoff.json` must include `project_id`, `revision`, `current_stage`, `gate_status`, approved artifact paths and hashes, `completed_slides`, `active_batch`, `remaining_slides`, `open_blockers`, `repair_round`, `latest_checks`, `backend`, `backend_version`, `environment_report_path`, `capability_status`, `next_action`, and `updated_at`.

On resume, verify files and hashes before loading content. Stop if the approved outline or design system is missing or changed without a revision update. Load only the current batch plus global confirmed artifacts. Never use chat memory as authority.

Positive: session 2 verifies outline/design hashes, reports `visual-approved`, and starts only slides 7–10. Negative: it regenerates slides 1–6 from chat memory. Common failures are stale paths, mismatched revisions and missing issue logs; validate hashes, page partition, state transition and next action.
