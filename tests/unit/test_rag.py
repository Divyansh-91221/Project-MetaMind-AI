"""RAG layer tests: chunking, embeddings and the vector store abstraction."""

from __future__ import annotations

import uuid

import pytest

from app.core.constants import DocumentType
from app.rag.chunking import TextChunker
from app.rag.embeddings import HashEmbeddingProvider, cosine_similarity
from app.rag.vector_store import InMemoryVectorStore, VectorRecord

pytestmark = pytest.mark.unit


class TestChunking:
    def test_short_text_is_a_single_chunk(self) -> None:
        chunks = TextChunker(chunk_size=500, overlap=50).split("A short description.")
        assert len(chunks) == 1
        assert chunks[0].index == 0

    def test_empty_text_produces_no_chunks(self) -> None:
        assert TextChunker().split("   ") == []

    def test_long_text_is_split(self) -> None:
        text = "\n\n".join(f"Paragraph {i}. " + "word " * 40 for i in range(10))
        chunks = TextChunker(chunk_size=300, overlap=40).split(text)
        assert len(chunks) > 1
        assert all(chunk.content for chunk in chunks)

    def test_chunk_indexes_are_sequential(self) -> None:
        text = "\n\n".join(f"Paragraph {i}. " + "word " * 40 for i in range(10))
        chunks = TextChunker(chunk_size=300, overlap=40).split(text)
        assert [chunk.index for chunk in chunks] == list(range(len(chunks)))

    def test_metadata_is_attached_to_every_chunk(self) -> None:
        text = "\n\n".join(f"Paragraph {i}. " + "word " * 40 for i in range(6))
        chunks = TextChunker(chunk_size=250, overlap=30).split(text, metadata={"urn": "x"})
        assert all(chunk.metadata["urn"] == "x" for chunk in chunks)

    def test_oversized_paragraph_falls_back_to_sentences(self) -> None:
        text = " ".join(f"Sentence number {i} about revenue." for i in range(80))
        chunks = TextChunker(chunk_size=200, overlap=20).split(text)
        assert len(chunks) > 1


class TestHashEmbeddings:
    async def test_embedding_has_the_configured_dimension(self) -> None:
        provider = HashEmbeddingProvider(dimension=128)
        assert len(await provider.embed_one("customer revenue")) == 128

    async def test_embeddings_are_deterministic(self) -> None:
        """Reproducibility is what makes the offline provider usable in tests."""
        provider = HashEmbeddingProvider(dimension=128)
        assert await provider.embed_one("customer") == await provider.embed_one("customer")

    async def test_batch_embedding_matches_single(self) -> None:
        provider = HashEmbeddingProvider(dimension=64)
        batch = await provider.embed(["a", "b"])
        assert batch[0] == await provider.embed_one("a")
        assert len(batch) == 2

    async def test_empty_batch_returns_empty(self) -> None:
        assert await HashEmbeddingProvider(dimension=64).embed([]) == []

    async def test_empty_text_yields_a_zero_vector(self) -> None:
        provider = HashEmbeddingProvider(dimension=32)
        assert await provider.embed_one("") == [0.0] * 32

    async def test_shared_tokens_score_higher_than_unrelated_text(self) -> None:
        provider = HashEmbeddingProvider(dimension=512)
        query = await provider.embed_one("monthly revenue kpi")
        related = await provider.embed_one("monthly revenue for each customer")
        unrelated = await provider.embed_one("shipping address postal code")
        assert cosine_similarity(query, related) > cosine_similarity(query, unrelated)


class TestCosineSimilarity:
    def test_identical_vectors_score_one(self) -> None:
        assert cosine_similarity([1.0, 0.0], [1.0, 0.0]) == pytest.approx(1.0)

    def test_orthogonal_vectors_score_zero(self) -> None:
        assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)

    def test_mismatched_dimensions_score_zero(self) -> None:
        assert cosine_similarity([1.0], [1.0, 0.0]) == 0.0

    def test_zero_vector_scores_zero(self) -> None:
        assert cosine_similarity([0.0, 0.0], [1.0, 0.0]) == 0.0


class TestInMemoryVectorStore:
    @pytest.fixture
    async def store(self) -> InMemoryVectorStore:
        store = InMemoryVectorStore()
        provider = HashEmbeddingProvider(dimension=256)
        document_id = uuid.uuid4()
        contents = {
            "urn:emc:table:snowflake:snowflake.sales": "Monthly sales fact table with revenue.",
            "urn:emc:table:sap:sap.customer": "SAP customer master record with names.",
        }
        await store.upsert(
            [
                VectorRecord(
                    content=text,
                    embedding=await provider.embed_one(text),
                    document_id=document_id,
                    document_title=urn,
                    document_type=DocumentType.METADATA_DESCRIPTION,
                    entity_urn=urn,
                )
                for urn, text in contents.items()
            ]
        )
        return store

    async def test_search_ranks_the_relevant_asset_first(self, store: InMemoryVectorStore) -> None:
        provider = HashEmbeddingProvider(dimension=256)
        matches = await store.search(await provider.embed_one("revenue"), top_k=2)
        assert matches[0].entity_urn == "urn:emc:table:snowflake:snowflake.sales"

    async def test_top_k_is_respected(self, store: InMemoryVectorStore) -> None:
        provider = HashEmbeddingProvider(dimension=256)
        matches = await store.search(await provider.embed_one("revenue"), top_k=1)
        assert len(matches) == 1

    async def test_entity_scoping_restricts_results(self, store: InMemoryVectorStore) -> None:
        provider = HashEmbeddingProvider(dimension=256)
        matches = await store.search(
            await provider.embed_one("revenue"),
            top_k=5,
            entity_urns=["urn:emc:table:sap:sap.customer"],
        )
        assert {match.entity_urn for match in matches} == {"urn:emc:table:sap:sap.customer"}

    async def test_document_type_filter_excludes_others(self, store: InMemoryVectorStore) -> None:
        provider = HashEmbeddingProvider(dimension=256)
        matches = await store.search(
            await provider.embed_one("revenue"),
            top_k=5,
            document_types=[DocumentType.GOVERNANCE_POLICY],
        )
        assert matches == []

    async def test_clear_empties_the_index(self, store: InMemoryVectorStore) -> None:
        provider = HashEmbeddingProvider(dimension=256)
        await store.clear()
        assert await store.search(await provider.embed_one("revenue")) == []
