# Luganda AI Studio — Handoff Report
> Written: 2026-05-09 | Last updated: 2026-05-09 | Session: Permanent Domain + Tunnel Setup
> Read by Claude at the start of every session (placed in project root).

---

## 1. What This App Is

A local-first AI application for Luganda ↔ English translation, semantic search, interactive teaching/flashcards, user feedback collection, and AI chat. Built with FastAPI + ChromaDB + NLLB-200 + Ollama. All AI runs on the user's machine (RTX 3050, 4 GB VRAM).

**Live URL (permanent — same link forever):**
https://app.lugandastudio.com
_(Tunnel auto-starts with Windows. Only start.bat is needed manually.)_

---

## 2. How to Start the App

### Every time you want the app running:

**Step 1 — Open PowerShell and start the backend:**
```powershell
cd D:\projects\Luganda_AI_Studio
.\start.bat
```
Wait until you see: `Uvicorn running on http://127.0.0.1:8000`

**That's it.** The Cloudflare tunnel starts automatically with Windows — you do NOT need to run cloudflared manually anymore.

**Step 2 (optional) — Start Ollama for chat:**
```powershell
ollama serve
```
Without this, the chat tab shows "offline" but translation, search, and teaching all work fine.

### Your permanent public URL:
**https://app.lugandastudio.com** — share this with anyone. It never changes.

### Verify it's working:
| Page | URL |
|---|---|
| Public frontend | https://app.lugandastudio.com/app/index.html |
| Local frontend | http://127.0.0.1:8000/app/index.html |
| API health | https://app.lugandastudio.com/api/v1/health |
| API docs | https://app.lugandastudio.com/docs |

### To stop:
Press `Ctrl+C` in the terminal running `start.bat`. The tunnel service keeps running in the background (by design) — it uses no resources when the app is off and will just show 502 until you start the app again.

---

## 3. Do I Have to Share a New Link Every Time?

**No.** The permanent named tunnel is now set up. The URL **https://app.lugandastudio.com** never changes. Share it once and it works forever as long as your machine is on and `start.bat` is running.

---

## 4. Where Is the Data Stored?

