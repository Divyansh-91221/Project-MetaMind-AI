"""Text chunking for retrieval.

Metadata documentation is short and highly structured, so the chunker is paragraph-aware
rather than a blind character split: keeping a definition or a policy clause intact is what
makes citations meaningful.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from app.core.config import settings

_PARAGRAPH = re.compile(r"\n\s*\n")
_SENTENCE = re.compile(r"(?<=[.!?])\s+")


@dataclass(slots=True)
class Chunk:
    content: str
    index: int
    metadata: dict[str, Any] = field(default_factory=dict)


class TextChunker:
    """Splits text into overlapping, semantically coherent chunks."""

    def __init__(self, chunk_size: int | None = None, overlap: int | None = None) -> None:
        self.chunk_size = chunk_size or settings.rag_chunk_size
        self.overlap = overlap or settings.rag_chunk_overlap

    def split(self, text: str, *, metadata: dict[str, Any] | None = None) -> list[Chunk]:
        text = (text or "").strip()
        if not text:
            return []
        if len(text) <= self.chunk_size:
            return [Chunk(content=text, index=0, metadata=dict(metadata or {}))]

        chunks: list[Chunk] = []
        buffer = ""
        for block in self._blocks(text):
            if len(buffer) + len(block) + 2 <= self.chunk_size:
                buffer = f"{buffer}\n\n{block}".strip()
                continue
            if buffer:
                chunks.append(self._chunk(buffer, len(chunks), metadata))
            buffer = self._carry_over(buffer) + block if self.overlap else block

        if buffer:
            chunks.append(self._chunk(buffer, len(chunks), metadata))
        return chunks

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #
    def _blocks(self, text: str) -> list[str]:
        """Paragraphs first; oversized paragraphs fall back to sentences."""
        blocks: list[str] = []
        for paragraph in _PARAGRAPH.split(text):
            paragraph = paragraph.strip()
            if not paragraph:
                continue
            if len(paragraph) <= self.chunk_size:
                blocks.append(paragraph)
                continue
            sentence_buffer = ""
            for sentence in _SENTENCE.split(paragraph):
                if len(sentence_buffer) + len(sentence) + 1 <= self.chunk_size:
                    sentence_buffer = f"{sentence_buffer} {sentence}".strip()
                else:
                    if sentence_buffer:
                        blocks.append(sentence_buffer)
                    sentence_buffer = sentence[: self.chunk_size]
            if sentence_buffer:
                blocks.append(sentence_buffer)
        return blocks

    def _carry_over(self, buffer: str) -> str:
        """Tail of the previous chunk, kept so context is not lost at boundaries."""
        if not self.overlap or len(buffer) <= self.overlap:
            return ""
        return buffer[-self.overlap :].strip() + "\n\n"

    @staticmethod
    def _chunk(content: str, index: int, metadata: dict[str, Any] | None) -> Chunk:
        return Chunk(content=content.strip(), index=index, metadata=dict(metadata or {}))


chunker = TextChunker()
