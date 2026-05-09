# PDF Extraction Plan — Luganda AI Studio

> Status: PARKED — do not start until Project Phase 4 (Data Pipeline)
> Connects to: project_plan.md Phase 4 → "PDF parser" task
> Also feeds: training-plan.md Phase 3 → LoRA fine-tuning (needs 500+ verified pairs first)
> Created: 2026-04-17

---

## Purpose

Extract Luganda-English translation pairs from the raw PDF documents in
`datasets/raw_downloads/` and convert them into the standard JSON format
used by the ingestion pipeline.

This is a data enrichment task. It does not unblock NLLB-200 (Phase 2) or
Teaching Mode (Phase 3). It becomes useful when preparing fine-tuning data
for LoRA (training-plan Phase 3).

---

## PDF Inventory

| File | Pages | Type | Layout | Priority | Expected Pairs |
|------|-------|------|--------|----------|----------------|
| `UG_Luganda_Language_Lessons.pdf` | 9 | Selectable text | Inline bilingual — Luganda and English on same line | **HIGH** | ~150–200 |
| `FSI - Luganda Basic Course - Instructor and Student Text.pdf` | 383 | Selectable text | English instructor guide with Luganda embedded | MEDIUM | ~300–500 (noisy) |
| `Dictionary.pdf` | 7 | Selectable text | Intro/orthography only — actual entries unclear | LOW | Unknown |
| `A_Handbook_of_Luganda.pdf` | 106 | Scanned + bad OCR | Garbled text — needs re-OCR | LOW | 0 without re-OCR |
| `Luganda-Ganda-2014-All-Bible.pdf` | 2218 | Selectable text | Pure Luganda — no English inside | **HIGH (future)** | ~31,000 if paired with English Bible |

---

## Extraction Approaches by File

### 1. UG_Luganda_Language_Lessons.pdf — Regex extraction

**Layout:** Inline pairs. Luganda phrase followed by English on the same line.

```
Wasuze otyanno nnyabo?  How did you spend the night madam?
Gyendi.  I am fine.
Nze Herbert.  I am Herbert.
```

**Method:** `pdfplumber` to extract text, regex to detect lines where
Luganda and English appear together. Pattern: text before a question mark or
period, followed by English translation.

**Script to build:** `scripts/extract_ug_luganda.py`

**Output:** `data/datasets/ug_luganda_lessons_sentences.json`

---

### 2. FSI Luganda Basic Course — Glossary + dialogue extraction

**Layout:** English teaching instructions with Luganda glossary entries and
dialogues embedded throughout. Not a clean two-column format.

**Method:** Extract glossary sections (`.tegeera (.tegedde) understand` pattern)
and any inline Luganda-English sentence pairs. Expect noisy output — requires
manual review pass before ingestion.

**Script to build:** `scripts/extract_fsi_course.py`

**Output:** `data/datasets/fsi_course_vocabulary.json` (needs_review: true)

---

### 3. Luganda Bible — Verse alignment with English Bible

**Layout:** Full Luganda Bible, 2,218 pages. No English inside. Structured by
book → chapter → verse.

**Method:**
1. Extract Luganda text by verse reference using `pdfplumber`
2. Download English Bible as plain text (KJV from Project Gutenberg — public domain)
3. Align by book/chapter/verse reference
4. Output ~31,000 verse pairs

**This is the highest-value source** but a significant project.

**Script to build:** `scripts/extract_bible_pairs.py`

**Output:** `data/datasets/bible_sentences.json`

**Note:** Bible text is highly formal/religious register. Good for volume,
less useful for everyday Luganda. Mark subcategory as "religious".

---

### 4. A_Handbook_of_Luganda.pdf — Needs re-OCR

**Problem:** The existing text layer is garbled (scanned and OCR'd badly by
Internet Archive).

**Method:** Re-OCR using `pytesseract` with Luganda/English language packs,
or send to a cloud OCR service (Google Vision, AWS Textract).

**Do this last** — uncertain quality until you try it on a few pages.

---

## Output Format

All extracted files must match the standard ingestion format:

```json
{
  "metadata": {
    "source": "ug_luganda_lessons",
    "category": "sentences",
    "date_added": "YYYY-MM-DD",
    "auto_imported": true,
    "needs_review": true
  },
  "entries": [
    {
      "luganda": "Wasuze otyanno nnyabo?",
      "english": "How did you spend the night madam?",
      "category": "imported",
      "subcategory": "peace_corps_lessons",
      "difficulty": "beginner",
      "needs_review": true
    }
  ]
}
```

Once JSON files are in `data/datasets/`, run:
```
python scripts/ingest_dataset.py
```

---

## Recommended Order of Work

1. `UG_Luganda_Language_Lessons.pdf` — quick win, clean pairs, do first
2. `FSI Luganda Basic Course` — more complex, higher volume
3. `Luganda Bible` — highest volume, most effort, do when ready for fine-tuning data
4. `A_Handbook_of_Luganda.pdf` — only if re-OCR works cleanly

---

## Dependencies to Install

```bash
pip install pdfplumber --break-system-packages       # already installed
pip install pytesseract --break-system-packages      # for Handbook re-OCR only
# Also install Tesseract binary from https://github.com/UB-Mannheim/tesseract/wiki
```

---

## When to Start This

Start this work when:
- [ ] NLLB-200 is integrated (training-plan Phase 2 complete)
- [ ] Feedback API endpoint is live (project Phase 2 complete)
- [ ] You have time to review extracted pairs manually before ingesting

Do NOT ingest extracted PDF pairs without a spot-check of at least 50 entries.
PDF extraction is never 100% clean.
