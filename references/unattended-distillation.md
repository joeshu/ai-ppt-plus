# Unattended distillation — retired

The unattended distillation subsystem has been removed to keep ai-ppt-plus smaller and easier to maintain.

Do not run automated case promotion, Golden promotion, distillation case matrices, or self-modifying maintenance loops. Use the normal deterministic workflow instead: source-bound reconstruction, Visual Lock, Repair Trace, render/object/text/icon/chart QA, Runtime Mirror, and explicit CI/review gates.

`scripts/unattended_distillation_agent.py` and `assets/unattended-distillation-policy.json` are compatibility tombstones only and must not be treated as an executable feature.
