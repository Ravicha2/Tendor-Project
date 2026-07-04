# Write-Up: Does Better Document Parsing Improve Procurement Signal Extraction?

## 1 Methodology

### Arms compared

Three parser configurations isolate independent variables:

| Arm | OCR | VLM (picture description) | Tests |
|---|---|---|---|
| __baseline__ | Off | Off | Text layer only |
| __ocr__ | On | Off | Effect of OCR on scanned/image pages |
| __ocr_vlm__ | On | On | Effect of VLM on top of OCR |

Same extraction engine (LangExtract with `google/gemini-3.1-flash-lite` via OpenRouter, temperature 0) across all arms. Parser is the only variable.

### Parser: Docling

All three arms use Docling with `PyPdfiumDocumentBackend`. The `ocr` arm enables EasyOCR; the `ocr_vlm` arm adds picture description via `google/gemini-2.5-pro` through OpenRouter, with a procurement-focused prompt.

### Extraction: LangExtract

LangExtract processes each parsed markdown document with a structured extraction schema matching the brief's signal format. Two extraction passes with `max_char_buffer=2000` for longer documents. Source grounding maps to `evidence_excerpt`. Post-processing coerces types (budget_value to number, confidence_score clamped to 0-1, needs_human_review to bool).

### Documents

| # | Document | Difficulty | Pages | Tables | Images | Why included |
|---|---|---|---|---|---|---|
| 1 | Logan Transport Committee minutes | Easy | 10 | 16 | 1 | Short, regular text. Baseline should work fine. |
| 2 | Logan Special Budget Committee minutes | Medium | 31 | 48 | 1 | Budget tables where parser quality matters for project-to-dollar alignment. |
| 3 | Brisbane City Council minutes | Hard | 115 | 31 | 7 | Very long, sparse signals. Tests chunking and cost control. |
| 4 | City of Sydney agenda (HTML) | Edge | 0 | 1 | 39 | Tests HTML parsing without overfitting to PDF. |
| 5 | 96 Rickard Road Planning Agreement | Image-heavy | 76 | 18 | 27 | Scanned PDFs with engineering drawings, site plans, signatures. The strongest test case for VLM. |

Document 5 was added beyond the provided set because it has 27 images (engineering drawings, site plans, subdivision certificates, handwritten signatures) that are invisible to the baseline parser and directly test whether VLM recovers procurement-relevant content from figures.

### Metrics

- __Field accuracy__: for matching signals, correctness of `budget_value`, `asset_or_location`, `category`.
- **Parse latency**: time per document per arm.
- __Token cost__: VLM tokens (ocr_vlm arm) and extraction tokens (all arms).

No golden dataset is provided. Annotating procurement signals from council documents requires domain expertise in tendering that the author does not have. Without that expertise, manual annotation produces unreliable ground truth: under-counting real signals (not knowing what counts) and over-counting marginal ones (not knowing what does not). The comparison below uses raw signal counts, confidence scores, and structural analysis rather than precision/recall/F1 against a golden set.

### Sampled precision

Rather than attempt full golden-set annotation, a stratified random sample of 30 signals (1 per confidence tier per document per arm, where available) was manually reviewed. Each signal was judged as **actionable** (a real procurement opportunity a supplier could act on) or **noise** (too vague, not procurement-related, or a duplicate). Precision is the fraction of actionable signals in the sample.

| Arm | High (>=0.8) actionable | Medium (0.6-0.79) actionable | Low (<0.6) actionable | Overall precision |
|---|---|---|---|---|
| baseline | 3/3 (100%) | 4/5 (80%) | 0/4 (0%) | 7/12 (58%) |
| ocr | 3/3 (100%) | 3/5 (60%) | 1/5 (40%) | 7/13 (53%) |
| ocr_vlm | 2/3 (67%) | 3/4 (75%) | 0/4 (0%) | 5/11 (45%) |

Sampled from 36 signals across 5 documents (see Appendix B). Precision is consistent across arms (45-58%), with high-confidence signals quite actionable (67-100%) and low-confidence signals almost entirely noise (0-40%). The parser configuration does not meaningfully affect precision.

---

## 2 Results

### 2.1 Signal counts

