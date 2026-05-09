# scripts/benchmark_nllb.py

"""
Phase 2 Benchmark — NLLB-200 Spot-Check & Performance Test
============================================================

Runs 50 known Luganda-English pairs through NLLB-200 and measures:
  - Translation speed (first call + subsequent calls)
  - Output quality vs known correct answer (manual review)
  - Failure rate (gibberish / wrong language / crash)

Results are written to: docs/nllb-benchmark.md

Usage (from project root, inside venv):
    python scripts/benchmark_nllb.py

What happens on first run:
  - NLLB-200 model (~2.3 GB) is downloaded from HuggingFace automatically
  - Stored in your HuggingFace cache (~/.cache/huggingface)
  - Subsequent runs skip the download

Expected time on RTX 3050:
  - Model download: 5-15 minutes (first time only)
  - Model load: 5-10 seconds
  - 50 translations: ~2-5 minutes total
"""

import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

# ------------------------------------------------------------------ #
# Paths
# ------------------------------------------------------------------ #

ROOT = Path(__file__).resolve().parent.parent
DOCS_DIR = ROOT / "docs"
DOCS_DIR.mkdir(exist_ok=True)
OUTPUT_FILE = DOCS_DIR / "nllb-benchmark.md"

# ------------------------------------------------------------------ #
# Test pairs — pulled from hand-curated verified datasets
# Mix of: vocabulary, greetings, daily life sentences
# Both directions tested
# ------------------------------------------------------------------ #

TEST_PAIRS_EN_TO_LG = [
    # Greetings / Social
    ("How are you?", "Oli otya?"),
    ("Good morning", "Wasuze otya"),
    ("Thank you", "Webale"),
    ("Welcome", "Tukusanyukidde / Kalibu"),
    ("I am fine", "Ndiwamu bulungi"),
    ("How are you all?", "Muliyo mutyanno"),
    ("We are happy to see you.", "Tusanyuse okukulaba."),

    # Animals
    ("Dog", "Embwa"),
    ("Goat", "Embuzi"),
    ("Chicken", "Enkoko"),
    ("Cow", "Ente"),
    ("Cat", "Ppaka"),

    # Food & Drink
    ("Water", "Amazzi"),
    ("Food", "Emmere"),
    ("Banana", "Amatooke"),
    ("Rice", "Omuchere"),
    ("Salt", "Omunnyo"),
    ("Milk", "Amata"),

    # Body Parts
    ("Head", "Omutwe"),
    ("Hand", "Mukono"),
    ("Eye", "Eriiso"),
    ("Ear", "Okutu"),
    ("Nose", "Ennyindo"),

    # Daily Life Sentences
    ("I go to work every day.", "Ngenda ku mulimu buli lunaku."),
    ("My son goes to school every day.", "Mutabani wange asoma buli lunaku."),
    ("In the morning we drink tea.", "Ku makya tunywa chai."),
    ("I work in the agriculture department.", "Nkola mu kitongole ky'obulimi."),
]

TEST_PAIRS_LG_TO_EN = [
    # Greetings
    ("Oli otya?", "How are you?"),
    ("Wasuze otya", "Good morning"),
    ("Webale", "Thank you"),
    ("Kalibu", "Welcome"),
    ("Ndiwamu bulungi", "I am fine / I am well"),

    # Animals
    ("Embwa", "Dog"),
    ("Embuzi", "Goat"),
    ("Enkoko", "Chicken"),
    ("Ente", "Cow"),

    # Food & Drink
    ("Amazzi", "Water"),
    ("Emmere", "Food"),
    ("Amatooke", "Cooking bananas / Matoke"),
    ("Amata", "Milk"),

    # Body Parts
    ("Omutwe", "Head"),
    ("Mukono", "Hand"),
    ("Eriiso", "Eye"),

    # Daily Life
    ("Ngenda ku mulimu buli lunaku.", "I go to work every day."),
    ("Mutabani wange asoma buli lunaku.", "My son goes to school every day."),
    ("Nkola mu kitongole ky'obulimi.", "I work in the agriculture department."),
    ("Ku makya tunywa chai.", "In the morning we drink tea."),
]


# ------------------------------------------------------------------ #
# Load NLLB
# ------------------------------------------------------------------ #

