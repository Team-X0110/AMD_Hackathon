"""
cache/semantic_cache.py — Local FAISS-based semantic cache with Firebase sync.
"""
from __future__ import annotations

import faiss
import numpy as np
from sentence_transformers import SentenceTransformer

from src.cache.firestore_client import get_db
from src.cache.exact_cache import normalize
from src.config import SEMANTIC_THRESHOLD

# ---------------------------------------------------------
# Module-level Initialization (Loads once on worker start)
# ---------------------------------------------------------
print("Loading local embedding model (all-MiniLM-L6-v2)...")
encoder = SentenceTransformer('all-MiniLM-L6-v2')
dimension = encoder.get_sentence_embedding_dimension()

# FAISS IndexFlatIP uses Inner Product. When vectors are L2-normalized, IP == Cosine Similarity.
index = faiss.IndexFlatIP(dimension)

# In-memory mapping of FAISS internal IDs to the cached document payloads
memory_map = {}
current_id = 0

def _get_embedding(text: str) -> np.ndarray:
    """Generates an L2-normalized embedding for cosine similarity."""
    emb = encoder.encode([text])[0]
    # Normalize to ensure Inner Product acts as Cosine Similarity
    faiss.normalize_L2(np.array([emb]))
    return np.array([emb])

def sync_from_firebase(collection: str):
    """
    Run this ONCE when the worker starts. 
    It pulls historical cache from Firebase and builds the fast FAISS index.
    """
    global current_id
    ref = get_db().child(collection)
    raw = ref.get()

    if not raw:
        print(f"No existing cache found in Firebase collection: {collection}")
        return

    print(f"Syncing {len(raw)} records from Firebase into FAISS...")
    for key, doc in raw.items():
        if isinstance(doc, dict) and "prompt" in doc:
            add_to_local_cache(doc["prompt"], doc, sync_to_db=False)
            
    print("FAISS index built successfully.")

def add_to_local_cache(query_text: str, doc_data: dict, sync_to_db: bool = True):
    """
    Embeds the prompt and stores it in the local FAISS index.
    Optionally syncs back to Firebase for persistence.
    """
    global current_id
    norm_text = normalize(query_text)
    embedding = _get_embedding(norm_text)
    
    index.add(embedding)
    memory_map[current_id] = doc_data
    current_id += 1
    
    # If this is a new subtask, save it to Firebase so it persists across restarts
    if sync_to_db:
        # Assuming you have a collection name setup in config
        collection = "semantic_cache" 
        get_db().child(collection).push(doc_data)

def semantic_lookup(query_text: str) -> tuple[dict | None, float]:
    """
    O(1) Search using the local FAISS index. Consumes 0 Fireworks tokens.
    """
    if current_id == 0:
        return None, 0.0

    norm_text = normalize(query_text)
    query_emb = _get_embedding(norm_text)
    
    # Search for the top 1 nearest neighbor
    k = 1
    distances, indices = index.search(query_emb, k)
    
    best_score = float(distances[0][0])
    best_index = int(indices[0][0])

    if best_score >= SEMANTIC_THRESHOLD and best_index != -1:
        return memory_map[best_index], best_score

    return None, best_score