| Document | baseline | ocr | ocr_vlm | Delta (ocr_vlm vs baseline) |
|---|---|---|---|---|
| 01 Easy (Logan Transport) | 6 | 5 | 5 | -1 |
| 02 Medium (Logan Budget) | 28 | 25 | 24 | -4 |
| 03 Hard (Brisbane Minutes) | 229 | 225 | 225 | -4 |
| 04 Edge (City of Sydney) | 11 | 11 | 11 | 0 |
| 05 Rickard Road Planning | 39 | 44 | __55__ | __+16 (+41%)__ |
| __Total__ | __313__ | __310__ | __320__ | __+7__ |

The only document where VLM produces a meaningful signal count increase is document 05, which contains 27 images (engineering drawings, subdivision certificates, site plans). In documents 01-04, signal counts are stable or slightly lower across arms.

However, raw signal counts overstate the VLM gain. After deduplication and confidence filtering (see section 3.1), VLM adds roughly 2-3 genuinely new high-confidence procurement signals to document 05, not 16.

### 2.2 Parse latency

| Document | baseline | ocr | ocr_vlm |
|---|---|---|---|
| 01 Easy (10 pages) | 36s | 38s | 43s |
| 02 Medium (31 pages) | 108s | 105s | 118s |
| 03 Hard (115 pages) | 86s | 157s | 185s |
| 04 Edge (HTML, 0 pages) | 0.08s | 0.05s | 0.07s |
| 05 Rickard Road (76 pages, 27 images) | 60s | 178s | __596s__ |

Key observations:

- OCR adds 0-70s depending on document length (most expensive on doc 03, the 115-page Brisbane minutes).
- VLM adds significant latency proportional to image count. Document 05 took 10 minutes because 27 images were each sent to `gemini-2.5-pro` sequentially.
- Documents 01-04 (1-7 images each) see only 2-29s of VLM overhead.

### 2.3 VLM token cost

| Document | VLM prompt tokens | VLM completion tokens | VLM total | VLM API calls |
|---|---|---|---|---|
| 01 Easy | 281 | 672 | 953 | 1 |
| 02 Medium | 281 | 1,366 | 1,647 | 1 |
| 03 Hard | 6,353 | 6,927 | 13,280 | 7 |
| 04 Edge | 0 | 0 | 0 | 0 |
| 05 Rickard Road | 40,095 | 30,776 | 70,871 | 27 |
| **Total** | **47,010** | **39,741** | **86,751** | **36** |

At OpenRouter pricing for `gemini-2.5-pro` (~$1.25/$10 per 1M tokens), VLM picture description cost approximately $0.46 total across all documents, with document 05 accounting for ~$0.40 of that.

### 2.4 Extraction token cost

| Document | Arm | Extract prompt tokens | Extract completion tokens | Extract total | Extract API calls |
|---|---|---|---|---|---|
| 01 Easy | baseline | 24,934 | 2,150 | 27,084 | 20 |
| 01 Easy | ocr | 20,934 | 2,027 | 22,961 | 20 |
| 01 Easy | ocr_vlm | 22,838 | 2,119 | 24,957 | 20 |
| 02 Medium | baseline | 99,060 | 8,639 | 107,699 | 78 |
| 02 Medium | ocr | 95,860 | 8,152 | 104,012 | 78 |
| 02 Medium | ocr_vlm | 98,628 | 8,349 | 106,977 | 78 |
| 03 Hard | baseline | 663,752 | 75,379 | 739,131 | 602 |
| 03 Hard | ocr | 656,552 | 74,516 | 731,068 | 602 |
| 03 Hard | ocr_vlm | 666,080 | 75,589 | 741,669 | 610 |
| 04 Edge | baseline | 28,204 | 4,422 | 32,626 | 24 |
| 04 Edge | ocr | 25,004 | 4,291 | 29,295 | 24 |
| 04 Edge | ocr_vlm | 25,004 | 4,354 | 29,358 | 24 |
| 05 Rickard Road | baseline | 210,442 | 13,367 | 223,809 | 192 |
| 05 Rickant Road | ocr | 219,558 | 14,667 | 234,225 | 194 |
| 05 Rickard Road | ocr_vlm | 245,566 | 18,494 | 264,060 | 224 |

Extraction token cost is dominated by document length. The `ocr_vlm` arm adds VLM picture descriptions to the markdown, increasing extraction input tokens by 5-17% depending on image content density. The extraction model cost difference across arms is marginal compared to VLM cost.

---

## 3 Where VLM helps: document 05 deep dive

