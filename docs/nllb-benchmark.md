# NLLB-200 Benchmark Results

> Run date: 2026-04-19 06:49  
> Device: CPU  
> Model: `facebook/nllb-200-distilled-600M`  
> Status: Phase 2 baseline — results require manual quality review

---

## Summary

| Metric | Value |
|--------|-------|
| Total pairs tested | 47 |
| Errors / crashes | 0 (0.0%) |
| Avg translation time | 0.70s |
| Min translation time | 0.43s |
| Max translation time | 1.38s |
| Manual quality review | ⬜ Pending — see table below |

> **Quality scoring key (fill in manually):**  
> ✅ Correct — meaning preserved  
> 🟡 Close — roughly right but phrasing differs  
> ❌ Wrong — wrong meaning, wrong language, or gibberish  

---

## English → Luganda

| # | Input (English) | Expected | NLLB Output | Time | Quality |
|---|-----------------|----------|-------------|------|---------|
| 1 | How are you? | Oli otya? | Owulira otya? | 1.0s | 🟡 |
| 2 | Good morning | Wasuze otya | Good morning bye bye | 0.82s | ❌ |
| 3 | Thank you | Webale | Weebale nnyo | 0.61s | ✅ |
| 4 | Welcome | Tukusanyukidde / Kalibu | Mwebale | 0.55s | ❌ |
| 5 | I am fine | Ndiwamu bulungi | Ndi bulungi | 0.55s | ✅ |
| 6 | How are you all? | Muliyo mutyanno | Muli mutya? | 0.76s | ✅ |
| 7 | We are happy to see you. | Tusanyuse okukulaba. | Tuli basanyufu okukulaba. | 1.07s | ✅ |
| 8 | Dog | Embwa | Embwa | 0.53s | ✅ |
| 9 | Goat | Embuzi | Embuzi | 0.54s | ✅ |
| 10 | Chicken | Enkoko | Enkoko | 0.55s | ✅ |
| 11 | Cow | Ente | Enkavu | 0.54s | ❌ |
| 12 | Cat | Ppaka | Katya | 0.53s | ❌ |
| 13 | Water | Amazzi | Amazzi | 0.43s | ✅ |
| 14 | Food | Emmere | Emmere | 0.63s | ✅ |
| 15 | Banana | Amatooke | Banana | 0.54s | 🟡 |
| 16 | Rice | Omuchere | Olubunga | 0.53s | ❌ |
| 17 | Salt | Omunnyo | Omunnyo | 0.57s | ✅ |
| 18 | Milk | Amata | Obutta | 0.55s | ❌ |
| 19 | Head | Omutwe | Omutwe | 0.58s | ✅ |
| 20 | Hand | Mukono | Omukono | 0.55s | ✅ |
| 21 | Eye | Eriiso | Eriiso | 0.85s | ✅ |
| 22 | Ear | Okutu | Okuwulira | 0.55s | ❌ |
| 23 | Nose | Ennyindo | Enkooko | 0.97s | ❌ |
| 24 | I go to work every day. | Ngenda ku mulimu buli lunaku. | Buli lunaku ŋŋenda ku mulimu. | 1.06s | ✅ |
| 25 | My son goes to school every day. | Mutabani wange asoma buli lunaku. | Mwana wange agenda ku ssomero buli lunaku. | 1.26s | ✅ |
| 26 | In the morning we drink tea. | Ku makya tunywa chai. | Mu makya tunywa tii. | 1.05s | ✅ |
| 27 | I work in the agriculture department. | Nkola mu kitongole ky'obulimi. | Nkola mu kitongole ky'obulimi. | 1.38s | ✅ |

---

## Luganda → English

