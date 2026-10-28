
# Data Ingestion

This project uses the [UCSD Goodreads public dataset](https://sites.google.com/eng.ucsd.edu/ucsdbookgraph/home). Since the dataset's terms restrict redistribution, the raw data is not included in this repository. The following steps describe how to reproduce the local data preparation pipeline.

## 1. Initial Data Selection

Each book record contains a `book_id` and a `work_id`. A `book_id` identifies a particular edition or translation, while a `work_id` groups editions belonging to the same underlying work.

We first build a `book_id` → `work_id` mapping from the book metadata. We then stream the reviews dataset and aggregate review statistics by `work_id`, including:

- Total number of reviews.
- Number of usable reviews, based on a minimum review-text length.
- Total number of characters across review texts.

These statistics help identify works with sufficient reader feedback for downstream analysis.

Next, we combine the review statistics with book metadata, including descriptions, ratings counts, average ratings, and other available fields. The works are filtered and ranked to select up to 5,000 candidates with rich metadata and sufficient review coverage.

To generate the initial selection CSV:

1. Update the input and output paths in `initial_data_selection.py`.
2. Run:

   ```bash
   uv sync
   uv run initial_data_selection.py
   ```

## 2. Selected Book Metadata and Reviews

The next stage enriches the selected works with additional metadata, including author names, page counts, publication information, genres, and other available fields. It also extracts a representative sample of reviews for each selected work.

To generate the enriched dataset:

1. Update the required file paths in `selected_books.py`.
2. Run:

   ```bash
   uv run selected_books.py
   ```

The resulting files are intended for local use by the project's annotation and recommendation pipeline. They may contain review text and metadata derived from the source dataset; **do not commit or redistribute these files unless the dataset's terms explicitly permit your intended use**.

## Reproducibility

The raw Goodreads dataset must be obtained separately and placed in the expected local paths. The scripts perform data selection and enrichment locally; they do not download or redistribute the source data.

## Citations

The Goodreads dataset was introduced and used in the following research papers:

1. Mengting Wan and Julian McAuley. **"Item Recommendation on Monotonic Behavior Chains."** *Proceedings of the 12th ACM Conference on Recommender Systems (RecSys '18), 2018.* [Paper](https://doi.org/10.1145/3240323.3240369)

2. Mengting Wan, Rishabh Misra, Ndapa Nakashole, and Julian McAuley. **"Fine-Grained Spoiler Detection from Large-Scale Review Corpora."** *Proceedings of the 57th Annual Meeting of the Association for Computational Linguistics (ACL '19), 2019.* [Paper](https://aclanthology.org/P19-1248/)