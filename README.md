# Literature Bot

A weekly literature digest bot that searches PubMed, arXiv, and bioRxiv for new publications matching your research topics, and emails you a formatted PDF.

## How it works

1. **Translate** — plain-English topics are converted to optimised database queries using Groq
2. **Fetch** — queries PubMed (Entrez), arXiv, and bioRxiv for papers published in the last N days
3. **Filter** — peer-reviewed papers below `min_impact_factor` are dropped (see below); preprints are kept unfiltered
4. **Build** — compiles a PDF digest with one section per topic, then a separate Preprints section
5. **Send** — emails the PDF via SMTP

## Configuration

Edit `config.yaml` to set your topics and search interval:

```yaml
topics:
  - "myeloid cells in brain cancers"
  - "CAR-macrophage therapy for solid tumors"
  - "microglia engineering in glioma"
  - "pediatric brain tumor microenvironment"

interval_days: 7          # how many days back to search (match your cron schedule)
max_results_per_source: 25 # per topic per source
min_impact_factor: 3.5   # drop peer-reviewed papers below this; 0 disables
always_include_journals: ["Neuro-Oncology"]  # exempt from the IF filter
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

For PubMed, the bot filters by exact electronic/publication date from the
fetched XML record. PubMed indexing dates are used only to find candidates, so
older papers that were merely indexed recently are excluded from the digest.

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

## Project structure

```
bot/
  fetcher.py         # PubMed, arXiv, bioRxiv API queries
  query_translator.py # plain-English → optimised search queries (Groq)
  impact.py          # journal impact-factor proxy via OpenAlex
  pdf_builder.py     # ReportLab PDF assembly
  mailer.py          # SMTP email + attachment
  main.py            # orchestrator with config validation
config.yaml          # topics and settings
.github/workflows/digest.yml
```