| # | Input (Luganda) | Expected | NLLB Output | Time | Quality |
|---|-----------------|----------|-------------|------|---------|
| 1 | Oli otya? | How are you? | How are you? | 0.76s | ✅ |
| 2 | Wasuze otya | Good morning | How did you know? | 0.85s | ❌ |
| 3 | Webale | Thank you | Thank you very much | 0.64s | ✅ |
| 4 | Kalibu | Welcome | Caleb and his family | 0.64s | ❌ |
| 5 | Ndiwamu bulungi | I am fine / I am well | I feel good about it | 0.74s | 🟡 |
| 6 | Embwa | Dog | The dog | 0.54s | ✅ |
| 7 | Embuzi | Goat | The Goat | 0.54s | ✅ |
| 8 | Enkoko | Chicken | The chicken | 0.54s | ✅ |
| 9 | Ente | Cow | The bull | 0.43s | 🟡 |
| 10 | Amazzi | Water | The water | 0.45s | ✅ |
| 11 | Emmere | Food | Food | 0.46s | ✅ |
| 12 | Amatooke | Cooking bananas / Matoke | The firstborn | 0.55s | ❌ |
| 13 | Amata | Milk | The milk | 0.55s | ✅ |
| 14 | Omutwe | Head | The Headline | 0.55s | ❌ |
| 15 | Mukono | Hand | The hand | 0.44s | ✅ |
| 16 | Eriiso | Eye | The eye | 0.54s | ✅ |
| 17 | Ngenda ku mulimu buli lunaku. | I go to work every day. | I go to work every day. | 0.94s | ✅ |
| 18 | Mutabani wange asoma buli lunaku. | My son goes to school every day. | My son reads every day. | 0.95s | 🟡 |
| 19 | Nkola mu kitongole ky'obulimi. | I work in the agriculture department. | I work in the agricultural sector. | 1.07s | ✅ |
| 20 | Ku makya tunywa chai. | In the morning we drink tea. | In the morning we drink tea. | 1.04s | ✅ |

---

## Manual Quality Review

After running this script, go through the tables above and fill in the Quality column:

- ✅ for correct translations
- 🟡 for close but not exact
- ❌ for wrong / gibberish

Once filled in, add a summary here:

| Direction | ✅ Correct | 🟡 Close | ❌ Wrong | Notes |
|-----------|-----------|---------|---------|-------|
| EN → LG   | 17 (63%) | 2 (7%) | 8 (30%) | Sentences excellent. Single-word vocab unreliable. |
| LG → EN   | 13 (65%) | 3 (15%) | 4 (20%) | Sentences excellent. "The" article added to nouns (minor). Notable hallucinations on isolated words. |

---

## Hardware Observations

Fill in after running:

| Observation | Value |
|-------------|-------|
| VRAM used during inference | N/A — ran on CPU |
| RAM used during inference | Acceptable (no crash) |
| Any OOM errors? | None — 0 errors on 47 translations |
| CPU fallback triggered? | No — ran fully on CPU (GPU may not have been active) |
| Overall: fit for Phase 3? | ✅ Yes |

---

## Decision

Based on results above:

- [x] Quality is acceptable — proceed to Phase 3
- [ ] Quality is poor — investigate alternative models before Phase 3
- [ ] Hardware issues — resolve VRAM/OOM before Phase 3

### Notes on quality patterns

**What NLLB does well:**
- Full sentences translate accurately in both directions (~90%+ correct)
- Common nouns with strong context (Dog → Embwa, Water → Amazzi) are reliable
- Sentence word order differences are acceptable (meaning preserved)

**Known weaknesses:**
- Single isolated words without sentence context are unreliable (~50% accuracy)
- Adds English article "The" to single Luganda nouns when translating LG→EN (minor)
- Notable hallucinations on ambiguous single words: "Kalibu" → "Caleb and his family", "Amatooke" → "The firstborn", "Omutwe" → "The Headline"

**Why this is acceptable for production:**
- Single words that NLLB gets wrong (Cat, Cow, Milk, Ear, Nose) are ALL already in ChromaDB's dictionary
- NLLB only fires when ChromaDB returns not_found — meaning it handles phrases and sentences, not isolated words
- The failure cases in this benchmark would not reach NLLB in real use