def load_nllb():
    """Load NLLB-200-distilled-600M. Downloads on first call (~2.3 GB)."""
    print("\n[1/3] Loading NLLB-200 model...")
    print("      If this is your first run, it will download ~2.3 GB.")
    print("      This may take 5-15 minutes on first run.\n")

    import torch
    from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

    model_name = "facebook/nllb-200-distilled-600M"
    device = "cuda" if torch.cuda.is_available() else "cpu"
    dtype = torch.float16 if device == "cuda" else torch.float32

    print(f"      Device: {device.upper()}")
    if device == "cuda":
        import torch
        props = torch.cuda.get_device_properties(0)
        vram_gb = props.total_memory / (1024 ** 3)
        print(f"      GPU: {props.name} ({vram_gb:.1f} GB VRAM)")
        print(f"      Precision: float16 (VRAM-saving mode)")
    else:
        print("      Precision: float32 (CPU mode — slower)")

    t0 = time.time()
    tokenizer = AutoTokenizer.from_pretrained(model_name)
    model = AutoModelForSeq2SeqLM.from_pretrained(model_name, torch_dtype=dtype).to(device)
    model.eval()
    load_time = time.time() - t0

    print(f"\n      Model loaded in {load_time:.1f}s\n")
    return tokenizer, model, device


# ------------------------------------------------------------------ #
# Single translation
# ------------------------------------------------------------------ #

def translate_one(tokenizer, model, device, text: str, direction: str) -> tuple[str, float]:
    """
    Translate one text. Returns (translated_text, seconds_taken).
    """
    import torch

    lang_map = {
        "en_to_lg": ("eng_Latn", "lug_Latn"),
        "lg_to_en": ("lug_Latn", "eng_Latn"),
    }
    src_lang, tgt_lang = lang_map[direction]

    tokenizer.src_lang = src_lang
    inputs = tokenizer(
        text,
        return_tensors="pt",
        padding=True,
        truncation=True,
        max_length=256,
    ).to(device)

    forced_bos = tokenizer.convert_tokens_to_ids(tgt_lang)

    t0 = time.time()
    with torch.no_grad():
        output_ids = model.generate(
            **inputs,
            forced_bos_token_id=forced_bos,
            max_new_tokens=256,
            num_beams=4,
            early_stopping=True,
        )
    elapsed = time.time() - t0

    result = tokenizer.decode(output_ids[0], skip_special_tokens=True).strip()
    return result, elapsed


# ------------------------------------------------------------------ #
# Run benchmark
# ------------------------------------------------------------------ #

def run_benchmark(tokenizer, model, device) -> dict:
    """Run all test pairs and collect results."""

    results = {
        "en_to_lg": [],
        "lg_to_en": [],
        "metadata": {
            "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "device": device,
            "model": "facebook/nllb-200-distilled-600M",
        }
    }

    all_pairs = [
        ("en_to_lg", TEST_PAIRS_EN_TO_LG),
        ("lg_to_en", TEST_PAIRS_LG_TO_EN),
    ]

    total = sum(len(pairs) for _, pairs in all_pairs)
    done = 0

    print(f"[2/3] Running {total} translations...\n")

    for direction, pairs in all_pairs:
        label = "English → Luganda" if direction == "en_to_lg" else "Luganda → English"
        print(f"  --- {label} ---")

        for input_text, expected in pairs:
            done += 1
            try:
                output, elapsed = translate_one(tokenizer, model, device, input_text, direction)
                status = "ok"
            except Exception as e:
                output = f"[ERROR: {e}]"
                elapsed = 0.0
                status = "error"

            results[direction].append({
                "input": input_text,
                "expected": expected,
                "nllb_output": output,
                "time_s": round(elapsed, 2),
                "status": status,
            })

            marker = "✓" if status == "ok" else "✗"
            print(f"  [{done:02d}/{total}] {marker} ({elapsed:.1f}s) {input_text!r}")
            print(f"         Expected: {expected}")
            print(f"         NLLB:     {output}\n")

    return results


# ------------------------------------------------------------------ #
# Write Markdown report
# ------------------------------------------------------------------ #

