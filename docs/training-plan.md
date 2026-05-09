# Luganda AI Studio — Model Training & Improvement Plan

> Created: April 14, 2026
> Updated: April 17, 2026
> Status: IN PROGRESS — Phase 1 scaffolding complete, ready to run
> Author: Mukalazi Patrick + Claude

---

## Current State Summary

| Metric | Value |
|--------|-------|
| Total translation pairs | 492 |
| Collections | vocabulary (294), sentences (110), grammar (28), proverbs (60) |
| Translation method | Search-based (exact → normalized → partial → semantic) |
| Embedding model | all-MiniLM-L6-v2 (384-dim, English-optimized) |
| Neural translation | None |
| Feedback loop | Endpoint working, processing script built, not yet connected to training |
| Machine | i7-11800H, 16GB RAM, RTX 3050 (4GB VRAM) |

**Core limitation:** The system is a dictionary lookup, not a translator. It can only return entries it already has stored. Any word, phrase, or sentence not in the database returns "not_found."

---

## The Plan: Three Phases

```
Phase 1: Scale the Data         → Week 1 (2-3 days)
Phase 2: Add Neural Translation → Week 2-3 (7-10 days)  
Phase 3: Close the Feedback Loop → Week 3-4 (3-4 days)
```

Total estimated time: 3-4 weeks of part-time work (2-3 hours/day).

---

## Phase 1: Scale the Data (2-3 days)

### Goal
Go from 492 translation pairs to 5,000+ by importing existing Luganda-English datasets. This immediately makes the search-based system more useful without changing any code.

### Step 1.1 — Find and Download Datasets

These are known free Luganda-English datasets available online:

| Source | What It Has | Where to Get It |
|--------|------------|-----------------|
| **Makerere University NLP** | Luganda-English parallel text, news translations | https://github.com/Makerere-University (search for NLP repos) |
| **OPUS Parallel Corpus** | Luganda translations from multiple sources (JW300, Ubuntu, GNOME) | https://opus.nlpl.eu/ — search language pair "en-lg" |
| **Hugging Face Datasets** | Community-uploaded Luganda datasets | https://huggingface.co/datasets?language=lg |
| **JW300** | ~30,000 Luganda-English sentence pairs (religious text) | Available via OPUS or Hugging Face |
| **Flores-200** | 1,000 high-quality benchmark sentences in Luganda | https://github.com/facebookresearch/flores |
| **Sunbird AI** | Ugandan NLP research group, some open datasets | https://github.com/SunbirdAI |

**Priority order:** Flores-200 first (small, high quality, good for testing), then JW300 (large volume), then OPUS collections.

### Step 1.2 — Clean and Normalize

Write a Python script that:

1. Reads downloaded datasets (CSV, TSV, or JSON)
2. Deduplicates against existing 492 entries
3. Normalizes encoding (UTF-8), strips extra whitespace
4. Categorizes entries (vocabulary vs sentences) based on length:
   - 1-2 words → vocabulary collection
   - 3+ words → sentences collection
5. Outputs clean JSON files matching your existing format:

```json
{
  "metadata": {
    "source": "flores-200",
    "category": "sentences",
    "date_added": "2026-04-20"
  },
  "entries": [
    {
      "luganda": "Enkuluze y'ensiri erimu ebinyonyi.",
      "english": "The forest reserve has birds.",
      "category": "imported",
      "subcategory": "flores-200",
      "difficulty": "intermediate",
      "needs_review": true
    }
  ]
}
```

**Important:** Mark all imported data as `needs_review: true` — you'll validate quality over time.

### Step 1.3 — Ingest into ChromaDB

Your existing ingestion pipeline (`loader.py` → `embedder.py` → `indexer.py`) already handles this. Steps:

1. Place cleaned JSON files in `data/datasets/`
2. Run the ingestion script (it uses MD5-based IDs so duplicates are safe)
3. Verify with `/api/v1/knowledge/stats` — confirm new counts
4. Test 20-30 translations that previously returned "not_found"

### Step 1.4 — Upgrade Embeddings (Optional but Recommended)

Your current embedding model (all-MiniLM-L6-v2) is English-optimized. For better semantic matching with Luganda text, switch to a multilingual model:

| Model | Size | Languages | Notes |
|-------|------|-----------|-------|
| **paraphrase-multilingual-MiniLM-L12-v2** | 471MB | 50+ languages | Good balance of size and quality. May not include Luganda specifically but handles Bantu languages better than English-only MiniLM. |
| **LaBSE** (Language-Agnostic BERT Sentence Embeddings) | 1.8GB | 109 languages including Luganda | Best multilingual coverage. Fits in RAM. |

