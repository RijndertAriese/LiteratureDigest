# Literature Bot

A weekly literature digest bot that searches PubMed, arXiv, and bioRxiv for new publications matching your research topics, and emails you a formatted PDF.

## How it works

1. **Translate** — Groq turns each plain-English topic into several query variants per source (focused, broad, synonyms) and keyword groups for bioRxiv
2. **Fetch** — runs every variant against PubMed (Entrez), arXiv, bioRxiv and medRxiv and merges the results. PubMed errata, comments, editorials and retraction notices are skipped
3. **Screen** — Groq reads each candidate's title and abstract, drops off-topic hits (`relevance_screen`) and writes a one-line *why it's relevant* for each paper it keeps, so broad queries add recall without adding noise
4. **Filter** — peer-reviewed papers below `min_impact_factor` are dropped (see below); preprints are kept unfiltered
5. **Rank** — within each topic, always-included journals come first, then by impact factor (high → low), then unknown-IF journals; ties go to the newest paper. Preprints are listed newest first. A paper matching several topics is shown in full once and cross-referenced elsewhere
6. **Summarise** — Groq writes a 2–3 sentence overview of each topic's week
7. **Build** — compiles a PDF digest: a page-1 overview table (per-topic counts, papers dropped by the IF filter, failed sources), a *Followed authors* section, one section per topic (with its weekly summary), then a separate Preprints section. Each paper shows article-type badges (Review, Clinical trial, Case report, Preprint, Followed), its *why* line and a **Free PDF** link when OpenAlex knows an open-access copy
8. **Send** — emails the PDF via SMTP. The email body itself carries the overview table, each topic's summary and top 3 papers, and every followed-author paper, so the highlights are readable without opening the attachment

## Configuration

Edit `config.yaml` to set your topics and search interval:

```yaml
topics:
  - "myeloid cells in brain cancers"
  - "CAR-macrophage therapy for solid tumors"
  - "microglia engineering in glioma"
  - "pediatric brain tumor microenvironment"
  - topic: "(live) imaging and spatial transcriptomics"  # topic with key terms
    hints:                # key terms; a list of lists needs one term from every group
      - ["imaging", "live imaging", "immunofluorescence"]
      - ["spatial transcriptomics", "Visium", "Xenium"]
    criteria: "Imaging and spatial transcriptomics are jointly analysed, not just both used"  # strict screen rule

interval_days: 7          # how many days back to search (match your cron schedule)
max_results_per_source: 25 # per topic, source and query variant
max_age_days: 60          # PubMed: keep papers new to PubMed if published ≤ 60 days ago
relevance_screen: true    # Groq drops off-topic hits (needs GROQ_API_KEY)
min_impact_factor: 3.5   # drop peer-reviewed papers below this; 0 disables
always_include_journals: ["Neuro-Oncology"]  # exempt from the IF filter
followed_authors: ["Ariese HCR"]  # always included, marked ★ (last name + initials)
followed_author_positions: {first: 3, last: 3}  # only count lead/senior authorship
recipient_email: "you@example.com"  # overridden by RECIPIENT_EMAIL secret
```

### Impact-factor filtering

