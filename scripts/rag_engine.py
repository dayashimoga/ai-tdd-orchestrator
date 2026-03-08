"""RAG Engine — Retrieval-Augmented Generation for context injection.

Indexes user-provided reference documents (API specs, architecture docs, etc.)
and injects the most relevant chunks into LLM prompts to improve code quality.

Reference docs go in: your_project/docs/reference/
Supports: .md, .txt, .json, .yaml, .yml, .py, .js, .ts files.

Usage:
    from scripts.rag_engine import RAGEngine
    rag = RAGEngine("your_project/docs/reference")
    rag.index()
    context = rag.retrieve("implement user authentication", top_k=5)
"""
import os
import re
import math
import hashlib
from typing import List, Tuple, Optional, Dict


# ---------------------------------------------------------------------------
# Text Chunking
# ---------------------------------------------------------------------------

def chunk_text(text: str, chunk_size: int = 500, overlap: int = 50) -> List[str]:
    """Splits text into overlapping chunks of approximately `chunk_size` chars."""
    if len(text) <= chunk_size:
        return [text]

    chunks = []
    sentences = re.split(r'(?<=[.!?\n])\s+', text)
    current_chunk = ""

    for sentence in sentences:
        if len(current_chunk) + len(sentence) > chunk_size and current_chunk:
            chunks.append(current_chunk.strip())
            # Keep overlap from end of previous chunk
            words = current_chunk.split()
            overlap_text = " ".join(words[-overlap:]) if len(words) > overlap else ""
            current_chunk = overlap_text + " " + sentence
        else:
            current_chunk += " " + sentence

    if current_chunk.strip():
        chunks.append(current_chunk.strip())

    return chunks


# ---------------------------------------------------------------------------
# TF-IDF Vector Store (E6: proper IDF weighting)
# ---------------------------------------------------------------------------

def _tokenize(text: str) -> List[str]:
    """Simple whitespace + punctuation tokenizer."""
    return re.findall(r'\b[a-zA-Z_][a-zA-Z0-9_]*\b', text.lower())


def _compute_tf(tokens: List[str]) -> Dict[str, float]:
    """Term frequency for a single document."""
    tf: Dict[str, float] = {}
    for token in tokens:
        tf[token] = tf.get(token, 0) + 1
    total = len(tokens)
    return {k: v / total for k, v in tf.items()} if total else {}


def _compute_idf(corpus_tokens: List[List[str]]) -> Dict[str, float]:
    """Inverse Document Frequency across the entire corpus.

    IDF(t) = log(N / (1 + df(t))) where df(t) = number of docs containing term t.
    The +1 in denominator prevents division by zero.
    """
    n = len(corpus_tokens)
    if n == 0:
        return {}

    df: Dict[str, int] = {}
    for doc_tokens in corpus_tokens:
        unique_tokens = set(doc_tokens)
        for token in unique_tokens:
            df[token] = df.get(token, 0) + 1

    return {term: math.log(n / (1 + freq)) for term, freq in df.items()}


def _compute_tfidf(tf: Dict[str, float], idf: Dict[str, float]) -> Dict[str, float]:
    """Compute TF-IDF vector from TF and IDF dictionaries."""
    return {term: tf_val * idf.get(term, 0.0) for term, tf_val in tf.items()}


def _cosine_similarity(vec_a: Dict[str, float], vec_b: Dict[str, float]) -> float:
    """Cosine similarity between two sparse TF-IDF vectors."""
    shared_keys = set(vec_a.keys()) & set(vec_b.keys())
    if not shared_keys:
        return 0.0
    dot = sum(vec_a[k] * vec_b[k] for k in shared_keys)
    mag_a = sum(v * v for v in vec_a.values()) ** 0.5
    mag_b = sum(v * v for v in vec_b.values()) ** 0.5
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)


