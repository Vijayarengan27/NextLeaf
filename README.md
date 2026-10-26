# NextLeaf

Describe your mood and time ("fast-paced, dark, 2-hour flight") and get up to five book picks with reasons.

## How it works
Book description + reader tags -> LLM "reader experience" blurb -> embedding -> Postgres/pgvector.
A query is parsed into constraints and trait targets, searched by similarity, re-ranked, and explained.