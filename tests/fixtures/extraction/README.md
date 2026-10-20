# Offline extraction fixtures (version 1)

Every HTML file and IOC case here is **hand-authored synthetic test data**, not a
publisher capture, paraphrased article, or verified current publisher layout.
Publisher names identify the configured source matrix only. Container choices
exercise the collector's existing supported HTML branches; their assignment to
publishers is illustrative and does not establish that those sites use them.
No web pages were fetched to create this corpus. CISA is included as a disabled
source control; its configuration remains disabled.

`layouts.json` records expected selection scope, required text, excluded noise,
and exact IOC candidates for all 11 source labels. Fixtures exercise all seven
recognized content classes plus article/main/body fallbacks, tables, code,
entities, inline formatting, line breaks, ignored link destinations, navigation,
templates, sidebars, and recommendation cards. Repeated shared content means
these are 11 routing cases, not 11 independent samples of article diversity.
Short pages, CSS visibility, malformed HTML recovery, JavaScript rendering,
PDFs, images, and linked IOC files are not covered by this matrix.

`iocs.json` has 16 independently labeled text cases with 24 expected unique
`(type, normalized value)` pairs. Labels were written before running the baseline
extractor. The `label_rationale` explains positives and negatives. All eight
current candidate types occur: SHA256, SHA1, MD5, IPv4, IPv6, URL, email, domain.
Benign reference URLs/emails are positives because the API returns syntactic
**candidates**, not a verdict of maliciousness. URL hosts are also labeled as
domain candidates, matching the existing contract. No DNS resolution or threat
intelligence lookup is performed. The corpus excludes cap saturation; a separate
regression test covers the 2,000-result cap and deduplication.

Run from the repository (or extracted server bundle) root:

```console
python -m unittest tests.test_extraction -v
python -m tests.benchmark_iocs
```

The scorer compares exact pairs per case. TP is the set intersection, FP is
predicted minus expected, FN is expected minus predicted. Micro totals sum these
counts across cases; precision = TP/(TP+FP), recall = TP/(TP+FN). Undefined ratios
are JSON null. Duplicate occurrences within a case count once; the same value in
two cases counts twice. Reports include per-type totals and per-case mismatches.
HTML routing assertions are separate from this text-only benchmark.

The small corpus was used to find and fix regressions: it is a development set,
not held-out evaluation. Perfect scores on it cannot be generalized to live
publishers, malicious IOC precision/recall, or all valid address/URL syntax.
Known unmeasured areas include domain-like strings in URL paths, embedded IPv4
IPv6 forms, URL punctuation ambiguity, Unicode/IDN, uncommon file extensions,
additional defanging, and invalid host labels. Ignoring `aside` avoids sidebar
noise but also omits substantive content if a publisher places it there. A future
real-world evaluation needs dated, permitted captures and independently reviewed
annotations with benign references and layout diversity.