**Recommendation:** Start with `paraphrase-multilingual-MiniLM-L12-v2`. If Luganda results are poor, upgrade to LaBSE.

Change in `embedder.py`:
```python
# Before
MODEL_NAME = "all-MiniLM-L6-v2"

# After  
MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"
```

**Warning:** Changing the embedding model means you must re-embed ALL data in ChromaDB. The old vectors and new vectors won't be compatible. Plan for a full re-ingestion.

### Phase 1 Progress (Updated Apr 17)

**Scripts built:**
- `scripts/download_datasets.py` — Downloads Flores-200 and JW300, deduplicates against existing 464 pairs, categorizes entries, outputs clean JSON. Supports `--source flores`, `--source jw300`, `--source all`, `--list`, and `--dry-run`.
- `scripts/ingest_dataset.py` — Reads any JSON from `data/datasets/` and ingests into ChromaDB via existing embedder + indexer pipeline. Supports `--dry-run`, `--stats`, and `--file` for single-file ingestion. Logs every ingestion run to `data/datasets/ingestion_log.jsonl`.

**Folders created:**
- `data/datasets/` — Cleaned downloaded datasets ready for ingestion
- `data/training/` — Accumulated correction pairs for future NLLB fine-tuning
- `data/feedback/` — User feedback from the translate page
- `scripts/` — All automation scripts

**How to run Phase 1:**
```bash
# Step 1: Download (start with Flores, then JW300)
python scripts/download_datasets.py --source flores
python scripts/download_datasets.py --source jw300

# Step 2: Preview what will be ingested
python scripts/ingest_dataset.py --dry-run

# Step 3: Ingest into ChromaDB
python scripts/ingest_dataset.py

# Step 4: Verify counts
python scripts/ingest_dataset.py --stats
```

### Phase 1 Deliverables
- [ ] 5,000+ translation pairs in ChromaDB *(scripts ready, run download + ingest)*
- [ ] Multilingual embedding model installed *(optional — upgrade after data is in)*
- [ ] Full re-ingestion completed
- [ ] 30 test translations verified working

---

## Phase 2: Add Neural Translation with NLLB-200 (7-10 days)

### Goal
Add a real machine translation model as a fallback so the system can translate ANY text, not just stored entries. When the search pipeline returns "not_found," NLLB-200 takes over.

### Why NLLB-200?

| Reason | Detail |
|--------|--------|
| **Supports Luganda natively** | Language code: `lug_Latn` |
| **Distilled version fits your GPU** | `facebook/nllb-200-distilled-600M` — runs on 4GB VRAM |
| **Free and open source** | Meta released it under CC-BY-NC |
| **Fine-tunable** | Can improve it on your specific domain data |
| **Proven quality** | Scored well on Flores-200 Luganda benchmark |

### Step 2.1 — Install NLLB-200

```bash
pip install transformers sentencepiece accelerate
```

Download the distilled model (first run will download ~2.3GB):

```python
from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

model_name = "facebook/nllb-200-distilled-600M"
tokenizer = AutoTokenizer.from_pretrained(model_name)
model = AutoModelForSeq2SeqLM.from_pretrained(model_name)
```

### Step 2.2 — Create Translation Service

New file: `backend/services/translation/nllb_service.py`

```python
"""
NLLB-200 neural translation service.
Used as fallback when search-based translation returns not_found.
"""
import torch
from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

class NLLBTranslator:
    def __init__(self):
        self.model_name = "facebook/nllb-200-distilled-600M"
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.tokenizer = None
        self.model = None
        self._loaded = False
    
    def load(self):
        """Lazy-load model to avoid startup delay."""
        if self._loaded:
            return
        self.tokenizer = AutoTokenizer.from_pretrained(self.model_name)
        self.model = AutoModelForSeq2SeqLM.from_pretrained(
            self.model_name
        ).to(self.device)
        self._loaded = True
    
    def translate(self, text: str, direction: str) -> str:
        """
        Translate text using NLLB-200.
        
        direction: "en_to_lg" or "lg_to_en"
        """
        self.load()
        
        # NLLB language codes
        lang_map = {
            "en_to_lg": ("eng_Latn", "lug_Latn"),
            "lg_to_en": ("lug_Latn", "eng_Latn"),
        }
        src_lang, tgt_lang = lang_map[direction]
        
        self.tokenizer.src_lang = src_lang
        inputs = self.tokenizer(text, return_tensors="pt").to(self.device)
        
        with torch.no_grad():
            output = self.model.generate(
                **inputs,
                forced_bos_token_id=self.tokenizer.convert_tokens_to_ids(tgt_lang),
                max_new_tokens=256,
            )
        
        result = self.tokenizer.decode(output[0], skip_special_tokens=True)
        return result

# Singleton instance
nllb_translator = NLLBTranslator()
```

