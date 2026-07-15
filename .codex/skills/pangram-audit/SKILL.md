---
name: pangram-audit
description: Audit saved Pangram AI-detector results, evaluate detector performance on authorized labeled JSONL datasets, prepare evidence-based false-positive reviews, and create or verify local drafting-provenance manifests. Use when interpreting Pangram scores or windows, checking model-version and API consistency, measuring FPR/FNR with uncertainty and realistic base rates, or documenting a truthful writing process. Do not use to rewrite text to lower a detector score, automate detector probing, extract detector-sensitive phrasing, evade an authorship policy, or certify text as 100% human-written.
---

# Pangram Audit

## Purpose

Treat Pangram output as a fallible classifier result, not authorship proof. Pin the model version, preserve the original result hash, measure uncertainty on labeled data, and use draft history plus truthful disclosure as supporting evidence.

Never claim that a style score proves who wrote a document. Never promise a stable result across model updates, domains, languages, document lengths, or editing histories.

## Route the Request

Choose one path:

1. **Saved-result audit** — validate and interpret a Pangram JSON response.
2. **Labeled benchmark** — measure a fixed detector policy on data the user is authorized to evaluate.
3. **Authorship review** — assemble drafts, sources, revision history, and a truthful AI-use statement for a false-positive review.
4. **Provenance record** — create or verify a local hash-chained manifest while drafting.
5. **Evasion request** — decline score-targeted rewriting or false authorship claims. Offer product explanation, a fixed saved-result audit, policy interpretation, or source verification. Offer provenance only prospectively for a new and truthful drafting process, never as retroactive evidence for disputed AI-originated work.

## Enforce the Boundary

Decline requests to:

- make text “pass,” “look human,” or reach a target Pangram score;
- repeatedly rewrite, submit, and optimize against detector feedback;
- identify words, sentences, or style features to change for evasion;
- reproduce detector-avoidance methods from research papers;
- describe AI-originated work as wholly human-authored;
- state that any script, detector result, or manifest proves sole human authorship.

Continue with safe work already in scope: interpret an existing result, audit a fixed policy, document sources and substantive human decisions, or prepare a review packet. Edit prose only when the assistance is permitted and will be truthfully disclosed; after deceptive intent is explicit, limit help to policy interpretation, source verification, or a fresh user-authored outline.

## Establish the Evidence Level

Before analysis, distinguish:

- **Official specification** — product behavior Pangram publicly documents.
- **Vendor evaluation** — performance Pangram measured itself.
- **Independent evidence** — a third party evaluated a Pangram version.
- **Inference** — a conclusion supported by public details but not confirmed by Pangram.
- **Undisclosed** — proprietary or absent from the public record.

Read [references/pangram-research.md](references/pangram-research.md) for product mechanics, version history, score semantics, limitations, and source citations. Read [references/evaluation-method.md](references/evaluation-method.md) before making accuracy, fairness, or policy claims.

## Audit a Saved Result

Run locally; do not upload the submitted text or require an API key:

```bash
python3 .codex/skills/pangram-audit/scripts/audit_result.py RESULT.json \
  --format markdown \
  --result-retrieved-at 2026-07-15T14:30:00Z \
  --input-format raw-text \
  --extraction-path "async API task" \
  --output pangram-audit.md
```

The script accepts the current direct async-task response and common wrappers containing `result` or `output`. It hashes the raw response, suppresses submitted text and per-span details, validates stage, version, fractions, counts, scores, confidence labels, window offsets, and current 3.3 score bands, and adds input-scope warnings. It reports aggregate window-label and confidence counts so a mixed result can be explained without inventing a document-level score or producing span-level optimization feedback.

Follow these rules when explaining the report:

1. Quote the returned prediction and fractions as detector output, not fact.
2. State the model/API version and retrieval date when available.
3. Separate schema inconsistencies from substantive classification uncertainty.
4. Do not turn highlighted spans into rewriting advice.
5. Mention the roughly 50-word resolution and nonzero error rate for 3.2/3.3.
6. Recommend corroboration and human review for consequential decisions.

