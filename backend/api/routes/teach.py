# backend/api/routes/teach.py

"""
Teaching Mode API
==================

Provides two modes of learning:

  1. FLASH CARD MODE
     GET /api/v1/teach/cards
     Returns a batch of Luganda/English card pairs.
     User flips the card and self-rates: Got It / Try Again.

  2. QUIZ MODE
     GET /api/v1/teach/quiz
     Returns one question at a time with 4 multiple choice options.
     One option is correct, three are random distractors from ChromaDB.
     POST /api/v1/teach/quiz/answer
     Submit an answer and get back correct/wrong + the right answer.

  3. PROGRESS
     GET  /api/v1/teach/progress   — get current session stats
     POST /api/v1/teach/progress   — save session results

DATA SOURCE:
  Uses your real ChromaDB vocabulary collection via get_chroma_client().
  Falls back to a small built-in starter set if ChromaDB has no data.

COLLECTIONS USED:
  vocabulary — primary source for quiz cards
  sentences  — optional, for sentence-level cards later
"""

import json
import logging
import random
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from backend.db.chroma_client import get_chroma_client

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Teaching Mode"])  # CHANGED: removed prefix="/teach" — main.py already sets prefix="/api/v1/teach"

# ── Progress file location ─────────────────────────────────────────────────────
# Stored in data/progress/progress.json relative to project root
PROJECT_ROOT   = Path(__file__).resolve().parents[3]
PROGRESS_DIR   = PROJECT_ROOT / "data" / "progress"
PROGRESS_FILE  = PROGRESS_DIR / "progress.json"

# ── How many cards to fetch from ChromaDB per request ─────────────────────────
CHROMA_FETCH_LIMIT = 200


# ── Response Models ────────────────────────────────────────────────────────────

class FlashCard(BaseModel):
    id:      str
    luganda: str
    english: str
    type:    str = "vocabulary"
    notes:   str = ""


class CardsResponse(BaseModel):
    cards:       list[FlashCard]
    total:       int
    source:      str = "chromadb"   # "chromadb" or "fallback"
    filtered_by: Optional[str] = None


class QuizOption(BaseModel):
    id:   str    # "A", "B", "C", "D"
    text: str    # The answer text shown to the user


class QuizQuestion(BaseModel):
    question_id:  str          # Stable ID for this question (luganda word hash)
    luganda:      str          # The Luganda word being tested
    question:     str          # The full question text e.g. "What does 'Embwa' mean?"
    options:      list[QuizOption]
    correct_id:   str          # Which option ID is correct ("A", "B", "C", or "D")
    notes:        str = ""     # Extra context shown after answering
    source_type:  str = "vocabulary"


class AnswerRequest(BaseModel):
    question_id: str   # Must match QuizQuestion.question_id
    selected_id: str   # Which option the user picked ("A", "B", "C", "D")
    correct_id:  str   # The correct answer (sent from frontend)


class AnswerResponse(BaseModel):
    correct:      bool
    selected_id:  str
    correct_id:   str
    correct_text: str   # The correct answer text (shown if user was wrong)
    message:      str   # Encouraging message


class ProgressData(BaseModel):
    total_sessions:  int = 0
    total_cards_seen: int = 0
    total_correct:   int = 0
    total_wrong:     int = 0
    last_session:    Optional[str] = None   # ISO date string


class SaveProgressRequest(BaseModel):
    cards_seen: int
    correct:    int
    wrong:      int
    session_date: str   # ISO date string from frontend


# ── Fallback data ──────────────────────────────────────────────────────────────
# Used only if ChromaDB vocabulary collection is empty.