Document 05 (96 Rickard Road Planning Agreement) is the clearest case where VLM adds value. It contains 27 images: engineering drawings, subdivision plans, site plans, landscape plans, council approval stamps, and handwritten signatures.

### What VLM recovered from images

The VLM arm produced 55 signals vs 39 for baseline (+41%). The 16 additional signals came from:

1. **Engineering drawings with "FOR CONSTRUCTION" stamps**: VLM identified project status markings (e.g. "ISSUED FOR CONSTRUCTION", "NOT FOR CONSTRUCTION") and project numbers (e.g. NL190570 for "Ingleburn Road Drainage"). However, VLM also misattributed adjacent-site labels as the subject project: "Proposed Woolworths Development" appears on the General Arrangement Plan as a neighboring site reference, not as the project being constructed (see section 8).
2. __Subdivision Works Certificates__: VLM read council approval stamps (Camden Council SWC numbers, Liverpool City Council approvals) and extracted them as `planned_action` and `capital_works_item` signals.
3. **Site plans**: VLM identified project names, addresses (90 Ingleburn Road, Leppington), developer names (Stevens Group, Northrop), and stage information ("Proposed Stage 1 Development", "Future Stage 2 Development").
4. **Handwritten dates**: VLM read "11 August 2025" from a handwritten date field.

### What VLM missed or got wrong

- Several VLM picture descriptions were for **signatures and CAPTCHAs** (images 18-26): the VLM correctly identified these as containing no procurement information, but they added noise to the parsed markdown without adding signals.
- **Low-resolution images** (images 8, 9, 14, 16): VLM correctly reported it could not read them, but no signal was recovered from these images.
- VLM hallucinated some details: e.g. image 13 was described as being from "London Borough of Camden" (confusing Camden, NSW with Camden, London).

### 3.1 Signal quality, not just quantity

The +41% raw count (55 vs 39 signals) is misleading. Breaking down the 25 VLM-only signals by confidence:

| Confidence tier | Count | Deduped unique projects | Assessment |
|---|---|---|---|
| High (>=0.8) | 7 | ~3 | After dedup and misattribution correction: 3 legitimate signals (see breakdown below). "Proposed Woolworths Development" (2 signals) misattributes an adjacent-site label as the subject project. "Proposed Stage 1 Development" (2 signals) is a stage label within the same Rickard Road development, not a distinct procurement opportunity. |
| Medium (0.6-0.79) | 12 | ~8 | Mixed: some real (infrastructure works, drainage), some vague ("Mixed-use development infrastructure works") |
| Low (<0.6) | 6 | ~3 | Mostly noise: null project names, vague references, duplicates of landscaping specs |

Near-duplicate signals are common. "Proposed Service Station" appears 3 times, "Proposed Woolworths Development" twice, "Ingleburn Road Drainage" twice, "Proposed Stage 1 Development" twice. These come from different pages of the same planning agreement describing the same project. After deduplication and excluding misattributions, VLM adds **3 genuinely accurate, high-confidence procurement signals** that are invisible to the baseline parser:

1. **"Ingleburn Road Drainage"** (conf 0.85): "ISSUED FOR CONSTRUCTION" stamp with specific project number NL190570. VLM read this from image 5 (a civil works drainage plan).
2. **"Proposed Service Station"** (conf 0.95): "FOR CONSTRUCTION" stamp and Camden Council SWC approval number. VLM read this from image 11 (a subdivision works certificate site plan).
3. **"Civil Works Plan - Town Centre Road / Ingleburn Road"** (conf 0.95): "ISSUED FOR CONSTRUCTION" stamp, Stevens Group as developer, Northrop as engineer. VLM read this from image 6.

The following high-confidence signals were **misattributed** and should not be counted as accurate:

- **"Proposed Woolworths Development"** (conf 0.85, 2 signals): The General Arrangement Plan (image 4) labels "Proposed Woolworths Development" as an adjacent site reference, not the subject of the construction drawing. VLM incorrectly identified it as the primary project.
- **"Proposed Stage 1 Development"** (conf 0.85, 2 signals): This is a stage label within the same 96 Rickard Road development, not a distinct procurement opportunity.

Mean confidence across arms for document 05: baseline 0.56, ocr 0.53, ocr_vlm 0.58. The slight VLM advantage comes from the high-confidence engineering-drawing signals, but most of the signal volume gain is medium- and low-confidence.

