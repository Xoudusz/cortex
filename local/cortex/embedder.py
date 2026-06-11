"""fastembed-based dense + sparse embeddings for cortex local mode."""

import os

os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
os.environ.setdefault("HF_HUB_DISABLE_IMPLICIT_TOKEN", "1")

from .config import EMBED_MODEL

_dense = None
_sparse = None


def _check_numpy() -> None:
    try:
        import numpy  # noqa: F401
    except RuntimeError as e:
        if "X86_V2" in str(e) or "baseline" in str(e).lower():
            raise RuntimeError(
                f"NumPy requires CPU features your machine lacks.\n"
                f'Reinstall with: pipx install "cortex-local[legacy]"\n'
                f"(Original error: {e})"
            ) from None
        raise


def embed(text: str) -> list:
    """Dense embedding via fastembed nomic-embed-text (768 dims)."""
    _check_numpy()
    global _dense
    if _dense is None:
        from fastembed import TextEmbedding
        _dense = TextEmbedding(EMBED_MODEL)
    return list(_dense.embed([text[:4000]]))[0].tolist()


def sparse_embed(text: str) -> tuple:
    """BM25 sparse embedding via fastembed (indices, values)."""
    global _sparse
    if _sparse is None:
        from fastembed import SparseTextEmbedding
        _sparse = SparseTextEmbedding("Qdrant/bm25")
    e = list(_sparse.embed([text[:4000]]))[0]
    return e.indices.tolist(), e.values.tolist()


def pull_models() -> None:
    """Pre-download embedding models (run at install time)."""
    print("Pulling fastembed models (this may take a few minutes on first run)...")
    print("  [1/2] Downloading nomic-embed-text-v1.5 (~270 MB)...", flush=True)
    embed("warmup")
    print("  [2/2] Downloading BM25 sparse model...", flush=True)
    sparse_embed("warmup")
    print("Models ready.")
