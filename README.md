# Nero — Xero Opportunity Research

Hackathon project. Research pipeline for surfacing product/market opportunities
for Xero from public signals (forums, app store reviews, community threads).

## Repo layout

```
xero-opportunity-research/
  raw/
    forums/       # scraped forum threads
    appstore/     # app store reviews
    community/    # community platform posts
```

## Collaboration workflow

Two people work on this repo (`Qin2Qin`, `khanhbtrn`), so we keep `main` clean
and ship everything through pull requests.

1. **Never commit directly to `main`.** Branch first:
   ```bash
   git switch -c <name>/<short-description>   # e.g. qin/forum-scraper
   ```
2. Commit, push the branch, open a PR against `main`.
3. Get a quick review from the other person, then squash-merge.
4. Delete the branch after merge and `git pull` on `main` to sync.

Keep PRs small and focused so they're fast to review.