FALLBACK_CARDS = [
    {"id": "f001", "luganda": "Oli otya",      "english": "How are you?",          "type": "greeting",   "notes": "Very common casual greeting"},
    {"id": "f002", "luganda": "Bulungi",        "english": "Fine / Good",            "type": "greeting",   "notes": "Standard reply to 'Oli otya'"},
    {"id": "f003", "luganda": "Webale nyo",     "english": "Thank you very much",    "type": "greeting",   "notes": "'Webale' alone = 'thank you'"},
    {"id": "f004", "luganda": "Amazzi",         "english": "Water",                  "type": "vocabulary", "notes": ""},
    {"id": "f005", "luganda": "Emmere",         "english": "Food",                   "type": "vocabulary", "notes": "Food in general"},
    {"id": "f006", "luganda": "Ssebo",          "english": "Sir / Mr.",              "type": "vocabulary", "notes": "Respectful address for older man"},
    {"id": "f007", "luganda": "Nnyabo",         "english": "Madam / Mrs.",           "type": "vocabulary", "notes": "Respectful address for older woman"},
    {"id": "f008", "luganda": "Embwa",          "english": "Dog",                    "type": "vocabulary", "notes": ""},
    {"id": "f009", "luganda": "Embuzi",         "english": "Goat",                   "type": "vocabulary", "notes": ""},
    {"id": "f010", "luganda": "Enkoko",         "english": "Hen / Chicken",          "type": "vocabulary", "notes": ""},
    {"id": "f011", "luganda": "Enjovu",         "english": "Elephant",               "type": "vocabulary", "notes": ""},
    {"id": "f012", "luganda": "Empologoma",     "english": "Lion",                   "type": "vocabulary", "notes": ""},
    {"id": "f013", "luganda": "Erinnya lyange", "english": "My name is",             "type": "phrase",     "notes": "Follow with your name"},
    {"id": "f014", "luganda": "Nkwagala",       "english": "I love you",             "type": "phrase",     "notes": "Used between family and close friends"},
    {"id": "f015", "luganda": "Mu kitiibwa",    "english": "You are welcome",        "type": "phrase",     "notes": "Response to 'webale'"},
]


# ── ChromaDB data loader ───────────────────────────────────────────────────────

def _load_vocabulary_from_chroma(
    limit: int = CHROMA_FETCH_LIMIT,
    category: Optional[str] = None,
) -> tuple[list[dict], str]:
    """
    Load vocabulary entries from ChromaDB.

    Returns:
        (list of card dicts, source string)
        source is "chromadb" or "fallback"

    Each card dict has: id, luganda, english, type, notes
    """
    try:
        client     = get_chroma_client()
        collection = client.get_or_create_collection("vocabulary")
        count      = collection.count()

        if count == 0:
            logger.warning("Vocabulary collection is empty — using fallback cards")
            return FALLBACK_CARDS, "fallback"

        # Fetch up to limit records
        fetch_limit = min(limit, count)
        results     = collection.get(
            limit=fetch_limit,
            include=["metadatas", "documents"],
        )

        if not results or not results.get("ids"):
            return FALLBACK_CARDS, "fallback"

        cards = []
        ids       = results.get("ids", [])
        metadatas = results.get("metadatas", []) or []
        documents = results.get("documents", []) or []

        for i, entry_id in enumerate(ids):
            meta    = metadatas[i] if i < len(metadatas) and metadatas[i] else {}
            doc     = documents[i] if i < len(documents) else ""

            luganda = str(meta.get("luganda") or "").strip()
            english = str(meta.get("english") or "").strip()

            # Skip entries without both fields
            if not luganda or not english:
                continue

            # Apply category filter if requested
            if category:
                card_cat = str(meta.get("category") or meta.get("data_type") or "").lower()
                if category.lower() not in card_cat:
                    continue

            notes    = str(meta.get("notes") or meta.get("example_sentence_english") or "")
            card_type = str(meta.get("data_type") or meta.get("_collection") or "vocabulary")

            cards.append({
                "id":      entry_id,
                "luganda": luganda,
                "english": english,
                "type":    card_type,
                "notes":   notes,
            })

        if not cards:
            logger.warning("No usable cards extracted from ChromaDB — using fallback")
            return FALLBACK_CARDS, "fallback"

        logger.info(f"Loaded {len(cards)} vocabulary cards from ChromaDB")
        return cards, "chromadb"

    except Exception as e:
        logger.error(f"ChromaDB load failed: {e}", exc_info=True)
        return FALLBACK_CARDS, "fallback"