There is no free, licensed feed for the Clarivate Journal Impact Factor, so the
bot uses [OpenAlex](https://openalex.org)'s `2yr_mean_citedness` — the same
citations-per-recent-paper ratio the JIF is built on, recomputed from open data.
It tracks the real JIF closely enough to screen out low-tier / predatory
journals (rough guide: *Neuro-Oncology* ≈ 16, *Glia* ≈ 6, *J Neurooncol* ≈ 3,
most predatory titles < 1.5).

- Applies to **peer-reviewed papers only**. arXiv / bioRxiv preprints have no
  journal metric and always appear, in their own section.
- Journals OpenAlex can't resolve are **kept** (shown as `IF n/a`), so new or
  niche journals aren't silently lost.
- **Known limitation:** journals that publish large conference-abstract
  supplements (e.g. *Neuro-Oncology*) score far below their real JIF because
  OpenAlex averages in thousands of ~0-citation abstracts. List substrings of
  such journal names under `always_include_journals` in `config.yaml` to exempt
  them; they appear marked `always included`.
- No API key needed. Set `min_impact_factor: 0` to turn filtering off.
- Optional `OPENALEX_EMAIL` secret joins OpenAlex's faster "polite pool";
  otherwise it falls back to `NCBI_EMAIL` / `SENDER_EMAIL`.

For PubMed, a paper is new when it **entered PubMed** in the last `interval_days`
(the Entrez date), so every paper lands in exactly one weekly digest. Journals
often deposit papers weeks after they go online, so these are kept as long as
their exact electronic/publication date is at most `max_age_days` old; older
back-catalogue records that are merely (re)indexed are excluded.

bioRxiv and medRxiv have no search API: the bot downloads each server's
preprint listing for the window once per run and matches each topic's keyword
groups (and the followed authors) against it.

arXiv requests use a shared throttled client to avoid API rate limits across
multiple configured topics.

## Required GitHub Secrets

Set these in **repo → Settings → Secrets → Actions**:

| Secret | Description |
|---|---|
| `SMTP_HOST` | SMTP server hostname (e.g. `smtp.gmail.com`) |
| `SMTP_PORT` | *(optional)* SMTP port; defaults to `587` (STARTTLS). Use `465` for implicit SSL |
| `SMTP_USER` | SMTP username (usually the full email address) |
| `SMTP_PASSWORD` | SMTP password. For Gmail, a 16-char [App Password](https://myaccount.google.com/apppasswords) (requires 2FA) |
| `SENDER_EMAIL` | *(optional)* From address; defaults to `SMTP_USER` |
| `RECIPIENT_EMAIL` | Where to send the digest |
| `GROQ_API_KEY` | *(recommended)* Enables query translation; raw topics are used if absent |
| `GROQ_MODEL` | *(optional)* Override the Groq model; defaults to `openai/gpt-oss-20b` |
| `OPENALEX_EMAIL` | *(optional)* Contact email for OpenAlex's faster polite pool (impact-factor lookups) |
| `NCBI_EMAIL` | *(optional)* PubMed contact email; defaults to `SENDER_EMAIL` |
| `NCBI_API_KEY` | *(optional)* Raises PubMed rate limit |

## Schedule

The workflow runs every **Monday at 08:17 UTC** by default.

To change the schedule, edit `.github/workflows/digest.yml`:

```yaml
schedule:
  - cron: "17 8 * * 1"  # Mon 08:17 UTC  → weekly
  # - cron: "0 8 1,15 * *" # 1st & 15th   → biweekly
  # - cron: "0 8 1 * *"    # 1st of month → monthly
```

Also update `interval_days` in `config.yaml` to match.

## Manual trigger

Go to **Actions → Literature Digest → Run workflow** to trigger immediately.

### Local trigger (optional)

GitHub's cron can start scheduled runs late, so `trigger_workflow.sh` can
trigger the workflow from your Mac every Monday via launchd. It uses the GitHub
CLI, whose credentials live in the macOS Keychain, so no token is stored in the
repo. One-time setup:

```bash
gh auth login
cp com.literature-bot.trigger.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.literature-bot.trigger.plist
```

## Project structure

```
bot/
  fetcher.py         # PubMed, arXiv, bioRxiv API queries
  query_translator.py # plain-English → query variants per source (Groq)
  screen.py          # Groq relevance screen, why-lines and weekly topic summaries
  authors.py         # followed-author name matching across sources
  impact.py          # journal impact-factor proxy via OpenAlex
  formatting.py      # shared date / IF / link formatting for PDF and email
  pdf_builder.py     # ReportLab PDF assembly
  mailer.py          # email body (overview + top picks) and SMTP send
  main.py            # orchestrator: config validation, ranking, run summary
config.yaml          # topics and settings
.github/workflows/digest.yml
```