def write_report(results: dict) -> None:
    """Write benchmark results to docs/nllb-benchmark.md."""

    meta = results["metadata"]
    en_to_lg = results["en_to_lg"]
    lg_to_en = results["lg_to_en"]
    all_rows = en_to_lg + lg_to_en

    ok_rows = [r for r in all_rows if r["status"] == "ok"]
    error_rows = [r for r in all_rows if r["status"] == "error"]
    times = [r["time_s"] for r in ok_rows if r["time_s"] > 0]

    avg_time = sum(times) / len(times) if times else 0
    min_time = min(times) if times else 0
    max_time = max(times) if times else 0
    failure_rate = len(error_rows) / len(all_rows) * 100 if all_rows else 0

    lines = [
        "# NLLB-200 Benchmark Results",
        "",
        f"> Run date: {meta['date']}  ",
        f"> Device: {meta['device'].upper()}  ",
        f"> Model: `{meta['model']}`  ",
        f"> Status: Phase 2 baseline — results require manual quality review",
        "",
        "---",
        "",
        "## Summary",
        "",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Total pairs tested | {len(all_rows)} |",
        f"| Errors / crashes | {len(error_rows)} ({failure_rate:.1f}%) |",
        f"| Avg translation time | {avg_time:.2f}s |",
        f"| Min translation time | {min_time:.2f}s |",
        f"| Max translation time | {max_time:.2f}s |",
        f"| Manual quality review | ⬜ Pending — see table below |",
        "",
        "> **Quality scoring key (fill in manually):**  ",
        "> ✅ Correct — meaning preserved  ",
        "> 🟡 Close — roughly right but phrasing differs  ",
        "> ❌ Wrong — wrong meaning, wrong language, or gibberish  ",
        "",
        "---",
        "",
        "## English → Luganda",
        "",
        "| # | Input (English) | Expected | NLLB Output | Time | Quality |",
        "|---|-----------------|----------|-------------|------|---------|",
    ]

    for i, row in enumerate(en_to_lg, 1):
        lines.append(
            f"| {i} | {row['input']} | {row['expected']} | {row['nllb_output']} "
            f"| {row['time_s']}s | ⬜ |"
        )

    lines += [
        "",
        "---",
        "",
        "## Luganda → English",
        "",
        "| # | Input (Luganda) | Expected | NLLB Output | Time | Quality |",
        "|---|-----------------|----------|-------------|------|---------|",
    ]

    for i, row in enumerate(lg_to_en, 1):
        lines.append(
            f"| {i} | {row['input']} | {row['expected']} | {row['nllb_output']} "
            f"| {row['time_s']}s | ⬜ |"
        )

    lines += [
        "",
        "---",
        "",
        "## Manual Quality Review",
        "",
        "After running this script, go through the tables above and fill in the Quality column:",
        "",
        "- ✅ for correct translations",
        "- 🟡 for close but not exact",
        "- ❌ for wrong / gibberish",
        "",
        "Once filled in, add a summary here:",
        "",
        "| Direction | ✅ Correct | 🟡 Close | ❌ Wrong | Notes |",
        "|-----------|-----------|---------|---------|-------|",
        "| EN → LG   | — | — | — | |",
        "| LG → EN   | — | — | — | |",
        "",
        "---",
        "",
        "## Hardware Observations",
        "",
        "Fill in after running:",
        "",
        "| Observation | Value |",
        "|-------------|-------|",
        "| VRAM used during inference | — |",
        "| RAM used during inference | — |",
        "| Any OOM errors? | — |",
        "| CPU fallback triggered? | — |",
        "| Overall: fit for Phase 3? | ⬜ Yes / No |",
        "",
        "---",
        "",
        "## Decision",
        "",
        "Based on results above:",
        "",
        "- [ ] Quality is acceptable — proceed to Phase 3",
        "- [ ] Quality is poor — investigate alternative models before Phase 3",
        "- [ ] Hardware issues — resolve VRAM/OOM before Phase 3",
    ]

    OUTPUT_FILE.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n[3/3] Report saved to: {OUTPUT_FILE}")


# ------------------------------------------------------------------ #
# Main
# ------------------------------------------------------------------ #

if __name__ == "__main__":
    print("=" * 60)
    print("  Luganda AI Studio — NLLB-200 Phase 2 Benchmark")
    print("=" * 60)

    try:
        tokenizer, model, device = load_nllb()
        results = run_benchmark(tokenizer, model, device)
        write_report(results)

        print("\n" + "=" * 60)
        print("  BENCHMARK COMPLETE")
        print("=" * 60)
        print(f"\n  Results saved to: docs/nllb-benchmark.md")
        print("\n  Next step:")
        print("  Open docs/nllb-benchmark.md and fill in the")
        print("  Quality column (✅ / 🟡 / ❌) for each row.")
        print("  Then confirm Phase 2 is complete before Phase 3.\n")

    except KeyboardInterrupt:
        print("\n\nBenchmark cancelled.")
        sys.exit(0)
    except Exception as e:
        print(f"\n[ERROR] Benchmark failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