__No arm extracted any budget_value from document 02__ (the budget document). All 28/25/24 signals across baseline/ocr/ocr_vlm have `budget_value: null`. since no actual value mentioned in the same chunk

### Signal quality comparison

Looking at the signals unique to the `ocr_vlm` arm for document 05, the VLM arm found signals like:

- `capital_works_item`: "Ingleburn Road Drainage" works with project number NL190570, stamped "ISSUED FOR CONSTRUCTION".
- `capital_works_item`: "Proposed Service Station" at 90 Ingleburn Road, Leppington, with a Camden Council subdivision works certificate (SWC) approval.
- `capital_works_item`: "Civil Works Plan - Town Centre Road / Ingleburn Road" with Stevens Group as developer and "ISSUED FOR CONSTRUCTION" stamp.

These 3 signals are genuine procurement information recovered from engineering drawings that are entirely invisible in the baseline parsed markdown. VLM also produced misattributed signals from the same drawings:

- `capital_works_item`: "Proposed Woolworths Development" at 60 Ingleburn Road. This label appears on the General Arrangement Plan as an adjacent site reference, not as the project being constructed. VLM read the text correctly but misinterpreted its role in the drawing.
- `capital_works_item`: "Proposed Stage 1 Development". This is a stage label within the same 96 Rickard Road development, not a distinct procurement opportunity.

---

## 4 Where VLM does not help

### Documents 01-03 (text-dominant PDFs)

For the Logan and Brisbane documents, signal counts are essentially flat across arms (variations of 1-4 signals, within extraction noise). These documents are text-heavy with minimal image content (1-7 images, mostly logos and headers). The VLM picture descriptions add no procurement-relevant content because the images are decorative (council logos, "NOTED" stamps, signatures).

### Document 04 (HTML)

The City of Sydney HTML agenda has 39 images but they are decorative/formatting icons, not content-bearing. VLM produced 0 picture descriptions (all were below the area threshold or not renderable). Signal count is identical across all arms (11).

### Signal count decreases

Interestingly, signal counts slightly decreased from baseline to OCR/VLM for documents 01-03. This is likely because minor text extraction differences (OCR artifacts, slightly different whitespace handling) cause LangExtract to merge or skip signals at chunk boundaries. The differences are small (1-4 signals) and fall within normal extraction variance.

---

## 5 Structural comparison: table and text preservation

| Document | Arm | Tables detected | Pages | Parse output size |
|---|---|---|---|---|
| 01 Easy | all | 16 | 10 | ~18-19 KB |
| 02 Medium | all | 48 | 31 | ~75 KB |
| 03 Hard | all | 31 | 115 | ~584 KB |
| 04 Edge | all | 1 | 0 | ~20 KB |
| 05 Rickard Road | all | 18 | 76 | 181 KB (baseline) / 183 KB (ocr) / __212 KB (ocr_vlm)__ |

Table counts are identical across arms because Docling's TableFormer runs regardless of OCR/VLM settings. The `ocr_vlm` arm produces larger markdown for document 05 because picture descriptions are injected inline, adding ~31 KB of VLM-generated text.

For document 05 specifically, the baseline markdown is 181 KB vs 212 KB for `ocr_vlm`. The 31 KB difference comes entirely from VLM picture descriptions embedded in the document, which the extraction model can then use as evidence for signals.

---

## 6 Limitations of golden dataset annotation

No golden dataset is provided. Annotating procurement signals from council documents requires domain expertise in tendering and local government procurement that the author does not have. Without that expertise, manual annotation is unreliable: annotators without domain knowledge will both under-count real signals (not recognising what counts as a procurement opportunity) and over-count marginal ones (not recognising what is too vague or already covered). Rather than report unreliable precision/recall/F1 numbers, this write-up uses raw signal counts, confidence score distributions, and structural analysis to compare arms.

---

## 7 Recommendation

### VLM benefits is real, but can also add new class of complexity

VLM picture description adds genuinely new signals for **image-heavy planning documents** containing engineering drawings, subdivision certificates, and approval stamps. After deduplication, confidence filtering, and excluding misattributions (where VLM reads adjacent-site labels or stage labels as distinct projects), this amounts to roughly 3 additional accurate, high-confidence signals per image-heavy document, not the 16 that raw counts suggest.

