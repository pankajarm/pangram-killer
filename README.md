# Pangram Audit

This repository is a research-backed Codex skill for auditing Pangram AI-detector results, evaluating detector performance on authorized labeled data, and preserving drafting provenance.

It does **not** contain Pangram's proprietary source code. The repository originally contained only this README and a Python `.gitignore`; the product analysis here is based on Pangram's public model cards, API documentation, research releases, and independent literature.

## Discovery

As of July 15, 2026, Pangram's public production lineage is 3.3.2. Public documentation describes a decoder-only transformer sequence classifier, a 512-token internal context window, QLoRA training, four AI-involvement labels, and a two-pass “Adaptive Boundaries” segmentation pipeline. The exact production backbone, weights, tokenizer, current corpus, calibration constants, confidence cutoffs, and document aggregation formula are not disclosed.

Pangram 3.3 documents these segment-score bands: `<=0.25` human, `0.25–0.50` light assistance, `0.50–0.75` moderate assistance, and `>=0.75` AI. It also says its practical resolution is about 50 words. A score is therefore a model estimate of AI involvement in a span—not proof of authorship, token-level provenance, or a calibrated probability of misconduct.

The public Open Pangram/EditLens checkpoints are research models and are not the production 3.3.2 service. Vendor evaluations report very strong results in many covered domains, while independent work confirms strong performance on some earlier-version benchmarks and also shows nonzero false positives, sensitivity to distribution and version changes, and ambiguity around lightly edited text.

The detailed known/claimed/unknown split and source list live in [pangram-research.md](.codex/skills/pangram-audit/references/pangram-research.md).

## Objective

The technically defensible objective is to make detector use auditable and authorship claims evidence-based. No text-only classifier or rewriting method can make AI-originated text “100% human-written,” permanently guarantee a detector result, or establish sole human authorship.

The skill deliberately refuses score-targeted rewriting, automated probing, detector-feature extraction, and false authorship certification. It supports:

- validating and interpreting saved Pangram API results without sending text to a service;
- measuring false-positive and false-negative behavior on labeled datasets with confidence intervals and base-rate projections;
- creating a local, hash-chained record of drafts and truthful AI-use declarations.

## Build

The versioned skill is in [.codex/skills/pangram-audit](.codex/skills/pangram-audit/SKILL.md). Its scripts use only the Python standard library and make no network requests.

```bash
python3 .codex/skills/pangram-audit/scripts/audit_result.py result.json

python3 .codex/skills/pangram-audit/scripts/evaluate_benchmark.py labeled.jsonl \
  --positive-truth ai,assisted \
  --negative-truth human \
  --positive-prediction ai,ai-assisted,mixed \
  --negative-prediction human \
  --prevalence 0.01,0.05,0.10

python3 .codex/skills/pangram-audit/scripts/provenance.py init \
  --manifest provenance.json
python3 .codex/skills/pangram-audit/scripts/provenance.py snapshot \
  --manifest provenance.json --file draft.md --note "First complete draft"
python3 .codex/skills/pangram-audit/scripts/provenance.py verify \
  --manifest provenance.json
```

## Test

```bash
python3 -m unittest discover -s tests -v
uv run --with pyyaml python \
  "${CODEX_HOME:-${HOME}/.codex}/skills/.system/skill-creator/scripts/quick_validate.py" \
  .codex/skills/pangram-audit
```

The test suite covers current and wrapped result shapes, malformed scores and offsets, benchmark metrics and Wilson intervals, realistic base-rate projections, group breakdowns, provenance-chain integrity, file mutation, and path-boundary enforcement.