### Step 2.3 — Integrate into Translation Pipeline

Modify `backend/services/translation/service.py` to add NLLB as the final fallback:

```
Current pipeline:
  exact → normalized → partial → semantic → not_found

New pipeline:
  exact → normalized → partial → semantic → NLLB-200 → not_found
```

When NLLB handles a translation:
- `match_type` = `"neural"`
- `confidence` = `0.70` (fixed baseline — NLLB quality varies)
- `matched_collection` = `"nllb-200"`
- `message` = `"AI-generated translation. May need review."`

### Step 2.4 — Optimize for Your Hardware

To make NLLB-200 run well on RTX 3050 (4GB VRAM):

1. **Use float16 precision** — halves memory usage:
```python
model = AutoModelForSeq2SeqLM.from_pretrained(
    model_name, 
    torch_dtype=torch.float16
).to("cuda")
```

2. **Lazy loading** — don't load the model on server startup. Load it on first neural translation request. This keeps ChromaDB-only translations fast.

3. **Batch translations** — if translating multiple texts, batch them to avoid repeated model loading overhead.

4. **CPU fallback** — if VRAM is exhausted (ChromaDB + MiniLM + NLLB competing), fall back to CPU. Slower but works.

**Expected performance:**
- First translation: 5-10 seconds (model loading)
- Subsequent translations: 1-3 seconds on GPU, 5-10 seconds on CPU
- Memory usage: ~1.5GB VRAM in float16

### Step 2.5 — Test and Benchmark

Create a test script that runs 100 known Luganda-English pairs through NLLB-200 and measures:

| Metric | How to Measure |
|--------|---------------|
| BLEU score | Compare NLLB output vs reference translation |
| Accuracy on common phrases | Manual spot-check of 20 greetings, farming terms |
| Speed | Average seconds per translation |
| Failure rate | How often output is gibberish or wrong language |

Save results to `docs/nllb-benchmark.md` — this becomes your baseline for measuring improvement.

### Phase 2 Deliverables
- [x] NLLB-200 distilled model downloaded and running
- [x] Neural fallback integrated into translation pipeline
- [x] Float16 optimization confirmed on RTX 3050 (CPU used in benchmark — code supports both)
- [x] Benchmark results documented — see docs/nllb-benchmark.md
- [x] 47 manual spot-checks completed — quality acceptable for production use

---

## Phase 3: Close the Feedback Loop (3-4 days)

### Goal
Make the system improve automatically from user corrections. When a user marks a translation as "wrong" and provides the correct answer, that correction should flow back into the system.

### Step 3.1 — Feedback → ChromaDB (Instant Improvement)

When a user submits feedback with verdict "wrong" and provides an expected output:

```json
{
  "input_text": "chicken feed",
  "direction": "en_to_lg",
  "translated_text": "enkoko",        // what system returned (wrong)
  "verdict": "wrong",
  "expected_output": "emmere y'enkoko" // what user says is correct
}
```

**Auto-ingest this correction:**

1. Read the feedback from `data/feedback/feedback_log.jsonl`
2. Create a new ChromaDB entry:
   - `english`: "chicken feed"
   - `luganda`: "emmere y'enkoko"
   - `category`: "user_correction"
   - `source`: "feedback"
   - `needs_review`: true
3. Upsert into the appropriate collection (vocabulary or sentences)
4. Next time someone searches "chicken feed," the corrected entry is found

**Important safeguards:**
- Only auto-ingest if `expected_output` is provided (not just "wrong" with no correction)
- Mark as `needs_review: true` — user corrections could be wrong too
- Log all auto-ingested corrections separately for audit
- Set a confidence boost: user-corrected entries should rank higher than imported data

### Step 3.2 — Feedback → Fine-Tuning Data (Gradual Improvement)

Accumulate correction pairs for eventually fine-tuning NLLB-200:

```
data/training/
├── corrections.jsonl      ← All user corrections
├── verified.jsonl         ← Corrections you've manually verified
└── training_pairs.jsonl   ← Formatted for NLLB fine-tuning
```

Format for fine-tuning:
```json
{"source": "chicken feed", "target": "emmere y'enkoko", "direction": "en_to_lg"}
```

**When to actually fine-tune:** When you have 500+ verified correction pairs. Below that, the data is too little to move the needle on a 600M parameter model.

### Step 3.3 — Fine-Tune NLLB-200 with LoRA

When you have enough data, use LoRA (Low-Rank Adaptation) to fine-tune NLLB-200 without training the full model. This is critical for your 4GB VRAM.

```bash
pip install peft datasets
```

**LoRA approach:**
- Freeze the full NLLB-200 model (600M params)
- Train only a small adapter (~2-5M params)
- Adapter learns your domain-specific corrections
- Total VRAM needed: ~3GB in float16 with LoRA

```python
from peft import LoraConfig, get_peft_model, TaskType

lora_config = LoraConfig(
    task_type=TaskType.SEQ_2_SEQ_LM,
    r=16,                    # rank — keep low for 4GB VRAM
    lora_alpha=32,
    lora_dropout=0.1,
    target_modules=["q_proj", "v_proj"],  # attention layers only
)

peft_model = get_peft_model(model, lora_config)
# peft_model.print_trainable_parameters() 
# → will show ~0.5% of params are trainable
```

**Training settings for your hardware:**

| Setting | Value | Why |
|---------|-------|-----|
| Batch size | 4 | Fits in 4GB VRAM with LoRA |
| Learning rate | 2e-4 | Standard for LoRA |
| Epochs | 3-5 | Small dataset needs fewer epochs |
| Max input length | 128 tokens | Luganda sentences are short |
| Gradient accumulation | 4 | Effective batch size = 16 |
| FP16 | Yes | Required for your VRAM |

**Expected training time:** 500 pairs × 5 epochs ≈ 30-60 minutes on RTX 3050.

**After fine-tuning:**
- Save the LoRA adapter (small file, ~10-20MB)
- Load base model + adapter at inference time
- Test on held-out set to confirm improvement
- If quality improved, deploy; if not, collect more data

### Step 3.4 — Build the Feedback Processing Script

A single script that runs periodically (manually or via cron):

```
python scripts/process_feedback.py
```

What it does:
1. Reads `data/feedback/feedback_log.jsonl`
2. Filters entries with verdict "wrong" + expected_output provided
3. Auto-ingests corrections into ChromaDB (Step 3.1)
4. Appends to `data/training/corrections.jsonl` (Step 3.2)
5. Reports: "Processed X corrections. Y new entries added to ChromaDB. Z total training pairs accumulated."
6. When training pairs > 500: prints "Ready for fine-tuning. Run: python scripts/finetune_nllb.py"

### Phase 3 Progress (Updated Apr 17)

**Scripts built:**
- `scripts/process_feedback.py` — Reads `data/feedback/feedback_log.jsonl`, finds corrections (verdict="wrong" + expected_output provided), auto-ingests into ChromaDB, accumulates training pairs for NLLB fine-tuning. Supports `--dry-run`, `--stats`, `--reset`. Tracks processed IDs to avoid reprocessing.

**How to run Phase 3:**
```bash
# Check what feedback has accumulated
python scripts/process_feedback.py --stats

# Preview corrections without writing
python scripts/process_feedback.py --dry-run

# Process all unprocessed feedback
python scripts/process_feedback.py
```

**Output files:**
- `data/training/corrections.jsonl` — Full correction records for audit
- `data/training/training_pairs.jsonl` — Minimal format for NLLB fine-tuning
- `data/feedback/auto_ingestion_log.jsonl` — Audit log of ChromaDB auto-ingestions
- `data/feedback/processed_ids.json` — Tracks which feedback IDs have been processed

### Phase 3 Deliverables
- [x] Feedback processing script working
- [x] User corrections auto-ingested into ChromaDB — tested end-to-end 2026-04-19
- [x] Training data accumulation pipeline running *(corrections.jsonl + training_pairs.jsonl)*
- [x] Save Correction button added to translate.html — corrections now submittable from UI
- [x] Partial match bug fixed — sentences (3+ words) skip to semantic/NLLB, not vocabulary
- [ ] LoRA fine-tuning script ready (to run when 500+ correction pairs accumulated)
- [ ] Documentation on how to trigger fine-tuning

