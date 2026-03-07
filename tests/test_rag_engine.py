"""Tests for scripts/rag_engine.py"""
import os
import tempfile
import shutil
import pytest
from scripts.rag_engine import (
    chunk_text, _tokenize, _compute_tf, _cosine_similarity,
    RAGEngine, get_rag_context,
)


class TestChunking:
    def test_small_text_single_chunk(self):
        text = "Hello world, this is a test."
        chunks = chunk_text(text, chunk_size=500)
        assert len(chunks) == 1
        assert "Hello world" in chunks[0]

    def test_large_text_multiple_chunks(self):
        text = ". ".join([f"Sentence number {i}" for i in range(100)])
        chunks = chunk_text(text, chunk_size=100)
        assert len(chunks) > 1

    def test_empty_text(self):
        chunks = chunk_text("", chunk_size=500)
        assert len(chunks) == 1


class TestTokenization:
    def test_simple_tokenize(self):
        tokens = _tokenize("Hello World 123 foo_bar")
        assert "hello" in tokens
        assert "world" in tokens
        assert "foo_bar" in tokens

    def test_empty_string(self):
        assert _tokenize("") == []


class TestTFIDF:
    def test_compute_tf(self):
        tf = _compute_tf(["hello", "hello", "world"])
        assert tf["hello"] == pytest.approx(2/3)
        assert tf["world"] == pytest.approx(1/3)

    def test_cosine_similarity_identical(self):
        vec = {"a": 1.0, "b": 0.5}
        assert _cosine_similarity(vec, vec) == pytest.approx(1.0)

    def test_cosine_similarity_orthogonal(self):
        vec_a = {"a": 1.0}
        vec_b = {"b": 1.0}
        assert _cosine_similarity(vec_a, vec_b) == 0.0

    def test_cosine_similarity_empty(self):
        assert _cosine_similarity({}, {"a": 1.0}) == 0.0


class TestRAGEngine:
    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        self.docs_dir = os.path.join(self.tmpdir, "reference")
        os.makedirs(self.docs_dir)

    def teardown_method(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_index_empty_directory(self):
        rag = RAGEngine(self.docs_dir)
        count = rag.index()
        assert count == 0

    def test_index_and_retrieve(self):
        # Create a reference document
        with open(os.path.join(self.docs_dir, "api_spec.md"), "w") as f:
            f.write("# User Authentication API\n\n"
                    "Use bcrypt for password hashing. "
                    "The login endpoint accepts POST /api/login with email and password. "
                    "Returns a JWT token on success.")

        rag = RAGEngine(self.docs_dir)
        count = rag.index()
        assert count > 0

        # Retrieve relevant context
        result = rag.retrieve("implement user authentication login")
        assert "REFERENCE DOCUMENTS" in result
        assert "bcrypt" in result or "login" in result

    def test_retrieve_no_match(self):
        with open(os.path.join(self.docs_dir, "api_spec.md"), "w") as f:
            f.write("Database schema uses PostgreSQL with UUID primary keys.")

        rag = RAGEngine(self.docs_dir)
        rag.index()
        result = rag.retrieve("xyzzy quantum flux capacitor")
        # Should return empty or minimal match
        assert isinstance(result, str)

    def test_has_documents_true(self):
        with open(os.path.join(self.docs_dir, "readme.md"), "w") as f:
            f.write("Some content")
        rag = RAGEngine(self.docs_dir)
        assert rag.has_documents() is True

    def test_has_documents_false(self):
        rag = RAGEngine(os.path.join(self.tmpdir, "nonexistent"))
        assert rag.has_documents() is False

    def test_cache_invalidation(self):
        with open(os.path.join(self.docs_dir, "v1.md"), "w") as f:
            f.write("Version 1 content")
        rag = RAGEngine(self.docs_dir)
        rag.index()
        count1 = len(rag.chunks)

        # Add another file
        with open(os.path.join(self.docs_dir, "v2.md"), "w") as f:
            f.write("Version 2 content with new features")
        rag.index()
        count2 = len(rag.chunks)
        assert count2 >= count1


class TestGetRagContext:
    def test_nonexistent_dir(self):
        result = get_rag_context("hello", docs_dir="/tmp/nonexistent_rag_test_dir")
        assert result == ""
