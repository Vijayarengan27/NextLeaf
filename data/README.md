# NextLeaf — Data Seeding and Enrichment

This project uses the [UCSD Goodreads public dataset](https://sites.google.com/eng.ucsd.edu/ucsdbookgraph/home). Since the dataset's terms restrict redistribution, the raw data is not included in this repository.
The data is not redistributed or used for any commercial purposes in this project. Citations are added at the end of this document.

This document describes the process used to build the NextLeaf literary book catalogue from Goodreads data.

The pipeline transforms raw book metadata and review statistics into a structured SQLite catalogue containing book information, emotional themes, reading-experience descriptions, trait profiles, and semantic embeddings.

## 1. Pipeline overview

```text
Goodreads source data
        |
        v
Initial book selection
        |
        v
Selected book catalogue
        |
        v
Metadata and review preparation
        |
        v
Muse Spark enrichment
        |
        v
Blurb + Themes + 14 Traits
        |
        v
Reading-experience descriptions
        |
        v
BGE embedding generation
        |
        v
SQLite recommendation database
```

The resulting database is consumed by the NextLeaf FastAPI backend.

## 2. Input datasets

The data preparation process uses the following source files:

| File | Purpose |
|---|---|
| `goodreads_books.json` | Goodreads book metadata |
| `goodreads_book_authors.json.gz` | Goodreads author metadata |
| `goodreads_reviews_dedup.json` | Existing review statistics |


## 3. Initial book selection

Run the initial selection script, which maps the work id to diffrent book ids and then finds the works with usable review contents.


Run from the directory containing the script and its input files:

```powershell
uv run initial_data_selection.py
```
Then run the selected_books.py to get the required number of books specified in the "TARGET_WORKS" variable there.

```powershell
uv run selected_books.py
```

This creates a sqlite database of the required work ids and book metadata named goodreads_catalog.

## 4. Catalogue enrichment

The selected books are prepared for insertion into the NextLeaf SQLite database.

The catalogue contains a `books` table with fields including:

- Work ID and representative book ID
- Title and author information
- Description
- Language and publication information
- Page count and publisher
- Average rating and rating counts
- Review statistics
- Popular shelves
- Series information
- Selection score

The database also contains supporting tables for enrichment and review data.

The final catalogue database is:

```text
goodreads_catalog.sqlite
```

The application expects it at:

```text
data/goodreads_catalog.sqlite
```

## 5. AI-powered book enrichment

Muse Spark is used to generate additional information for each selected book.

The enrichment process produces:

### Book blurb

A concise description that captures the book's central subject matter and literary identity.

### Emotional themes

A collection of themes describing what the book explores.

Examples include:

- Loneliness
- Identity
- Grief
- Memory
- Love
- Alienation
- Belonging
- Existentialism

### Reading-experience traits

Each book receives a profile across 14 normalized dimensions, with values between 0 and 1.

| Category | Trait | Scale |
|---|---|---|
| Feel | Emotional intensity | Restrained → Intense |
| Feel | Darkness | Light → Bleak |
| Feel | Hope/cozy | Bleak → Comforting |
| Feel | Humour | Serious → Humorous |
| Feel | Tension/suspense | Relaxed → Suspenseful |
| Drive | Pace | Slow-burn → Propulsive |
| Drive | Action/violence | Little → Substantial |
| Drive | Romance/spice | Little → Prominent |
| Craft | Prose density | Clean → Literary/dense |
| Craft | Character depth | Simple → Complex |
| Craft | Plot complexity | Straightforward → Intricate |
| Craft | World immersion | Minimal → Rich |
| Mind | Philosophical depth | Little → Deep |
| Mind | Weirdness/experimental | Conventional → Experimental |

These profiles allow NextLeaf to compare the reader's desired experience against the characteristics of individual books.

## 6. Reading-experience descriptions

In addition to numerical traits, each book receives a natural-language reading-experience description.

This description captures qualities that are difficult to represent through individual numerical dimensions alone.

It is used as a separate semantic retrieval channel.

To get the AI powered enrichemnt, we run the following, using appropriate path variables in the respective files. blurb generation takes time, so it can be sped up in the future by using multiple threads.

```powershell
uv run text_blurb_generation.py
uv run get_embeddings.py
```

## 7. Embedding generation

NextLeaf uses:

```text
BAAI/bge-small-en-v1.5
```

Embeddings are generated locally using Sentence Transformers.

The pipeline maintains separate embeddings for:

- `content_embedding`: represents the book's subject matter, themes, and ideas.
- `experience_embedding`: represents the emotional and stylistic reading experience.

The resulting vectors are stored as float32 BLOBs in SQLite.

The embedding dimension is 384.

The same embedding model and preprocessing conventions must be used for both indexing and query-time retrieval.

The project currently contains embeddings and blurbs for 900 carefully selected works.

## 8. Database schema

### `books`

Stores the book catalogue and Goodreads metadata.

### `book_enrichment`

Stores generated enrichment information:

- `blurb`
- `themes_json`
- `traits_json`
- `reading_experience`
- `model_name`
- `prompt_version`
- `source_hash`
- `content_embedding`
- `experience_embedding`
- Embedding model metadata

### `reviews`

Stores the selected review records associated with books.



## Reproducibility

The raw Goodreads dataset must be obtained separately and placed in the expected local paths. The scripts perform data selection and enrichment locally; they do not download or redistribute the source data.

## Citations

The Goodreads dataset was introduced and used in the following research papers:

1. Mengting Wan and Julian McAuley. **"Item Recommendation on Monotonic Behavior Chains."** *Proceedings of the 12th ACM Conference on Recommender Systems (RecSys '18), 2018.* [Paper](https://doi.org/10.1145/3240323.3240369)

2. Mengting Wan, Rishabh Misra, Ndapa Nakashole, and Julian McAuley. **"Fine-Grained Spoiler Detection from Large-Scale Review Corpora."** *Proceedings of the 57th Annual Meeting of the Association for Computational Linguistics (ACL '19), 2019.* [Paper](https://aclanthology.org/P19-1248/)