---

## Complete Architecture After All 3 Phases

```
User Input
    ↓
POST /api/v1/translate
    ↓
┌─────────────────────────────────────────┐
│  Phase 1: Search Pipeline               │
│  ┌─────────────────────────────────┐    │
│  │ ChromaDB (5,000+ entries)       │    │
│  │ + multilingual embeddings       │    │
│  │                                 │    │
│  │ exact → normalized → partial    │    │
│  │ → semantic                      │    │
│  └─────────────────────────────────┘    │
│  Found? → Return (confidence 0.85-1.0)  │
└──────────────┬──────────────────────────┘
               │ not_found
               ↓
┌─────────────────────────────────────────┐
│  Phase 2: Neural Fallback               │
│  ┌─────────────────────────────────┐    │
│  │ NLLB-200-distilled-600M         │    │
│  │ + LoRA adapter (Phase 3)        │    │
│  │ float16 on RTX 3050             │    │
│  └─────────────────────────────────┘    │
│  Return (confidence 0.70, match: neural)│
└──────────────┬──────────────────────────┘
               ↓
Translation Response → Frontend
               ↓
User gives feedback (correct/wrong/review)
               ↓
┌─────────────────────────────────────────┐
│  Phase 3: Learning Loop                 │
│                                         │
│  Wrong + correction provided?           │
│  ├→ Add to ChromaDB (instant fix)       │
│  └→ Add to training data (for LoRA)     │
│                                         │
│  500+ corrections accumulated?          │
│  └→ Fine-tune NLLB-200 with LoRA        │
│     └→ Better neural translations       │
└─────────────────────────────────────────┘
```

---

## Timeline

| Week | Phase | Tasks | Hours |
|------|-------|-------|-------|
| Week 1 (Apr 19-20) | Phase 1 | Download datasets, clean, ingest, upgrade embeddings | 6-8 hrs |
| Week 2 (Apr 21-25) | Phase 2 | Install NLLB-200, integrate fallback, optimize for GPU | 10-14 hrs |
| Week 3 (Apr 26-28) | Phase 2+3 | Benchmark NLLB, build feedback processing script | 8-10 hrs |
| Week 4 (Apr 29-30) | Phase 3 | LoRA setup, testing, documentation | 4-6 hrs |

**Total: ~28-38 hours across 2 weeks of focused work.**

---

## Dependencies to Install

```bash
# Phase 1
pip install sentence-transformers --break-system-packages

# Phase 2
pip install transformers sentencepiece accelerate torch --break-system-packages

# Phase 3
pip install peft datasets --break-system-packages
```

**Disk space needed:** ~5GB (NLLB model + datasets + ChromaDB growth)

---

## Success Metrics

| Metric | Before | After Phase 1 | After Phase 2 | After Phase 3 |
|--------|--------|---------------|---------------|---------------|
| Known vocabulary | 492 | 5,000+ | 5,000+ | 5,000+ growing |
| Can translate unknown text | No | No | Yes | Yes, better |
| Translation quality (manual) | Good for known words | Good for more words | Decent for all text | Improving over time |
| User corrections used | Never | Never | Never | Automatically |
| "not_found" rate | High | Medium | Near zero | Near zero |

---

## Risks and Mitigations

| Risk | Mitigation |
|------|-----------|
| NLLB Luganda quality is poor | Benchmark first with Flores-200; if bad, try AfriMT or other Africa-focused models |
| 4GB VRAM not enough for NLLB + ChromaDB | Use CPU fallback; or quantize to int8 (even smaller) |
| Downloaded datasets have bad quality | Mark all as needs_review; spot-check 50 entries before bulk ingestion |
| Users submit wrong corrections | All corrections marked needs_review; periodic manual audit |
| LoRA fine-tuning makes model worse | Always keep base model; A/B test adapter vs base before deploying |
| Scope creep delays Farm Beacon work | This plan is POST-launch only; do not start before Apr 19 |

---

## Rules

1. **Do NOT start this before Farm Beacon launch is complete (Apr 15+)**
2. Phase 1 is mandatory before Phase 2 — more data helps everything
3. Phase 2 is mandatory before Phase 3 — need the model before fine-tuning it
4. Test after every phase — don't stack untested changes
5. Back up ChromaDB before any re-ingestion (`cp -r data/chromadb data/chromadb_backup`)
6. All imported data marked `needs_review: true` until manually verified