# ── Quiz generator ─────────────────────────────────────────────────────────────

def _generate_quiz_question(
    target_card: dict,
    all_cards: list[dict],
) -> QuizQuestion:
    """
    Generate a multiple choice question for one vocabulary card.

    Format:
      Question: "What does '[luganda word]' mean in English?"
      Options:  A, B, C, D — one correct, three random distractors

    The correct answer position is randomised so it is not always A.
    """
    correct_english = target_card["english"]
    luganda         = target_card["luganda"]

    # Build a pool of distractor answers (different from the correct one)
    distractors_pool = [
        c["english"] for c in all_cards
        if c["english"].strip().lower() != correct_english.strip().lower()
    ]

    # Pick 3 unique distractors
    distractors = random.sample(
        distractors_pool,
        min(3, len(distractors_pool))
    )

    # Pad with fallback if not enough distractors
    while len(distractors) < 3:
        distractors.append("(no translation available)")

    # Build 4 options and shuffle
    option_texts = [correct_english] + distractors[:3]
    random.shuffle(option_texts)

    labels  = ["A", "B", "C", "D"]
    options = [
        QuizOption(id=labels[i], text=option_texts[i])
        for i in range(4)
    ]

    # Find which label ended up with the correct answer
    correct_label = next(
        opt.id for opt in options
        if opt.text.strip().lower() == correct_english.strip().lower()
    )

    # Stable question ID based on the luganda word
    import hashlib
    question_id = hashlib.md5(luganda.encode()).hexdigest()[:12]

    return QuizQuestion(
        question_id  = question_id,
        luganda      = luganda,
        question     = f"What does \"{luganda}\" mean in English?",
        options      = options,
        correct_id   = correct_label,
        notes        = target_card.get("notes", ""),
        source_type  = target_card.get("type", "vocabulary"),
    )


# ── Progress helpers ───────────────────────────────────────────────────────────

