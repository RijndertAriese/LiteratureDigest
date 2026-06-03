# Literature Bot

A weekly literature digest bot that searches PubMed, arXiv, and bioRxiv for new publications matching your research topics, and emails you a formatted PDF.

## How it works

1. **Translate** — plain-English topics are converted to optimised database queries using Groq (Llama 3)
2. **Fetch** — queries PubMed (Entrez), arXiv, and bioRxiv for papers published in the last N days
3. **Build** — compiles a PDF digest with one section per topic: reference + abstract per paper
4. **Send** — emails the PDF via SendGrid

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
recipient_email: "you@example.com"  # overridden by RECIPIENT_EMAIL secret
```

For PubMed, the bot filters by exact electronic/publication date from the
fetched XML record. PubMed indexing dates are used only to find candidates, so
older papers that were merely indexed recently are excluded from the digest.

arXiv requests use a shared throttled client to avoid API rate limits across
multiple configured topics.

## Required GitHub Secrets

Set these in **repo → Settings → Secrets → Actions**:

| Secret | Description |
|---|---|
| `SENDGRID_API_KEY` | SendGrid API key (Mail Send permission only) |
| `SENDGRID_SENDER_EMAIL` | Verified sender email in SendGrid |
| `RECIPIENT_EMAIL` | Where to send the digest |
| `GROQ_API_KEY` | *(recommended)* Enables query translation; raw topics are used if absent |
| `NCBI_EMAIL` | *(optional)* PubMed contact email; defaults to `SENDGRID_SENDER_EMAIL` |
| `NCBI_API_KEY` | *(optional)* Raises PubMed rate limit |

## Schedule

The workflow runs every **Monday at 08:00 UTC** by default.

To change the schedule, edit `.github/workflows/digest.yml`:

```yaml
schedule:
  - cron: "0 8 * * 1"   # Mon 08:00 UTC  → weekly
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
  pdf_builder.py     # ReportLab PDF assembly
  mailer.py          # SendGrid email + attachment
  main.py            # orchestrator with config validation
config.yaml          # topics and settings
.github/workflows/digest.yml
```