For 4 of 5 documents (text-dominant PDFs and HTML), VLM produced equal or slightly fewer signals than baseline while adding latency and cost. Even for document 05, the mean confidence score barely improved (0.58 vs 0.56).

### Conditions for production deployment

1. **Route by image content, not blindly.** Run VLM only on documents where image analysis is likely to add value. A simple heuristic: skip VLM for documents where all images are below a size threshold or where page count to image ratio is very high (i.e. mostly text with a few decorative logos). This avoids spending ~596s and 70K VLM tokens on a document like 05 when a quick pre-check could route it differently.
2. **Cost is manageable.** Total VLM cost across all 5 documents was ~$0.46 at gemini-2.5-pro pricing. Even at scale (thousands of documents), VLM cost is negligible compared to extraction cost (which dominates at 700K+ tokens for the Brisbane minutes). The real cost is latency, not money.
3. **Latency is the bottleneck.** Document 05 took 10 minutes to parse with VLM because images are processed sequentially. Parallelizing VLM calls or using a faster model for picture description would cut this significantly. Consider gemini-2.5-flash for picture description (lower quality per image, but 10x faster and cheaper) with a fallback to gemini-2.5-pro for images that appear to contain engineering drawings or approval stamps.
4. **OCR alone is not worth the latency for text-layer PDFs.** Documents 01-04 are text-layer PDFs where OCR adds no new content (the text layer already contains all text). OCR only matters for scanned/image-only pages. Consider enabling OCR only when page text is empty or below a threshold.
5. **Filter out noise images.** The VLM described signatures, CAPTCHAs, and low-resolution thumbnails as containing "no procurement information." These descriptions add ~5 KB of noise per document with zero signal gain. Pre-filter images by size and resolution before sending to VLM.
6. __Parser quality does not fix extraction gaps.__ No arm recovered any `budget_value` from document 02 (the budget document). All 28/25/24 signals had `budget_value: null`. Table structure was preserved identically across arms (48 tables detected in all), but the extraction model still failed to pull dollar figures. This is an extraction-layer problem, not a parser-layer problem.

---

## 8 Limitations

- **Single extraction model.** Results may differ with a different extraction model. The parser comparison is fair because extraction is constant, but absolute signal quality depends on the LLM.
- **Small sample size.** 5 documents is not enough for statistical significance. The finding is directional, not definitive.
- **VLM model variability.** gemini-2.5-pro picture descriptions may change over time. Results were captured once at temperature 0, but API behavior may drift.
- **Document 05 was self-selected.** I chose it because it had many images and was likely to show a VLM effect. This is an explicit bias toward finding an effect, not a random sample.
- **No scanned-only PDF tested.** All PDFs in the test set have text layers. The brief's concern about OCR recovery from image-only pages remains untested.
- **HTML document has no VLM effect.** The City of Sydney HTML had 39 images that were all formatting/decorative. VLM produced 0 picture descriptions for this document.
- **No deduplication in the pipeline.** The same project (e.g. "Proposed Service Station") can produce 3 separate signals from 3 different pages. Signal counts overstate the real information gain. After deduplication, VLM adds 4-5 genuinely new high-confidence signals, not 16.
- __All doc 05 signals are `capital_works_item`.__ The extraction model did not produce any `procurement_intent`, `budget_approved`, or `planned_action` signals from the engineering drawings, even though VLM descriptions contained phrases like "FOR CONSTRUCTION" and "Subdivision Works Certificate" that could qualify as procurement intent.
- **VLM recovers text from images but does not understand construction drawings.** The VLM correctly OCR'd labels like "Proposed Woolworths Development" from General Arrangement Plans, but misinterpreted them as the subject of the construction drawing. In practice, "Proposed Woolworths Development" labels an adjacent site on the GA Plan, not the project being built. Similarly, "Proposed Stage 1 Development" is a stage label within the same Rickard Road project, not a distinct procurement opportunity. This means 4 of the 7 high-confidence VLM-only signals are misattributed. VLM is an OCR upgrade for images, not an engineering-drawing reader.
- __No budget values recovered.__ Zero signals across all arms have `budget_value` for document 02 (the budget document). Parser quality did not fix extraction-level failures to pull dollar figures from tables.

---

## 9 Technology choices

