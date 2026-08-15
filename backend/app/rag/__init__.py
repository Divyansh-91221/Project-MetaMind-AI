"""Retrieval-augmented generation layer: embeddings, chunking, vector store, retrieval."""

from app.rag.chunking import Chunk, TextChunker
from app.rag.document_loader import DocumentLoader, LoadedDocument
from app.rag.embeddings import (
    EmbeddingProvider,
    HashEmbeddingProvider,
    get_embedding_provider,
    set_embedding_provider,
)
from app.rag.rag_pipeline import IndexingReport, RAGPipeline
from app.rag.retriever import Retriever
from app.rag.vector_store import (
    InMemoryVectorStore,
    PgVectorStore,
    VectorMatch,
    VectorRecord,
    VectorStore,
    get_vector_store,
)

__all__ = [
    "Chunk",
    "DocumentLoader",
    "EmbeddingProvider",
    "HashEmbeddingProvider",
    "InMemoryVectorStore",
    "IndexingReport",
    "LoadedDocument",
    "PgVectorStore",
    "RAGPipeline",
    "Retriever",
    "TextChunker",
    "VectorMatch",
    "VectorRecord",
    "VectorStore",
    "get_embedding_provider",
    "get_vector_store",
    "set_embedding_provider",
]
