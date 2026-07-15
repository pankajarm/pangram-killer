# Detector Evaluation Method

Use this workflow for an authorized, labeled audit. It is designed for a fixed detector policy, not for optimizing text against a detector.

## 1. Define the Decision

Write down before evaluation:

- the allowed and disallowed AI-use policy;
- which ground-truth labels count as positive;
- which ground-truth labels count as negative, rejecting all undeclared labels;
- which returned predictions count as positive, or one fixed numeric threshold;
- which returned predictions count as negative when using categorical output;
- the Pangram model/API version and collection dates;
- target domains, languages, lengths, authors, and input formats;
- the consequence of a false positive and a false negative;
- plausible deployment prevalence.

Do not choose the operating rule after inspecting final-test outcomes. If calibration is required, use a separate calibration set and lock the policy before final evaluation.

## 2. Construct Representative Labels

Use process-verified examples where possible:

- human samples with drafts, version history, or pre-LLM publication dates;
- AI samples generated under recorded models, prompts, and dates;
- separately labeled AI-edited human and human-edited AI samples;
- current, unseen generators and realistic task prompts;
- enough independent authors and sources to avoid treating chunks from one document as independent evidence.

Avoid using detector output as ground truth. Record uncertainty rather than forcing ambiguous mixed-authorship examples into a binary class.

Keep calibration and test documents separated by author/source. Use a time split when deployment must generalize to later writing or models.

## 3. Preserve the Evaluation Record

For each example, store:

- stable ID;
- truth label and how it was established;
- detector prediction and optional score;
- Pangram version and request date;
- domain, language, length, author/source cluster, and input format;
- raw-result hash or secured raw response.

Do not place confidential submitted text in an audit report unless necessary and authorized.

## 4. Compute the Confusion Matrix

For positive class `P` and negative class `N`:

| | Predicted positive | Predicted negative |
|---|---:|---:|
| Truth positive | TP | FN |
| Truth negative | FP | TN |

Metrics:

- sensitivity / TPR = `TP / (TP + FN)`
- false-negative rate = `FN / (TP + FN)`
- specificity / TNR = `TN / (TN + FP)`
- false-positive rate = `FP / (TN + FP)`
- precision / PPV = `TP / (TP + FP)`
- negative predictive value = `TN / (TN + FN)`
- accuracy = `(TP + TN) / N`
- balanced accuracy = `(TPR + TNR) / 2`
- F1 = `2TP / (2TP + FP + FN)`

Return an undefined metric as `null`, not zero.

## 5. Report Uncertainty

Use a Wilson 95% interval for binomial proportions. Zero observed errors does not imply a zero population error rate.

A useful one-sided approximation for zero observed errors is the rule of three: the 95% upper bound is roughly `3/n`. Examples:

- 0 errors in 40 representative samples: upper bound about 7.5%;
- 0 in 300: about 1%;
- 0 in 1,992: about 0.15%;
- bounding an error rate below 0.01% with no observed errors requires roughly 30,000 independent representative cases.

Independence matters. Multiple windows or passages from one author/document should be clustered or bootstrapped at the author/source level for a publishable audit.

## 6. Project Realistic Base Rates

Sensitivity and FPR alone do not give the probability that a positive flag is correct in deployment.

For prevalence `pi`, sensitivity `s`, FPR `f`, and specificity `c = 1-f`:

- projected PPV = `s*pi / (s*pi + f*(1-pi))`
- projected NPV = `c*(1-pi) / (c*(1-pi) + (1-s)*pi)`

Example: with 99% sensitivity, 1% FPR, and 1% prevalence, projected PPV is 50%. With the same sensitivity and prevalence but 0.1% FPR, projected PPV is about 90.9%.

These projections assume conditional error rates remain stable at the deployment base rate and distribution. State that assumption.

## 7. Stratify Before Generalizing

At minimum, inspect:

- domain and genre;
- language and translation status;
- native/non-native writer groups where ethically and legally appropriate;
- text-length bands;
- raw text versus extracted PDF;
- pure human, pure AI, and editing/assistance categories;
- generator family and release date;
- detector version and collection date.

Report subgroup sample sizes and intervals. A tiny subgroup rate is diagnostic, not a stable policy estimate.

The bundled evaluator requires a present, nonempty, unique ID for every row, at least 30 total rows, and 10 examples in each truth class for aggregate reporting. It suppresses subgroup metrics below the same total or class-specific floors. Subgroup fields come from a fixed allowlist of audit dimensions such as domain, language, length band, format, detector version, generator family/release period, and assistance category. Never encode rewrite attempts, variants, rounds, prompts, or candidates inside an allowed field; benchmarking must not become a detector-optimization scoreboard.

## 8. Make a Consequence-Aware Recommendation

For high-cost false positives:

- treat the detector as triage;
- require corroboration from drafts, sources, oral explanation, or version history;
- give the affected person notice and a meaningful review path;
- prohibit automated sanctions from a score alone;
- monitor version drift and rerun a hidden audit after product updates.

For prevalence research, aggregate estimates may be more defensible than individual accusations if the design accounts for error and sampling.

## 9. State the Limits

Every report should say:

> This evaluation measures a fixed policy on the labeled sample and Pangram version recorded here. It does not prove authorship for an individual document or guarantee performance under other distributions or future versions.

Do not translate a company benchmark, AUROC, or balanced-dataset accuracy directly into real-world precision.