| Component | Choice | License | Rationale |
|---|---|---|---|
| Parser | Docling 3.x | MIT | Best open-source document parser with built-in OCR, table extraction, and VLM integration. Single library for all three arms. |
| OCR engine | EasyOCR (via Docling) | Apache 2.0 | Docling's default OCR backend. Runs on CPU. |
| VLM | gemini-2.5-pro via OpenRouter | Commercial API | High-quality image understanding. OpenRouter provides unified API access. |
| Extraction | LangExtract (google-gemini) | Apache 2.0 | Structured extraction with source grounding. Maps naturally to the signal schema. |
| Extraction model | gemini-3.1-flash-lite via OpenRouter | Commercial API | Fast and cheap. Good enough for structured extraction where the parser is the variable under test. |

---

## Appendix A: Raw results

See the `results/` directory (included in the submission zip). Each arm (`baseline/`, `ocr/`, `ocr_vlm/`) contains parsed markdown, parse metadata, extracted signals, and extraction metadata for all five documents.

---

## Appendix B: Sampled signals for precision review

Each signal below was sampled from the extraction results (1 per confidence tier per document, where available). Mark each as **A** (actionable procurement opportunity) or **N** (noise: too vague, not procurement-related, or duplicate).

### baseline

| #   | Doc             | Tier | Conf | Signal                                             | Evidence                                                                                                                                    | A/N |
| --- | --------------- | ---- | ---- | -------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------- | --- |
| 1   | 01 Easy         | M    | 0.65 | Local Roads (Kerb and Channel) Program             | Local Roads (Kerb and Channel) Program of Council's Capital Roadworks and Drainage Program                                                  | A   |
| 2   | 02 Medium       | M    | 0.65 | 2026/27 Environmental Levy Program                 | 2026/27 Environmental Levy endorsed for inclusion in the 2026/27 budget                                                                     | A   |
| 3   | 02 Medium       | L    | 0.20 | null                                               | Consideration of Item 5 in Closed Session pursuant to Section 254J(3) of the Local Government Regulation 2012                               | N   |
| 4   | 03 Hard         | H    | 0.95 | Eric Crescent pedestrian safety improvements       | Petition requesting Council install a wombat crossing or shared zone on Eric Crescent outside Mackenzie Place Park, Annerley                | A   |
| 5   | 03 Hard         | M    | 0.70 | Salisbury Recreational Reserve BMX track construct | construction of the BMX jump track at Salisbury Recreational Reserve                                                                        | N   |
| 6   | 03 Hard         | L    | 0.45 | Bus fleet fuel transition or procurement           | The bus fleet is predominantly diesel and the council is facing risk due to fuel shortages                                                  | N   |
| 7   | 04 Edge         | H    | 0.95 | Parks and Street Greening Maintenance Services     | Tender - T-2025-1686 - Parks and Street Greening Maintenance Services                                                                       | A   |
| 8   | 04 Edge         | M    | 0.65 | Town Hall Square Transformation                    | Continuing the Transformation of Central Sydney - Project Scope - Town Hall Square                                                          | A   |
| 9   | 04 Edge         | L    | 0.30 | Delivery Program 2025-2029                         | 2025/26 Quarter 2 Review - Delivery Program 2025-2029                                                                                       | N   |
| 10  | 05 Rickard Road | H    | 0.85 | Developer Works - Trunk Drainage and Landscaping   | Construction of trunk drainage comprising underground culverts and landscaping works                                                        | A   |
| 11  | 05 Rickard Road | M    | 0.65 | Mixed use development site                         | Development of mixed use site including service station, McDonald's, child care facility, health services, office, hotel, and food premises | A   |
| 12  | 05 Rickard Road | L    | 0.40 | Rickard Road Planning Agreement                    | Rickard Road Planning Agreement                                                                                                             | N   |

### ocr

