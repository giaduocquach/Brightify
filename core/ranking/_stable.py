"""Cross-platform reproducible descending argsort — shared by the recommender
facade and the extracted ranking helpers (coherence/journey)."""
import numpy as np


def argsort_desc_stable(scores, k=None):
    """Descending argsort that is reproducible across CPU/BLAS platforms.

    Ranking scores are float32 BLAS products (e.g. MERT/MuQ cosine @ centroid),
    whose last bits differ between arm64 (Apple Accelerate) and amd64 (OpenBLAS).
    A bare ``np.argsort(x)[::-1]`` is non-stable, so those ~1e-7 differences flip
    near-tied songs and the same color returns a slightly different order per host.
    Rounding absorbs the ULP noise; a stable sort then keeps ascending index order
    for equal-rounded scores (a fixed tie-break) → identical output everywhere.
    """
    rounded = np.round(np.asarray(scores, dtype=np.float64), 6)
    order = np.argsort(-rounded, kind='stable')
    return order[:k] if k is not None else order
