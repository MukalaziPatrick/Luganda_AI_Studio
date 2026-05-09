# Cloudflare Tunnel — Deployment Guide

Share Luganda AI Studio publicly from your Windows machine in ~30 minutes.
No cloud server. No data migration. Your GPU and models stay local.

---

## How It Works

```
Internet → Cloudflare Edge (HTTPS) → cloudflared.exe → localhost:8000
```

Cloudflare gives you a stable HTTPS URL that tunnels directly to your
running FastAPI app. Your machine is the server.

---

## Step 1 — Start the App

Open a terminal in `D:\projects\Luganda_AI_Studio\` and run:

```bat
start.bat
```

Or manually:

```bat
venv\Scripts\activate
uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
```

Confirm it works at: http://127.0.0.1:8000/app/index.html

---

## Step 2 — Install cloudflared

Download the latest Windows installer from:
https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/

Choose: **cloudflared-windows-amd64.msi**

Install it. After install, open a new terminal and verify:

```bat
cloudflared --version
```

---

## Step 3 — Start the Tunnel (Quick Mode — no account needed)

In a second terminal (keep the app running in the first), run:

```bat
cloudflared tunnel --url http://localhost:8000
```

After ~5 seconds you will see output like:

```
INF |  https://xyz-abc-123.trycloudflare.com
```

That URL is your public app. Share it with anyone. It works immediately.

**Note:** This URL changes every time you restart cloudflared.
For a permanent URL, see Step 4 below.

---

## Step 4 (Optional) — Permanent URL with a Free Cloudflare Account

A named tunnel gives you a permanent custom subdomain (e.g. `luganda.yourdomain.com`).

### 4a. Create a Cloudflare account and add your domain
- Sign up free at https://cloudflare.com
- Add a domain you own, or use a free `.pages.dev` subdomain

### 4b. Authenticate cloudflared

```bat
cloudflared tunnel login
```

This opens a browser to authorise your machine.

### 4c. Create a named tunnel

```bat
cloudflared tunnel create luganda-studio
```

Note the tunnel ID printed (e.g. `a1b2c3d4-...`).

### 4d. Create the config file

Create `C:\Users\<you>\.cloudflared\config.yml`:

```yaml
tunnel: <your-tunnel-id>
credentials-file: C:\Users\<you>\.cloudflared\<tunnel-id>.json

ingress:
  - hostname: luganda.yourdomain.com
    service: http://localhost:8000
  - service: http_status:404
```

### 4e. Add DNS record

```bat
cloudflared tunnel route dns luganda-studio luganda.yourdomain.com
```

### 4f. Run the named tunnel

```bat
cloudflared tunnel run luganda-studio
```

Your app is now live at `https://luganda.yourdomain.com` — permanently,
as long as your machine is on and the tunnel is running.

---

## Step 5 — Run Both Together (Recommended)

Open two terminals side by side:

**Terminal 1 — App:**
```bat
cd D:\projects\Luganda_AI_Studio
start.bat
```

**Terminal 2 — Tunnel:**
```bat
cloudflared tunnel --url http://localhost:8000
```

Or for named tunnel:
```bat
cloudflared tunnel run luganda-studio
```

---

## Verify Everything Works

Once both are running, open your Cloudflare URL and test:

| Check | URL |
|---|---|
| Frontend | `https://xyz.trycloudflare.com/app/index.html` |
| API health | `https://xyz.trycloudflare.com/api/v1/health` |
| API docs | `https://xyz.trycloudflare.com/docs` |
| Translate test | POST to `/api/v1/translate` with `{"text":"hello","direction":"en_to_lg"}` |

---

## Notes

- **Chat feature** requires Ollama running locally (`ollama serve`). It will work
  through the tunnel as long as Ollama is up on your machine.
- **NLLB neural fallback** uses your local GPU — no change needed.
- **ChromaDB** reads from `data/chromadb/` on your disk — no migration needed.
- **Feedback submissions** write to `data/feedback/feedback_log.jsonl` on your disk.
- CORS is set to `*` in `backend/main.py` — the tunnel URL is accepted automatically.

---

## Stopping

- Press `Ctrl+C` in each terminal to stop the app and the tunnel.
- Your data is safe — ChromaDB and feedback files are untouched.