| #   | Doc             | Tier | Conf | Signal                                             | Evidence                                                                                                            | A/N |
| --- | --------------- | ---- | ---- | -------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------- | --- |
| 13  | 01 Easy         | M    | 0.65 | Logan Reserve Residential Subdivision (109 Lots)   | Development application COM/63/2023 for a Place of Worship and Community Use at 283-293 Logan Reserve Road          | A   |
| 14  | 01 Easy         | L    | 0.45 | Draft Logan Plan Refinement                        | Refinement of the Draft Logan Plan including feasibility of removing the Flood Investigation Area from overlay maps | N   |
| 15  | 02 Medium       | M    | 0.65 | 2026/27 Environmental Levy Program                 | 2026/27 Environmental Levy endorsed for inclusion in the 2026/27 budget                                             | A   |
| 16  | 02 Medium       | L    | 0.45 | 2026/27 recurrent budget submissions               | Endorsement of 2026/27 recurrent budget submissions for inclusion in the 2026/27 budget                             | N   |
| 17  | 03 Hard         | H    | 0.85 | Pallara bus stops                                  | $235,000 for Pallara for Councillor KIM out there as well                                                           | A   |
| 18  | 03 Hard         | M    | 0.65 | BMX track construction                             | Construction of a dirt BMX track                                                                                    | N   |
| 19  | 03 Hard         | L    | 0.45 | Mullens Street and Riding Road intersection improv | Council have, in the past, looked at options to improve the intersection of Mullens Street and Riding Road          | A   |
| 20  | 04 Edge         | H    | 0.95 | Parks and Street Greening Maintenance Services     | Tender - T-2025-1686 - Parks and Street Greening Maintenance Services                                               | A   |
| 21  | 04 Edge         | M    | 0.65 | Town Hall Square Transformation                    | Continuing the Transformation of Central Sydney - Project Scope - Town Hall Square                                  | A   |
| 22  | 04 Edge         | L    | 0.30 | Delivery Program 2025-2029                         | 2025/26 Quarter 2 Review - Delivery Program 2025-2029                                                               | N   |
| 23  | 05 Rickard Road | H    | 0.85 | Developer Works - Trunk Drainage and Landscaping   | Construction of trunk drainage comprising underground culverts and landscaping works                                | A   |
| 24  | 05 Rickard Road | M    | 0.65 | Drainage facilities development                    | Developer to provide land and works that are earmarked for drainage facilities in the Council's contributions plan  | N   |
| 25  | 05 Rickard Road | L    | 0.35 | Developer Works Rectification                      | Rectification of Defects                                                                                            | N   |

### ocr_vlm

| #   | Doc             | Tier | Conf | Signal                                         | Evidence                                                                                                                     | A/N |
| --- | --------------- | ---- | ---- | ---------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------- | --- |
| 26  | 01 Easy         | M    | 0.65 | Veresdale Scrub Road upgrade                   | Veresdale Scrub Road, Veresdale Scrub be included in the Local Roads Statement of Intent 2022 with ranking of Priority No. 2 | A   |
| 27  | 02 Medium       | M    | 0.65 | 2026/27 Volunteer Fire Brigade Separate Charge | Endorsement of the 2026/27 Volunteer Fire Brigade Separate Charge for inclusion in the 2026/27 budget                        | N   |
| 28  | 02 Medium       | L    | 0.40 | 2026/27 Annual Budget                          | 2026/27 Budget - Proposed Annual Budget                                                                                      | N   |
| 29  | 03 Hard         | H    | 0.95 | March 2026 Contracts and Tendering             | Contracts and tendering report for March 2026                                                                                | A   |
| 30  | 03 Hard         | M    | 0.65 | Park tree planting                             | Tree planting in a park at a cost of $38,000                                                                                 | A   |
| 31  | 03 Hard         | L    | 0.40 | Pedestrian Access Review                       | PETITION - REQUESTING COUNCIL REVIEW PEDESTRIAN ACCESS BETWEEN HARRIER STREET AND MILES PLATTING ROAD, ROCHEDALE             | N   |
| 32  | 04 Edge         | H    | 0.95 | Parks and Street Greening Maintenance Services | Tender - T-2025-1686 - Parks and Street Greening Maintenance Services                                                        | A   |
| 33  | 04 Edge         | L    | 0.30 | Delivery Program 2025-2029                     | 2025/26 Quarter 2 Review - Delivery Program 2025-2029                                                                        | N   |
| 34  | 05 Rickard Road | H    | 0.85 | Proposed Stage 1 Development                   | Proposed Stage 1 Development at Ingleburn Road, Leppington NSW 2179                                                          | N   |
| 35  | 05 Rickard Road | M    | 0.65 | Trunk Drainage Infrastructure Works            | Developer Works for trunk drainage infrastructure                                                                            | A   |
| 36  | 05 Rickard Road | L    | 0.50 | 96 Rickard Road Planning Agreement             | 96 Rickard Road Planning Agreement                                                                                           | N   |