class RAGEngine:
    """Lightweight RAG engine using TF-IDF similarity (zero external deps).

    For production use with large document sets, swap this for ChromaDB
    or FAISS by replacing the `index()` and `retrieve()` methods.
    """

    SUPPORTED_EXTENSIONS = (".md", ".txt", ".json", ".yaml", ".yml",
                           ".py", ".js", ".ts", ".jsx", ".tsx",
                           ".html", ".css", ".go", ".rs")

    # Minimum relevance score threshold to avoid injecting noise
    MIN_SCORE_THRESHOLD: float = 0.01

    def __init__(self, docs_dir: str = "your_project/docs/reference",
                 chunk_size: int = 500):
        self.docs_dir = docs_dir
        self.chunk_size = chunk_size
        self.chunks: List[str] = []
        self.chunk_sources: List[str] = []  # source file for each chunk
        self.chunk_vectors: List[Dict[str, float]] = []
        self._idf: Dict[str, float] = {}
        self._index_hash: Optional[str] = None

    def _compute_dir_hash(self) -> str:
        """Computes a hash of all files in the docs directory for cache invalidation."""
        if not os.path.exists(self.docs_dir):
            return ""
        files_hash = hashlib.md5()
        for root, _, files in sorted(os.walk(self.docs_dir)):
            for fname in sorted(files):
                fpath = os.path.join(root, fname)
                files_hash.update(fname.encode())
                try:
                    files_hash.update(str(os.path.getmtime(fpath)).encode())
                except OSError:
                    pass
        return files_hash.hexdigest()

    def index(self) -> int:
        """Indexes all supported documents in the reference directory.

        Returns the number of chunks indexed.
        Uses proper TF-IDF: term frequency weighted by inverse document frequency.
        """
        if not os.path.exists(self.docs_dir):
            print(f"📚 RAG: No reference docs directory at {self.docs_dir}")
            return 0

        # Check if we need to re-index
        current_hash = self._compute_dir_hash()
        if current_hash == self._index_hash and self.chunks:
            print(f"📚 RAG: Index is up-to-date ({len(self.chunks)} chunks)")
            return len(self.chunks)

        self.chunks = []
        self.chunk_sources = []
        self.chunk_vectors = []
        self._idf = {}

        # Phase 1: Collect all chunk texts and their tokens
        all_chunk_tokens: List[List[str]] = []
        all_tf: List[Dict[str, float]] = []

        file_count = 0
        for root, _, files in os.walk(self.docs_dir):
            for fname in files:
                if not fname.endswith(self.SUPPORTED_EXTENSIONS):
                    continue
                fpath = os.path.join(root, fname)
                try:
                    with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                        content = f.read()

                    rel_path = os.path.relpath(fpath, self.docs_dir)
                    file_chunks = chunk_text(content, self.chunk_size)

                    for chunk in file_chunks:
                        tokens = _tokenize(chunk)
                        self.chunks.append(chunk)
                        self.chunk_sources.append(rel_path)
                        all_chunk_tokens.append(tokens)
                        all_tf.append(_compute_tf(tokens))

                    file_count += 1
                except Exception as e:
                    print(f"⚠️ RAG: Could not read {fpath}: {e}")

        # Phase 2: Compute IDF across all chunks
        self._idf = _compute_idf(all_chunk_tokens)

        # Phase 3: Compute TF-IDF vectors
        for tf in all_tf:
            self.chunk_vectors.append(_compute_tfidf(tf, self._idf))

        self._index_hash = current_hash
        print(f"📚 RAG: Indexed {file_count} files → {len(self.chunks)} chunks")
        return len(self.chunks)

    def retrieve(self, query: str, top_k: int = 5) -> str:
        """Retrieves the top-K most relevant chunks for a query.

        Uses TF-IDF weighted cosine similarity for accurate ranking.
        Returns a formatted string ready to inject into an LLM prompt.
        """
        if not self.chunks:
            return ""

        query_tokens = _tokenize(query)
        query_tf = _compute_tf(query_tokens)
        query_vec = _compute_tfidf(query_tf, self._idf)

        scored: List[Tuple[float, int]] = []
        for i, chunk_vec in enumerate(self.chunk_vectors):
            score = _cosine_similarity(query_vec, chunk_vec)
            if score > self.MIN_SCORE_THRESHOLD:
                scored.append((score, i))

        scored.sort(reverse=True)
        top = scored[:top_k]

        if not top:
            return ""

        context_parts = ["--- REFERENCE DOCUMENTS (RAG) ---"]
        for score, idx in top:
            source = self.chunk_sources[idx]
            context_parts.append(f"\n[Source: {source} | Relevance: {score:.3f}]")
            context_parts.append(self.chunks[idx])

        context_parts.append("--- END REFERENCE DOCUMENTS ---\n")
        return "\n".join(context_parts)

    def has_documents(self) -> bool:
        """Returns True if reference documents exist."""
        if not os.path.exists(self.docs_dir):
            return False
        return any(
            f.endswith(self.SUPPORTED_EXTENSIONS)
            for _, _, files in os.walk(self.docs_dir) for f in files
        )


# Singleton instance
_engine: Optional[RAGEngine] = None


def get_rag_context(query: str, docs_dir: str = "your_project/docs/reference",
                    top_k: int = 5) -> str:
    """Convenience function: indexes docs (if needed) and retrieves context.

    Safe to call even if no reference docs exist — returns empty string.
    """
    global _engine
    if _engine is None:
        _engine = RAGEngine(docs_dir)
    _engine.index()
    return _engine.retrieve(query, top_k)
