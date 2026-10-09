"""UMAP to 2D, then a nested 3-level K-Means hierarchy (fine -> mid -> top).

Following Jay Alammar's approach: many small clusters first, then cluster the centroids
into coarser groups. Clustering in the 2D map space keeps every cluster a contiguous region,
so labels sit cleanly on the map at each zoom level.
"""
import numpy as np
import pandas as pd
import umap
from sklearn.cluster import KMeans

from common import CLUSTERS, EMBEDDINGS, PAPERS

N_FINE, N_MID, N_TOP = 150, 40, 10
SEED = 42


def cluster_centroids(points, labels, k):
    centroids = np.stack([points[labels == i].mean(axis=0) for i in range(k)])
    sizes = np.bincount(labels, minlength=k)
    return centroids, sizes


def main():
    df = pd.read_parquet(PAPERS)
    emb = np.load(EMBEDDINGS)
    assert len(df) == len(emb), "Re-run 02_embed.py after re-fetching papers"

    coords = umap.UMAP(n_neighbors=15, min_dist=0.05, metric="cosine", random_state=SEED).fit_transform(emb)

    fine = KMeans(N_FINE, random_state=SEED, n_init=10).fit_predict(coords)
    fine_c, fine_n = cluster_centroids(coords, fine, N_FINE)

    fine_to_mid = KMeans(N_MID, random_state=SEED, n_init=10).fit_predict(fine_c, sample_weight=fine_n)
    mid = fine_to_mid[fine]
    mid_c, mid_n = cluster_centroids(coords, mid, N_MID)

    mid_to_top = KMeans(N_TOP, random_state=SEED, n_init=10).fit_predict(mid_c, sample_weight=mid_n)
    top = mid_to_top[mid]

    out = pd.DataFrame({"pid": df["pid"], "x": coords[:, 0], "y": coords[:, 1], "fine": fine, "mid": mid, "top": top})
    out.to_parquet(CLUSTERS)
    print(f"Saved {CLUSTERS}: fine={N_FINE}, mid={N_MID}, top={N_TOP}")
    print("Top-level sizes:", np.bincount(top).tolist())


if __name__ == "__main__":
    main()
