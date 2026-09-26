"""
Build a ChromaDB index from markdown KB articles and run sample queries.

Usage:
    pip install chromadb
    python build_kb_index.py                # uses ./data/kb
    python build_kb_index.py path/to/kb     # custom folder

Steps:
  1) Read every .md file in the KB folder
  2) Split each article into chunks at '## ' headings
  3) Store all chunks in the ChromaDB collection 'isdo_kb'
  4) Run 4 sample queries and print the best-matching article + confidence
"""

import re
import sys
from pathlib import Path

import chromadb

KB_DIR = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("data/kb")
DB_DIR = "chroma_db"            # persisted index folder
COLLECTION_NAME = "isdo_kb"

SAMPLE_QUERIES = [              # edit these to match your articles
    "I can't connect to the VPN from home",
    "How do I reset my forgotten password?",
    "The printer is not printing my documents",
    "Outlook keeps crashing when I open it",
]

H2_PATTERN = re.compile(r"^##\s+(.+?)\s*$")   # matches '## X' but not '### X'


# ---------------------------------------------------------------- 1) read
def read_articles(kb_dir: Path) -> dict[str, str]:
    if not kb_dir.is_dir():
        sys.exit(f"KB folder not found: {kb_dir.resolve()}")
    files = sorted(kb_dir.glob("*.md"))
    if not files:
        sys.exit(f"No .md files found in {kb_dir.resolve()}")
    return {f.stem: f.read_text(encoding="utf-8") for f in files}


# ---------------------------------------------------------------- 2) chunk
def split_at_h2(text: str) -> list[tuple[str, str]]:
    """Return [(heading, body), ...]. Text before the first '##' becomes 'Introduction'."""
    chunks, heading, lines = [], "Introduction", []
    in_code_block = False

    for line in text.splitlines():
        if line.strip().startswith("```"):
            in_code_block = not in_code_block
        match = None if in_code_block else H2_PATTERN.match(line)
        if match:
            if "\n".join(lines).strip():
                chunks.append((heading, "\n".join(lines).strip()))
            heading, lines = match.group(1), []
        else:
            lines.append(line)

    if "\n".join(lines).strip():
        chunks.append((heading, "\n".join(lines).strip()))
    return chunks


def article_title(article: str, text: str) -> str:
    """Use the '# Title' line if present, else the file name."""
    for line in text.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return article


# ---------------------------------------------------------------- 3) store
def build_collection(articles: dict[str, str]):
    client = chromadb.PersistentClient(path=DB_DIR)

    # Start fresh each run so edited/removed articles don't leave stale chunks
    try:
        client.delete_collection(COLLECTION_NAME)
    except Exception:
        pass

    # Cosine distance -> confidence = 1 - distance is easy to read (0..1)
    collection = client.create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )

    ids, docs, metas = [], [], []
    for article, text in articles.items():
        title = article_title(article, text)
        for i, (heading, body) in enumerate(split_at_h2(text)):
            ids.append(f"{article}::{i}")
            # Prefix title + heading so each chunk carries its context
            docs.append(f"{title} - {heading}\n\n{body}")
            metas.append({"article": article, "title": title,
                          "heading": heading, "chunk_index": i})

    collection.add(ids=ids, documents=docs, metadatas=metas)
    print(f"Indexed {len(ids)} chunks from {len(articles)} articles "
          f"into '{COLLECTION_NAME}' ({Path(DB_DIR).resolve()})\n")
    for article in articles:
        n = sum(1 for m in metas if m["article"] == article)
        print(f"  - {article}.md: {n} chunks")
    print()
    return collection


# ---------------------------------------------------------------- 4) query
def run_queries(collection, queries: list[str]) -> None:
    n_results = min(5, collection.count())
    for q in queries:
        res = collection.query(query_texts=[q], n_results=n_results,
                               include=["metadatas", "distances"])
        metas, dists = res["metadatas"][0], res["distances"][0]

        best = metas[0]                       # results are sorted by distance
        confidence = max(0.0, 1.0 - dists[0])

        print(f"Query:      {q}")
        print(f"Best match: {best['article']}.md  (section: {best['heading']})")
        print(f"Confidence: {confidence:.2%}")
        runner_up = next((m for m, d in zip(metas, dists)
                          if m["article"] != best["article"]), None)
        if runner_up:
            d = dists[metas.index(runner_up)]
            print(f"Runner-up:  {runner_up['article']}.md ({max(0.0, 1 - d):.2%})")
        print("-" * 60)


if __name__ == "__main__":
    articles = read_articles(KB_DIR)
    collection = build_collection(articles)
    run_queries(collection, SAMPLE_QUERIES)