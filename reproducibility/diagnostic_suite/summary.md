# Revision Experiment Summary

Generated: 2026-06-12 18:35:03

## Ambiguity Detection
- Cases: 30
- Accuracy: 1.000
- Precision: 1.000
- Recall: 1.000

## Pre-Solve Invalid-Spec Checks
- Cases: 8
- Expected issue sets fully detected: 8/8
- Detection rate: 1.000

## Failure/Retry Recovery
- Cases: 8
- Blocking errors cleared after repair: 8/8
- Expected issue sets cleared after repair: 8/8

## Safety-Rail Ablation
- Cases: 8
- With safety rails caught: 8/8
- Without safety rails caught: 0/8

## Rule-Only Parser Ablation
- Pipeline prompts: 10
- Field accuracy: 0.989 (89/90)
- Challenge prompts: 10
- Challenge field accuracy: 0.744 (67/90)

## Expanded Prompt Generalization Suite
- Held-out prompts: 100
- Rule-only field accuracy: 0.724 (652/900)
- ambiguous_supported: 0.728 (131/180); ambiguity-flag incidence 0.70
- multi_load: 0.694 (125/180); ambiguity-flag incidence 0.15
- paraphrased_canonical: 0.794 (143/180); ambiguity-flag incidence 0.30
- passive_region: 0.644 (116/180); ambiguity-flag incidence 0.35
- spatial_language: 0.761 (137/180); ambiguity-flag incidence 0.10

## Template-Style Configuration Baseline Proxy
- Cases: 121
- Mean manual-completion fields: 4.09/9
- Canonical mean manual-completion fields: 1.60
- Challenge mean manual-completion fields: 4.60
- Expanded held-out mean manual-completion fields: 4.32
- Normalized bracket mean manual-completion fields: 1.00

## Normalized Engineering-Style Bracket Case
- Cases: 1
- Passed pre-solve checks: 1/1
- Max loads/passive regions/elements: 2/3/9600

## Empirical Items Not Covered By This Local Harness
- Controlled user study: requires recruited participants and task timing.
- Provider-diverse LLM comparison: requires additional API credentials and model access.
- GUI timing against external tools: requires a defined participant/protocol or recorded operator runs.
