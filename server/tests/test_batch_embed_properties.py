"""
Property-based tests for _batch_embed in server/knowledge_base.py.

Feature: Embedding batch processing optimization
Property 14: Batch partitioning — ⌈N/B⌉ batches, each ≤ B, union equals original

Validates: Requirements 9.1
"""

import math
import sys
from unittest.mock import MagicMock

from hypothesis import given, settings
from hypothesis import strategies as st

sys.path.insert(0, ".")

from server.data.knowledge_base import _batch_embed


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

_text_lists = st.lists(
    st.text(min_size=1, max_size=32, alphabet="abcdefghijklmnopqrstuvwxyz0123456789 "),
    min_size=0,
    max_size=200,
)
_batch_sizes = st.integers(min_value=1, max_value=64)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_recording_model():
    """Create a mock embeddings model that records each batch it receives."""
    model = MagicMock()
    model.recorded_batches = []

    def _embed(texts):
        model.recorded_batches.append(list(texts))
        return [[1.0, 2.0, 3.0] for _ in texts]

    model.embed_documents.side_effect = _embed
    return model


# ---------------------------------------------------------------------------
# Property 14: Batch partitioning
# ---------------------------------------------------------------------------

@given(texts=_text_lists, batch_size=_batch_sizes)
@settings(max_examples=50)
def test_batch_count_equals_ceil_n_over_b(texts: list[str], batch_size: int) -> None:
    """
    **Validates: Requirements 9.1**

    For N texts and batch_size B, the embeddings model should be called
    exactly ⌈N/B⌉ times.
    """
    model = _make_recording_model()
    _batch_embed(texts, model, batch_size=batch_size, delay_ms=0, max_retries=0)

    expected_batches = math.ceil(len(texts) / batch_size) if texts else 0
    assert model.embed_documents.call_count == expected_batches


@given(texts=_text_lists, batch_size=_batch_sizes)
@settings(max_examples=50)
def test_each_batch_size_at_most_b(texts: list[str], batch_size: int) -> None:
    """
    **Validates: Requirements 9.1**

    Each batch passed to embed_documents should have size ≤ B.
    """
    model = _make_recording_model()
    _batch_embed(texts, model, batch_size=batch_size, delay_ms=0, max_retries=0)

    for batch in model.recorded_batches:
        assert len(batch) <= batch_size


@given(texts=_text_lists, batch_size=_batch_sizes)
@settings(max_examples=50)
def test_union_of_batches_equals_original(texts: list[str], batch_size: int) -> None:
    """
    **Validates: Requirements 9.1**

    The concatenation of all batches should equal the original texts list
    (same order, no duplicates, no omissions).
    """
    model = _make_recording_model()
    _batch_embed(texts, model, batch_size=batch_size, delay_ms=0, max_retries=0)

    reconstructed = []
    for batch in model.recorded_batches:
        reconstructed.extend(batch)

    assert reconstructed == texts


@given(texts=_text_lists, batch_size=_batch_sizes)
@settings(max_examples=50)
def test_output_length_matches_input(texts: list[str], batch_size: int) -> None:
    """
    **Validates: Requirements 9.1**

    The returned vector list should have the same length as the input texts list.
    """
    model = _make_recording_model()
    result = _batch_embed(texts, model, batch_size=batch_size, delay_ms=0, max_retries=0)

    assert len(result) == len(texts)


def test_empty_input_produces_empty_output() -> None:
    """
    **Validates: Requirements 9.1**

    Empty texts list should produce empty output with zero batches.
    """
    model = _make_recording_model()
    result = _batch_embed([], model, batch_size=32, delay_ms=0, max_retries=0)

    assert result == []
    assert model.embed_documents.call_count == 0
