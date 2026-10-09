"""Embed title + abstract with a local sentence-transformers model (no API cost)."""
import os

import numpy as np
import pandas as pd
import torch
from sentence_transformers import SentenceTransformer

from common import EMBEDDINGS, PAPERS

MODEL = os.environ.get("NEURIPS_EMBED_MODEL", "BAAI/bge-base-en-v1.5")


def main():
    df = pd.read_parquet(PAPERS)
    device = "mps" if torch.backends.mps.is_available() else "cuda" if torch.cuda.is_available() else "cpu"
    model = SentenceTransformer(MODEL, device=device)
    texts = (df["title"] + ". " + df["abstract"]).tolist()
    emb = model.encode(texts, batch_size=32, show_progress_bar=True, normalize_embeddings=True)
    np.save(EMBEDDINGS, emb.astype(np.float32))
    print(f"Saved embeddings {emb.shape} -> {EMBEDDINGS}")


if __name__ == "__main__":
    main()
