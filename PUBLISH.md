# Publishing JevGym

How to publish and update the JevGym site (GitHub Pages), the code repo, the private
communication repo, and — when you're ready — the dataset on Hugging Face.

- **Public repo + site:** `github.com/ruyianry/JevGym` → served at
  **https://ruyianry.github.io/JevGym/**
- **Private repo (confidential/comms):** `github.com/ruyianry/jevarena-internal` (private)
- **Dataset (Hugging Face):** `ruyian/JevArena` — **HELD** until you say go.

The site is plain static HTML at the repo root (`index.html`, `kalshi.html`, `beat-jev.html`,
`evaluate.html`) — no build step. GitHub Pages serves them directly.

---

## 0. One-time: what stays secret

Never commit these (already in `.gitignore`, verified):

- `.env` — your `TYPESAFE_API_KEY` (Jev) and `HF_TOKEN`.
- `CONFIDENTIAL.md` — the candid internal assessment.
- `*.private.md`, `data/` (raw API payloads + derived artifacts), `.claude/`.

Quick safety check before any push:

```bash
git status --short                 # .env / CONFIDENTIAL.md must NOT appear
git ls-files | grep -iE 'env|confidential|private' || echo "clean"
```

---

## 1. Publish the public site (first time)

From the project root:

```bash
git add -A
git commit -m "JevGym: public site + KalshiJev benchmark"
git branch -M main

# create the public repo on your account and push
gh repo create ruyianry/JevGym --public --source=. --remote=origin --push

# turn on GitHub Pages from main / root
gh api -X POST repos/ruyianry/JevGym/pages \
  -f 'source[branch]=main' -f 'source[path]=/'
```

Pages builds in ~1 minute. Your site is then live at **https://ruyianry.github.io/JevGym/**.
Check build status any time:

```bash
gh api repos/ruyianry/JevGym/pages | python3 -m json.tool   # look for "status": "built"
```

---

## 2. Update the site (every time after)

Edit any `*.html` (or the docs), then:

```bash
git add -A
git commit -m "site: <what changed>"
git push
```

Pages rebuilds automatically within a minute or two. Hard-refresh your browser
(Cmd-Shift-R) if you don't see the change — GitHub/browsers cache aggressively.

**Tip — preview locally before pushing:**

```bash
python3 -m http.server 8901        # then open http://localhost:8901/index.html
```

---

## 3. The private repo (confidential / communication)

`CONFIDENTIAL.md` and key notes live in a **separate private repo** so they can never leak
into the public one. It lives at `../jevarena-internal`.

```bash
cd ../jevarena-internal
git add -A
git commit -m "internal: refresh confidential notes"
# first time only:
gh repo create ruyianry/jevarena-internal --private --source=. --remote=origin --push
# after that:
git push
```

Keep the public `CONFIDENTIAL.md` (in the JevGym working dir) as your live scratch copy;
copy it over when you want to snapshot it into the private repo:

```bash
cp CONFIDENTIAL.md ../jevarena-internal/CONFIDENTIAL.md
```

---

## 4. Custom domain (optional)

If you point a domain at the site: add a `CNAME` file at the repo root containing just the
domain (e.g. `jevgym.ai`), push, then set the DNS records GitHub shows under
Settings → Pages. Until then, `ruyianry.github.io/JevGym/` is the canonical URL.

---

## 5. Dataset on Hugging Face (when you're ready — currently HELD)

The dataset push is intentionally on hold. When you decide to release it:

```bash
# token in .env as HF_TOKEN; repo id ruyian/JevArena
pip install -e ".[hf]"
jevgym hf-build                          # builds configs + card locally, no upload
jevgym hf-push --repo ruyian/JevArena    # private by default; add --public to open it
```

Review `DISCLAIMER.md` first — the **Kalshi Data ToS restricts ML-training use and
redistribution of archived data** without written consent, so only derived records
(never raw payloads) should ever be shared.

---

## 6. Before you make anything public — checklist

- [ ] `git status` clean of `.env` / `CONFIDENTIAL.md` / `data/`.
- [ ] `LICENSE` copyright holder — currently "the JevGym authors"; set your legal name/entity
      if you prefer (see the note at the bottom of `LICENSE`).
- [ ] `DISCLAIMER.md` reviewed (not affiliated with Kalshi/Polymarket/TypeSafe; not advice).
- [ ] Pages you don't want indexed yet? Keep the repo private until ready
      (`gh repo edit ruyianry/JevGym --visibility private`), then flip to public.
- [ ] `ruff check src tests scripts` and `pytest` green.