Exit codes: `0` audit completed without structural errors, `2` invalid usage/input, `3` audit completed with structural errors.

## Evaluate a Labeled Benchmark

Require ground-truth labels produced independently of Pangram. Freeze the policy before reading results. Keep calibration data separate from the final test set.

Input one JSON object per line:

```json
{"id":"sample-1","truth":"human","prediction":"human","model_version":"3.3.2","group":{"domain":"academic","language":"en"}}
```

Evaluate categorical predictions:

```bash
python3 .codex/skills/pangram-audit/scripts/evaluate_benchmark.py labeled.jsonl \
  --positive-truth ai,assisted \
  --negative-truth human \
  --positive-prediction ai,ai-assisted,mixed \
  --negative-prediction human \
  --prevalence 0.001,0.01,0.05,0.10 \
  --group-field domain \
  --group-field language \
  --output metrics.json
```

Evaluate a score only with a threshold fixed explicitly in advance:

```bash
python3 .codex/skills/pangram-audit/scripts/evaluate_benchmark.py labeled.jsonl \
  --positive-truth ai \
  --negative-truth human \
  --threshold 0.75 \
  --prevalence 0.01 \
  --output metrics.json
```

Do not add threshold optimization, per-document rewriting feedback, or automated API calls. Require a present, nonempty, unique ID for every row and reject labels outside the declared positive/negative sets. Require at least 30 total rows and 10 examples in each truth class for aggregate reporting. Limit subgroup fields to the script's fixed audit-dimension allowlist, and suppress subgroup metrics when total or class-specific sample sizes are too small. Do not encode rewrite variants or attempts inside an allowed field. Report confusion counts, Wilson 95% intervals, subgroup sample sizes, version mixing, and PPV/NPV at plausible deployment prevalences. Prefer FPR and TPR at a fixed policy point over headline accuracy or AUROC alone.

Exit codes: `0` evaluation completed, `2` invalid usage/input, `4` no evaluable rows.

## Create Drafting Provenance

Initialize the manifest at the project boundary:

```bash
python3 .codex/skills/pangram-audit/scripts/provenance.py init --manifest provenance.json
```

Record meaningful drafts, not every autosave:

```bash
python3 .codex/skills/pangram-audit/scripts/provenance.py snapshot \
  --manifest provenance.json \
  --file draft.md \
  --note "Reworked the analysis from my lab notes"
```

Record a truthful disclosure in the author's own words:

```bash
python3 .codex/skills/pangram-audit/scripts/provenance.py declare \
  --manifest provenance.json \
  --ai-use limited \
  --statement "AI was used for spelling suggestions; the analysis and wording are mine."
```

Verify the chain and current versions of snapshotted files:

```bash
python3 .codex/skills/pangram-audit/scripts/provenance.py verify --manifest provenance.json
```

Create provenance during a genuine drafting process; never backfill it to imply a history that did not occur. The manifest stores hashes and metadata, not document content. Verification distinguishes chain integrity and current-file matches while always returning `authorship_verified: false`, `trusted_timestamp: false`, and `declaration_source: self_asserted`. Someone controlling the files can rebuild it. Publish the manifest head hash to a trusted external system if stronger timestamp evidence is needed.

Exit codes: `0` success, `2` invalid usage/input, `3` verification failed.

## Prepare a False-Positive Review

Build a neutral evidence packet containing:

1. the original file and exact submitted text;
2. the raw Pangram JSON and its SHA-256 hash;
3. Pangram model/API version, date, input format, and extraction path;
4. relevant drafts, notes, source citations, version-control history, and provenance report;
5. a truthful description of permitted assistive tools;
6. known input limitations relevant to the document;
7. a request for independent human review under the applicable policy.

Do not edit the disputed document to obtain a different score. Preserve the original and any later revisions as separate artifacts.

## Report Conclusions

Use calibrated language:

- “Pangram returned …” rather than “the text is …”
- “On this labeled sample …” rather than “Pangram is universally …”
- “The manifest supports this drafting history …” rather than “the manifest proves authorship …”

Always include: **Detector scores and local provenance are supporting signals, not proof of authorship or misconduct.**