def _load_progress() -> dict:
    """Load progress from JSON file. Returns empty progress if file missing."""
    try:
        if PROGRESS_FILE.exists():
            return json.loads(PROGRESS_FILE.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning(f"Could not read progress file: {e}")
    return {
        "total_sessions":   0,
        "total_cards_seen": 0,
        "total_correct":    0,
        "total_wrong":      0,
        "last_session":     None,
    }


def _save_progress(data: dict) -> None:
    """Save progress to JSON file. Creates directory if needed."""
    try:
        PROGRESS_DIR.mkdir(parents=True, exist_ok=True)
        PROGRESS_FILE.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception as e:
        logger.error(f"Could not save progress: {e}")


# ── Encouraging messages ───────────────────────────────────────────────────────

CORRECT_MESSAGES = [
    "Kirungi nnyo! (Very good!)",
    "Weebale! You got it!",
    "Nnyabo / Ssebo — excellent!",
    "Correct! Keep going!",
    "Ggwanga! (Well done!)",
]

WRONG_MESSAGES = [
    "Not quite — study this one.",
    "Close! Review and try again.",
    "Keep going — you'll get it!",
    "Almost there — check the answer.",
    "Don't worry — practice makes perfect!",
]


# ── Routes ─────────────────────────────────────────────────────────────────────

@router.get("/cards", response_model=CardsResponse)
def get_flash_cards(
    limit:    int            = Query(default=10, ge=1, le=50),
    type:     Optional[str] = Query(default=None, description="Filter by card type"),
    shuffle:  bool           = Query(default=True),
    category: Optional[str] = Query(default=None, description="Filter by category e.g. animals"),
):
    """
    Return a batch of Luganda flash cards for the teaching mode UI.
    Cards come from your real ChromaDB vocabulary collection.
    Falls back to built-in starter cards if ChromaDB is empty.
    """
    all_cards, source = _load_vocabulary_from_chroma(category=category)

    # Apply type filter if requested
    if type:
        filtered = [c for c in all_cards if c.get("type", "").lower() == type.lower()]
        pool     = filtered if filtered else all_cards
    else:
        pool = all_cards

    if shuffle:
        pool = list(pool)
        random.shuffle(pool)

    selected = pool[:limit]

    if not selected:
        raise HTTPException(
            status_code=404,
            detail="No cards found. Add vocabulary data to the dataset."
        )

    flash_cards = [
        FlashCard(
            id      = str(c.get("id", "")),
            luganda = str(c.get("luganda", "")),
            english = str(c.get("english", "")),
            type    = str(c.get("type", "vocabulary")),
            notes   = str(c.get("notes", "")),
        )
        for c in selected
    ]

    return CardsResponse(
        cards       = flash_cards,
        total       = len(flash_cards),
        source      = source,
        filtered_by = type,
    )


@router.get("/quiz", response_model=QuizQuestion)
def get_quiz_question(
    category: Optional[str] = Query(default=None, description="Filter by category"),
    exclude:  Optional[str] = Query(default=None, description="Comma-separated luganda words to exclude (already seen)"),
):
    """
    Return one multiple choice quiz question.

    The question asks: "What does [Luganda word] mean in English?"
    Four options are given — one correct, three random distractors.

    Use the 'exclude' param to avoid repeating recently seen words.
    Example: exclude=Embwa,Enjovu,Ente
    """
    all_cards, _ = _load_vocabulary_from_chroma(category=category)

    if len(all_cards) < 4:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Not enough vocabulary cards to generate a quiz. "
                f"Need at least 4, found {len(all_cards)}. "
                f"Run data ingestion first."
            )
        )

    # Filter out recently seen words if provided
    exclude_set = set()
    if exclude:
        exclude_set = {w.strip().lower() for w in exclude.split(",")}

    available = [
        c for c in all_cards
        if c["luganda"].strip().lower() not in exclude_set
    ]

    # If all cards have been seen, reset and use the full pool
    if not available:
        available = all_cards

    # Pick one random card as the question target
    target = random.choice(available)

    return _generate_quiz_question(target, all_cards)


@router.post("/quiz/answer", response_model=AnswerResponse)
def check_answer(request: AnswerRequest):
    """
    Check a quiz answer and return feedback.

    The frontend sends:
      - question_id : which question was answered
      - selected_id : which option the user picked (A/B/C/D)
      - correct_id  : which option was correct (sent from frontend state)

    Returns whether the answer was correct plus an encouraging message.
    """
    is_correct = request.selected_id == request.correct_id

    return AnswerResponse(
        correct      = is_correct,
        selected_id  = request.selected_id,
        correct_id   = request.correct_id,
        correct_text = "",   # Frontend already has the text from the question
        message      = (
            random.choice(CORRECT_MESSAGES) if is_correct
            else random.choice(WRONG_MESSAGES)
        ),
    )


@router.get("/progress", response_model=ProgressData)
def get_progress():
    """Return the user's overall learning progress from the local file."""
    data = _load_progress()
    return ProgressData(**data)


@router.post("/progress")
def save_progress(request: SaveProgressRequest):
    """
    Save session results to the local progress file.
    Called by the frontend when a session ends.
    """
    data = _load_progress()

    data["total_sessions"]    = data.get("total_sessions", 0) + 1
    data["total_cards_seen"]  = data.get("total_cards_seen", 0) + request.cards_seen
    data["total_correct"]     = data.get("total_correct", 0) + request.correct
    data["total_wrong"]       = data.get("total_wrong", 0) + request.wrong
    data["last_session"]      = request.session_date

    _save_progress(data)

    return {
        "status":  "saved",
        "summary": data,
    }
