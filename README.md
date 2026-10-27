# Medicine Review Insights

An academic research interface for the supplied UCI/KUC drug-review data. It offers configurable review-based rankings for a selected condition and a searchable corpus explorer.

## Run locally

Use the managed web workflow or run:

```sh
pnpm --filter @workspace/medicine-review-insights run dev
```

Typecheck:

```sh
pnpm --filter @workspace/medicine-review-insights run typecheck
```

The production workflow builds a static site from this package. No API, database, or secrets are required.

## Dataset

The attached training and testing archives contain 161,297 and 53,766 source rows. The preparation script cleans and aggregates 212,698 usable reviews into `public/data/medicine-review-summary.json`; 2,365 incomplete or invalid rows are excluded. This includes removing malformed condition values that contain review-interface HTML fragments. The generated summary includes medicine/condition statistics, short review excerpts, concern keyword counts, term counts, and two-word phrase counts.

Regenerate the summary after replacing the attached archives:

```sh
python3 scripts/prepare_reviews.py
```

The generator uses Python's standard library only.

## Ranking and interpretation

The ranking is a transparent project-defined heuristic. It combines mean rating, positive rating share, review usefulness, review-volume confidence, and concern-keyword mentions. Preference selections change the weights. The project score is not clinically validated.

Sentiment bands are rating-derived: 8–10 positive, 5–7 neutral, 1–4 negative. This is a coarse proxy, not an NLP classifier or an independent measure of treatment outcomes. The supplied files do not include a trained sentiment model.

**Research use only.** Patient-written reviews are subjective and may be biased or incomplete. Rankings and excerpts do not establish medicine safety or efficacy and must not guide treatment decisions.

## Source

KUC Hackathon Winter 2018 Drug Review dataset, as named in the supplied project brief. Original archives are retained in the workspace `attached_assets/` directory.