All data lives on YOUR machine at `D:\projects\Luganda_AI_Studio\data\`.

| Data | Path | What it is |
|---|---|---|
| ChromaDB vector database | `data/chromadb/` | ~2,500+ Luganda/English pairs. Core translation data. SQLite + binary index files. |
| User feedback | `data/feedback/feedback_log.jsonl` | Every ✓/✗/🔁 rating a user submits. Grows with use. |
| Corrections | `data/training/corrections.jsonl` | Full records when users provide the correct translation. |
| Training pairs | `data/training/training_pairs.jsonl` | Minimal format pairs for future NLLB fine-tuning. |
| Ingestion log | `data/datasets/ingestion_log.jsonl` | Record of what datasets have been imported. |
| Imported datasets | `data/datasets/` | Flores-200 sentence pairs downloaded in Phase 1. |

**This data does NOT go to the cloud. It does NOT leave your machine.**
When someone uses the app through the Cloudflare tunnel, their requests hit your machine, the translation runs locally, and results are sent back. Feedback they submit writes to YOUR disk.

### Backing up the data:
The simplest backup is to copy the entire `data/` folder to an external drive or cloud storage (Google Drive, OneDrive, etc.) periodically. See Section 6 for the Git approach.

---

## 5. Permanent URL Setup — COMPLETED 2026-05-09

This is done. No action needed. Recorded here for reference.

### What was set up:

| Step | What happened |
|---|---|
| A | Bought `lugandastudio.com` via Cloudflare Registrar (~$9/yr, renews May 2027) |
| B | Domain added to Cloudflare — Active on Free plan |
| C | Ran `cloudflared tunnel login` — machine authorised |
| D | Created named tunnel `luganda-studio` (ID: `edcb6439-b31a-4541-bc42-4eaf5c536686`) |
| E | Config file written to `C:\Users\patri\.cloudflared\config.yml` |
| F | DNS CNAME record added: `app.lugandastudio.com` → tunnel |
| G | Ran `cloudflared service install` (as Administrator) — tunnel now auto-starts with Windows |

### Key files on this machine:
| File | Purpose |
|---|---|
| `C:\Users\patri\.cloudflared\config.yml` | Tunnel config — hostname + service routing |
| `C:\Users\patri\.cloudflared\edcb6439-b31a-4541-bc42-4eaf5c536686.json` | Tunnel credentials — keep secret, do not share |
| `C:\Users\patri\.cloudflared\cert.pem` | Origin certificate from `cloudflared tunnel login` |

### Live URL:
**https://app.lugandastudio.com** — permanent, HTTPS, works whenever machine is on and `start.bat` is running.

---

## 6. Putting ChromaDB Data in Git (No Supabase / Vercel Needed)

The current `.gitignore` blocks `*.sqlite3` and `*.bin` — this means your ChromaDB data is NOT backed up by git.

### Fix: allow the data folder in git

Add these lines to `.gitignore` EXCEPTIONS (already done if you ran the fix):
```
# Allow ChromaDB data to be committed
!data/chromadb/
!data/chromadb/**
!data/feedback/
!data/training/
```

Then:
```powershell
git add data/chromadb/ data/feedback/ data/training/
git commit -m "Add ChromaDB data and feedback logs"
git push
```

**Trade-off:** ChromaDB binary files are large (~50–200 MB). If they grow very large, use Git LFS (Large File Storage) — free on GitHub up to 1 GB.

**You do NOT need Supabase or Vercel for this.** Those are for multi-user cloud databases. Your app is single-machine and ChromaDB handles everything locally. Git is sufficient for backup and version history.

---

## 7. What Was Built — Session Log

### Session 1 (2026-05-09): Deployment + Infrastructure

| File | Action | What changed |
|---|---|---|
| `requirements.txt` | REPLACED | Was UTF-16 encoded (broken for pip). Now clean UTF-8 with all pinned versions. |
| `backend/core/config.py` | EDITED | Added `python-dotenv` loader. Made `OLLAMA_BASE_URL` and `OLLAMA_DEFAULT_MODEL` configurable via env vars. |
| `.env` | CREATED | Local environment file with safe defaults. Not committed to git. |
| `start.bat` | CREATED | One-command Windows startup script. |
| `DEPLOY_CLOUDFLARE.md` | CREATED | Full step-by-step Cloudflare Tunnel guide. |
| `HANDOFF.md` | CREATED | This file. |

### Session 2 (2026-05-09): Permanent Domain + Tunnel

| Action | Detail |
|---|---|
| Bought domain | `lugandastudio.com` via Cloudflare Registrar — $9/yr, renews May 2027 |
| Named tunnel created | `luganda-studio` (ID: `edcb6439-b31a-4541-bc42-4eaf5c536686`) |
| Config file written | `C:\Users\patri\.cloudflared\config.yml` |
| DNS record added | `app.lugandastudio.com` CNAME → tunnel |
| Windows service installed | `cloudflared service install` — tunnel auto-starts on boot |
| Live URL confirmed | https://app.lugandastudio.com loads the app |

---

## 8. Session 3 — PWA + Mobile Optimisation (COMPLETED 2026-05-09)

### What was built

| File | Action | Detail |
|---|---|---|
| `frontend/icons/icon-192.svg` | NEW | Drumhead logo — 192px. Dark green bg, radial lines, amber "L". |
| `frontend/icons/icon-512.svg` | NEW | Same logo at 512px for splash screens. |
| `frontend/manifest.json` | NEW | PWA manifest — name, icons, theme, scope, shortcuts to Translate + Teach. |
| `frontend/service-worker.js` | NEW | Cache-first SW. Caches all 6 HTML pages + assets. Never caches API calls. Offline fallback to index.html. |
| `frontend/index.html` | EDIT | PWA head tags, mobile drawer nav, ☰ toggle button, SW registration. |
| `frontend/translate.html` | EDIT | PWA head tags, mobile drawer nav, improved touch targets (52px buttons, 44px feedback buttons). |
| `frontend/search.html` | EDIT | PWA head tags, mobile drawer nav, full-width search button on mobile. |
| `frontend/teach.html` | EDIT | PWA head tags, mobile drawer nav, scaled flashcard + quiz for mobile. |
| `frontend/chat.html` | EDIT | PWA head tags, mobile CSS (16px textarea prevents iOS zoom, full-width chips). |
| `frontend/reviews.html` | EDIT | PWA head tags, mobile drawer nav, touch-friendly filter tabs. |

### PWA install behaviour
- **Android Chrome:** install banner appears automatically after 2 visits. App launches full-screen.
- **iOS Safari:** Share → Add to Home Screen. Full-screen.
- **Desktop Chrome:** install icon in address bar.
- **Offline:** UI shell loads from cache. API calls fail gracefully (already handled in each page's JS).

### Logo: Drumhead (Concept 3)
Amber "L" at centre of a circle with radial lines — references the engalabi drum. Dark green background matching app colour scheme.

---

## 9. Next Session

**Approved scope for next session:**

### A. Mobile/Accessibility optimisation
- Make all 6 HTML pages responsive for phone screens (320px–480px)
- Touch-friendly tap targets (min 44×44px)
- Fix font sizes for small screens
- Improve contrast ratios for accessibility (WCAG AA)
- Test translate, search, teach, and feedback flows on mobile layout
- Target: Android and iOS equally

### B. Progressive Web App (PWA)
- Add `manifest.json` — defines app name, icons, theme colour, display mode
- Add `service-worker.js` — enables offline caching of the UI shell
- Add install prompt so Android users see "Add to Home Screen"
- iOS users: manual "Share → Add to Home Screen" (iOS limitation)
- App icon needed — either generate one or ask Mukalazi to provide a logo
- Offline behaviour: UI loads from cache, shows "connecting..." when backend is off

### PWA install works on:
| Platform | How |
|---|---|
| Android Chrome | Automatic install banner or menu |
| iOS Safari | Manual: Share → Add to Home Screen |
| Desktop Chrome | Install icon in address bar |

### Files that will change in next session:
- `frontend/manifest.json` (NEW)
- `frontend/service-worker.js` (NEW)
- `frontend/styles.css` (EDIT — mobile breakpoints)
- `frontend/index.html` (EDIT — manifest link, SW registration)
- `frontend/translate.html` (EDIT — mobile layout)
- `frontend/search.html` (EDIT — mobile layout)
- `frontend/teach.html` (EDIT — mobile layout)
- `frontend/chat.html` (EDIT — mobile layout)
- `frontend/reviews.html` (EDIT — mobile layout)

---

## 10. Full App State Snapshot (2026-05-09)

### Working right now:
- Translation: exact → normalized → partial → semantic → NLLB-200 neural
- Search across vocabulary, sentences, grammar, proverbs
- Feedback collection with correction UI → auto-ingest into ChromaDB
- Reviews page: admin view of all submitted feedback
- Teaching mode: flashcards + quiz
- Chat assistant via Ollama (requires `ollama serve`)
- Session quality metrics on translate page
- Cloudflare Tunnel: public HTTPS URL from local machine

### NOT built yet:
- Admin dashboard (Phase 5)
- Evaluation/test suite (Phase 6)
- LoRA fine-tuning script (needs 500+ correction pairs first)
- Voice input/output (no Luganda audio model confirmed)
- PWA + mobile optimisation (approved for next session)

### Data counts:
- ChromaDB: ~2,500+ pairs (vocabulary + sentences + grammar + proverbs + corrections)
- Feedback log: grows with each user session
- Training pairs: accumulating for future NLLB fine-tuning

---

## 11. Machine Specs (Do Not Forget These)

| Component | Spec |
|---|---|
| OS | Windows 11, 64-bit |
| CPU | Intel Core i7-11800H |
| RAM | 16 GB |
| GPU | NVIDIA RTX 3050 Laptop |
| VRAM | 4 GB |

**Constraint:** Do not recommend training large models from scratch. NLLB-200-distilled-600M (~2.3 GB) is the largest model that fits. All AI must be realistic for 4 GB VRAM or CPU-only fallback.
