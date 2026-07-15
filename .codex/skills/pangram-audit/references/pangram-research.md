# Pangram Research Reference

Research cutoff: 2026-07-15. Recheck live sources before asserting that a product version, endpoint, price, language list, or policy is current.

Use these evidence tags:

- `official-specification`: Pangram publicly documents product behavior.
- `vendor-evaluation`: Pangram reports its own measurement.
- `independent-evidence`: a third party evaluated a Pangram version.
- `inference`: a conclusion drawn from public evidence but not confirmed by Pangram.
- `undisclosed`: the public record does not provide the detail.

## Executive Summary

- `official-specification` The latest publicly identified production version is Pangram 3.3.2, released as a May 18, 2026 bugfix to 3.3. The May 15 release 3.3.1 changed long-document segmentation without changing the underlying model.
- `official-specification` The 3.x system is a decoder-only transformer sequence classifier with a classification head, not a perplexity-only heuristic and not an LLM prompted to judge text.
- `official-specification` Pangram 3.2 reduced the internal context from 1,024 to 512 tokens. Long documents are split through a two-pass Adaptive Boundaries pipeline.
- `official-specification` Current output describes four degrees of AI involvement and has practical resolution of approximately 50 words. It does not recover token-level provenance.
- `inference` The score is best read as a model estimate of AI-involvement patterns in the submitted surface text. It is not documented as a calibrated probability that a person used AI or committed misconduct.
- `undisclosed` The exact production backbone, parameter count, weights, tokenizer, current training corpus, calibration constants, confidence thresholds, and document aggregation formula remain proprietary.
- `official-specification` Open Pangram/EditLens checkpoints are research releases and are not the production detector.
- `independent-evidence` Independent evaluations support strong performance on some earlier-version, covered distributions but also show nonzero errors, editing-label ambiguity, and sensitivity to model, domain, time, and detector-version changes.

## Product and Version Lineage

| Date | Public event | Evidence |
|---|---|---|
| 2024-02 / 2024-07 | Foundational binary-classifier technical report and update | `official-specification` |
| 2025-10-09 | Pangram 2.0 introduces Adaptive Boundaries | `official-specification` |
| 2025-12-11 | Pangram 3.0 introduces four-level AI-assistance detection | `official-specification` |
| 2026-01-16 | Pangram 3.1 publishes a detailed production model card | `official-specification` |
| 2026-02-27 | Pangram 3.2 lowers minimum input to 50 words and context to 512 tokens | `official-specification` |
| 2026-03-24 | Open Pangram research checkpoints released | `official-specification` |
| 2026-05-13 | Pangram 3.3 released | `official-specification` |
| 2026-05-15 | 3.3.1 changes segmentation for documents over 450 words | `official-specification` |
| 2026-05-18 | 3.3.2 bugfix changes fewer than 3% of predictions, per Pangram | `official-specification` |
| 2026-06-18 | Pangram Space identifies production 3.3.2 embeddings | `official-specification` |

Primary sources:

- [Pangram 3.3 model card](https://www.pangram.com/research/model-card/pangram-3-3)
- [Pangram 3.2 model card](https://www.pangram.com/research/model-card/pangram-3-2)
- [Pangram 3.1 model card](https://www.pangram.com/research/model-card/pangram-3-1)
- [Pangram Space](https://www.pangram.com/blog/pangram-space-an-interactive-research-project)

## Product Surface at the Research Cutoff

`official-specification` Pangram offers a web detector, browser and Google Docs extensions, LMS integrations, bulk/file workflows, and a developer API. Public product pages advertise PDF, DOCX, and RTF uploads and multi-file scanning; model cards prefer raw text or DOCX because PDF extraction can introduce artifacts.

`official-specification` Public pricing on the research cutoff listed four free scans per day, a 600-credit individual tier at $20/month, a 3,000-credit professional tier at $65/month, and developer usage at $0.05 per started 1,000-word unit with a $25 starter package. Pricing and credit rules are volatile; verify the live page before budgeting.

`official-specification` The 3.2/3.3 model-card lineage lists 22 supported languages: English, Spanish, French, Portuguese, Arabic, Chinese, Japanese, Korean, Norwegian, Russian, Turkish, Hungarian, German, Dutch, Swedish, Romanian, Ukrainian, Polish, Italian, Czech, Greek, and Hindi. A current multilingual product page lists a different 24-language set, adding Persian, Urdu, and Vietnamese while omitting Norwegian. Treat the exact support set as internally inconsistent until Pangram clarifies it, and require language-specific validation rather than assuming equal performance.

Sources:

- [Pangram product homepage](https://www.pangram.com/)
- [Pricing](https://www.pangram.com/pricing)
- [Multilingual detection](https://www.pangram.com/solutions/multilingual)

## Production Architecture

The most defensible public reconstruction is:

1. `official-specification` Normalize whitespace, case, and characters into a standardized form.
2. `official-specification` Tokenize with what Pangram calls a standard multilingual tokenizer.
3. `official-specification` Run a modern decoder-only transformer.
4. `official-specification` Feed its representation into a classification head producing an undisclosed number `K` of AI-pervasiveness logits.
5. `official-specification` Decode those logits into Human-Written, Lightly AI-Assisted, Moderately AI-Assisted, or AI-Generated.
6. `official-specification` For long documents, create overlapping first-pass windows; identify uncertain or label-transition regions; create sentence-aware finer windows; aggregate scores to sentences; cluster adjacent similar sentences; and apply hysteresis, non-maximal suppression, and outlier removal.
7. `official-specification` Adjust/calibrate logits toward avoiding false positives.
8. `undisclosed` Aggregate returned spans into document fractions and a document headline using an unpublished formula.

Pangram reports QLoRA training targeting all layers, PyTorch/Hugging Face, and three days on eight NVIDIA H100 GPUs for the 3.1/3.2 architecture. Do not infer the exact backbone or parameter count from the 24B EditLens paper model or the 12B shared-task system; neither is documented as the production checkpoint.

## Training Strategy

The 2024 company technical report describes two key methods:

### Synthetic mirrors

`official-specification` Generate an AI counterpart for a human document while matching topic, length, domain, tone, style, and semantics. This is meant to reduce shortcut learning based on subject, format, or length.

### Hard-negative mining

`official-specification` Train an initial detector, score a much larger pool of presumed human documents, select human false positives, create matched AI mirrors, add both sides to training, and repeat until held-out improvement stops.

The early report describes approximately 28 million pre-2022 human documents, a four-million-document holdout, an initial 360,000 human examples plus mirrors, and rounds adding up to 80,000 hard human examples plus mirrors. These are historical report figures, not a disclosed inventory for 3.3.2.

Sources:

- [Technical Report on the Pangram AI-Generated Text Classifier](https://arxiv.org/abs/2402.14873)
- [How Pangram detects AI content](https://www.pangram.com/research/how-it-works)

## Disclosed Research Systems Are Not Production

Pangram's 2025 GenAI Detection shared-task paper is its clearest reproducible classifier description, but the authors explicitly distinguish that system from the commercial service:

- `official-specification` Mistral NeMo 12B with the Tekken tokenizer;
- `official-specification` frozen backbone plus LoRA adaptation;
- `official-specification` final-token hidden state feeding a binary human/AI head and an auxiliary generator-identification head;
- `official-specification` input cropped to 512 tokens;
- `official-specification` one epoch on eight A100 GPUs with AdamW and linear learning-rate decay;
- `official-specification` checkpoint selection weighting false positives three times more heavily;
- `official-specification` active learning that added 50,000 high-error RAID AI examples and 50,000 paired human documents.

The shared-task system used a higher-FPR operating tradeoff, a lower minimum word count, and benchmark-specific labeled data. Do not use its 12B backbone, training recipe, or shared-task score as facts about production 3.3.2.

Pangram's DAMAGE paper used a similar disclosed research architecture to study defensive transformation invariance. It reported strong recall at a fixed 5% FPR on its snapshot of transformed academic/student prose, but it was company-authored, excluded base-model output, and used an operating point inappropriate for high-stakes individual accusations. Its defensive training results support distribution-specific stress testing, not a universal production guarantee.

Sources:

- [Pangram at GenAI Detection Task 3](https://aclanthology.org/2025.genaidetect-1.40/)
- [DAMAGE: Detecting Adversarially Modified AI Generated Text](https://aclanthology.org/2025.genaidetect-1.9/)

## EditLens and Assistance Scores

`official-specification` Pangram says its 3.x assistance system uses technology from EditLens. EditLens training starts with a human original and an AI-edited version, then derives an edit-magnitude target from embedding cosine distance or a semantic soft-n-gram measure. At inference the classifier sees only the final text; it does not receive the original draft.

Important consequences:

- `official-specification` EditLens estimates a one-dimensional edit magnitude, not the editing process or provenance.
- `official-specification` Its continuous output is an expected value over ordinal classification buckets, not a documented authorship probability.
- `official-specification` Different histories can lead to the same surface text and therefore the same inference input.
- `independent-evidence` Human validation in the paper used three expert annotators and showed only moderate agreement, illustrating that assistance categories contain judgment calls.
- `official-specification` The selected paper model was a QLoRA-tuned 24B Mistral model, but production equivalence is not claimed.
- `official-specification` The released research checkpoints are a 3B Llama adapter and 355M RoBERTa-large model under a noncommercial share-alike license; Pangram says not to use them for enforcement.

Sources:

- [EditLens paper](https://arxiv.org/abs/2510.03154)
- [Peer-reviewed ICLR 2026 version](https://openreview.net/forum?id=gOkitaPCfZ)
- [EditLens source](https://github.com/pangramlabs/EditLens)
- [Open Pangram announcement](https://www.pangram.com/blog/introducing-open-pangram)

## Current Score Semantics

Pangram 3.3 documents the following segment bands:

| `ai_assistance_score` | Documented interpretation |
|---:|---|
| `<= 0.25` | Human |
| between `0.25` and `0.50` | Lightly AI-assisted |
| between `0.50` and `0.75` | Moderately AI-assisted |
| `>= 0.75` | AI |

Boundary inclusivity at exactly `0.50` is not specified. Exact label validation should therefore skip that value. The current API documentation still uses a 3.0 example whose label/score pair does not follow the later 3.3 bands; do not apply current bands retroactively to older versions.

Pangram describes categories this way:

- Human may include extremely minor assistance.
- Light assistance covers surface edits such as grammar, spelling, phrasing, translation, or readability.
- Moderate assistance covers added detail, restructuring, tone/style shifts, or substantial rewriting.
- AI-generated includes initially human text rewritten so extensively that the model treats AI as the primary author.

`inference` These are policy-facing interpretations of a statistical model. They should not be mapped automatically to an institution's permitted-use rules.

## Inputs, Resolution, and API

`official-specification` Pangram 3.2/3.3 accepts at least 50 words and is intended for long-form prose in complete sentences. The 3.1 card documented a 75,000-character maximum; live current docs should be checked before relying on that inherited limit.

`official-specification` Approximate resolution is 50 words. Shorter interleaved human and AI portions may be returned as assistance, and Pangram says it cannot distinguish them at word or sentence level.

`official-specification` Riskier inputs include bullet lists, instructions/manuals, tables of contents, reference sections, templated or automated writing, and dense equations. Raw text or DOCX is preferred to PDF because parsing can add artifacts.

`official-specification` The live API documentation on the research cutoff uses asynchronous tasks:

1. `POST https://text.external-api.pangram.com/task`
2. Receive `task_id`.
3. Poll `GET /task/{task_id}`.
4. Stop at `STAGE_SUCCESS` or `STAGE_FAILED`.

Successful responses document version, headline, long/short predictions, AI/assisted/human fractions, segment counts, and windows with text, label, score, confidence, character indices, word count, and token length.

Search results may still show the deprecated synchronous `/v3` endpoint. Pin the documentation date and response schema when auditing historical results.

Sources:

- [Current AI Detection API](https://docs.pangram.com/api-reference/ai-detection)
- [API documentation index](https://docs.pangram.com/llms.txt)
- [Deprecated endpoints](https://docs.pangram.com/api-reference/deprecated-endpoints)

## Vendor Evaluation Claims

The 3.3 model card reports these selected human false-positive rates:

| Dataset | FPR | N |
|---|---:|---:|
| English academic writing | 0.02% | 62,971 |
| Google-translated academic writing | 0.17% | 600 |
| Multilingual news | 0.03% | 100,199 |
| Long-form English creative writing | 0.01% | 10,495 |
| Poetry | 0.49% | 12,769 |
| Biomedical papers | 0.01% | 65,053 |
| Multilingual how-to articles | 0.04% | 166,194 |

It also reports AI false-negative rates of 0.00% on 48,443 academic samples, 0.23% on 41,940 creative samples, and 1.50% on 2,536 Chatbot Arena samples.

Tag all of these as `vendor-evaluation`. “Third-party benchmark” on the card means Pangram ran its model on an external dataset, not that an independent party audited current production 3.3.2. The model card itself warns that released benchmarks can be trained on and should not be treated as a current measure after release.

The homepage's “99.98%+ accuracy” and approximate one-in-10,000 aggregate false-positive claim do not disclose a universal deployment mixture or denominator. Do not project them onto an untested domain.

## Independent Evidence

### Russell, Karpinska, and Iyyer — ACL 2025

`independent-evidence` On 300 English professional nonfiction articles across five experiments, the then-current base Pangram had 98.0% true-positive rate and 2.0% false-positive rate overall; a separate humanizer-focused Pangram model had 99.3% TPR and 2.7% FPR. This is direct and favorable but narrow: only 150 human articles and 150 matched AI articles, all in one broad writing class.

Source: [People who frequently use ChatGPT for writing tasks are accurate and robust detectors of AI-generated text](https://aclanthology.org/2025.acl-long.267/)

### APT-Eval — Findings of ACL 2025

`independent-evidence` APT-Eval tested 15,000 AI-polished samples from 300 human texts across six domains and multiple editing levels. The older binary Pangram version performed strongly on the pure-human/pure-AI calibration setup, but lightly polished text exposed the ambiguity of collapsing degrees of assistance into a binary label. Treat this as evidence for tiered reporting and policy alignment, not as a conventional false-positive rate for today's four-level model.

Source: [Almost AI, Almost Human: The Challenge of Detecting AI-Polished Writing](https://aclanthology.org/2025.findings-acl.1303/)

### NBER Working Paper 34223 — 2025

`independent-evidence` On 1,992 human passages in six genres and matched output from four frontier LLMs, Pangram's May 2025 API was the strongest tested detector and had near-zero error at several policy points. The paper is not peer-reviewed; thresholds were selected within the same corpus, novels comprised a large share of the human sample, and the result is an older API snapshot rather than a current 3.3.2 audit.

Source: [Artificial Writing and Automated Detection](https://www.nber.org/papers/w34223)

### RAID 2025 Shared Task

`independent-evidence` A Pangram shared-task system placed near the top at a fixed 5% false-positive operating point. The Pangram system paper says it added hard RAID examples and used a model/policy that differed from the commercial service, including a more permissive false-positive tradeoff and lower minimum length. Do not convert shared-task TPR at 5% FPR into production accuracy.

Sources:

- [RAID 2025 shared-task overview](https://aclanthology.org/2025.genaidetect-1.45/)
- [Pangram shared-task system paper](https://aclanthology.org/2025.genaidetect-1.40/)

### Academic-integrity study — 2026

`independent-evidence` A preregistered study of 160 long English academic papers observed zero false positives among 40 fully human papers and high inclusive recall on fully AI and hybrid categories. The sample is too small for a universal zero-FPR claim, and the authors recommend treating scores as initial flags.

Source: [Who wrote this? Evaluating the accuracy of AI text detectors on human, AI-generated, and hybrid academic writing](https://link.springer.com/article/10.1007/s40979-026-00226-w)

## Distribution Shift and Fundamental Limits

- `independent-evidence` The original RAID benchmark, which did not evaluate Pangram, shows that detector behavior can shift across generator, domain, decoding strategy, and perturbation. Use it for evaluation design, not a Pangram-specific score.
- `independent-evidence` A May 2026 preprint found Pangram and GPTZero often scored base-model continuations as more human than instruction-tuned continuations from the same families. This suggests current detectors may learn post-training and local-context artifacts rather than an invariant property of machine authorship. Do not transfer the paper's evasion implementation into a skill.
- `independent-evidence` A June 2026 preprint measured substantial performance loss under deliberately shifted inputs and shortly after a new LLM release, followed by a large improvement after Pangram 3.3. This is evidence that results are version- and distribution-dependent. Do not reproduce its detector-optimization procedure.
- `inference` If human and machine text distributions overlap, no text-only classifier can perfectly recover hidden provenance from every surface text. Longer or repeated samples may improve statistical separation but do not turn a score into proof for one document.

Sources:

- [RAID: A Shared Benchmark for Robust Evaluation of Machine-Generated Text Detectors](https://aclanthology.org/2024.acl-long.674/)
- [Base Models Look Human To AI Detectors](https://arxiv.org/abs/2605.19516)
- [Hitting a Moving Target: Test-Time Adaptation for AI Text Detection under Continual Distribution Shift](https://arxiv.org/abs/2606.25152)
- [Can AI-Generated Text be Reliably Detected?](https://arxiv.org/abs/2303.11156)

## Known, Claimed, and Unknown Checklist

### Publicly specified

- decoder-only transformer sequence classifier;
- 512-token internal context for 3.2/3.3;
- QLoRA/all-layer production training description;
- four classes and normalized 3.3 score bands;
- two-pass Adaptive Boundaries segmentation;
- approximately 50-word resolution;
- async task API and public response fields;
- open research models and data distinct from production.

### Claimed by Pangram

- 99.98%+ aggregate accuracy;
- approximately one-in-10,000 aggregate FPR;
- current per-domain FPR/FNR tables;
- improved recall on new LLMs, long documents, and humanized text;
- current training-data licensing and non-use of customer submissions;
- SOC 2 Type II and compliance assertions.

### Undisclosed or unverified

- exact production backbone, size, weights, and tokenizer;
- exact current training-set size, sources, generators, and prompt distribution;
- number `K`, loss, QLoRA hyperparameters, seeds, and calibration constants;
- numeric confidence thresholds;
- exact window sizes, strides, transition rules, and aggregation weights;
- whether fractions are word-, token-, character-, or span-weighted;
- full headline decision logic;
- current per-language performance;
- reproducibility and contamination status of vendor test sets;
- stability across silent patches or future versions.

## Privacy Notes

`official-specification` Pangram's public privacy materials say submitted content is not used to train its models, registered submissions are retained for account history, history can be deleted, and account content is deleted within 30 days after closure unless another agreement controls. Enterprise zero-retention is described as an option, not the public default. Verify the current agreement before sending confidential, regulated, student, client, or unpublished material.

Sources:

- [Privacy policy](https://www.pangram.com/privacy-policy)
- [Data Privacy FAQ](https://www.pangram.com/data-privacy)

## Required Interpretive Language

Use these formulations:

- “Pangram returned a score of … under version …”
- “The score is an AI-assistance estimate, not proof of authorship.”
- “The observed FPR on this labeled sample is … with a 95% interval of …”
- “Performance on a different domain, language, generator, or later detector version may differ.”
- “Corroborate consequential decisions with drafts, sources, policy context, and human review.”

Never use:

- “Pangram proved this was written by AI.”
- “This score proves the author cheated.”
- “A zero score certifies 100% human authorship.”
- “No observed false positives means the true FPR is zero.”
