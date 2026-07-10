"""
cache/firestore_client.py — Now actually connects to Realtime Database!

(Keeping filename to avoid breaking other imports, but this returns a firebase_admin.db reference).
"""
from __future__ import annotations
import os

import firebase_admin
from firebase_admin import credentials, db

from src.config import FIREBASE_KEY_PATH, FIREBASE_PROJECT_ID

_app_initialized = False

# Your realtime database URL based on the error output earlier
RTDB_URL = "https://amd-hackathon-c23d8-default-rtdb.asia-southeast1.firebasedatabase.app"

def get_db():
    """
    Return the Realtime Database root reference.
    """
    global _app_initialized

    if not _app_initialized and not firebase_admin._apps:
        key_path = FIREBASE_KEY_PATH.strip()
        key_file_exists = key_path and os.path.isfile(key_path)

        if key_file_exists:
            print(f"[rtdb] Initializing with service account: {key_path}")
            cred = credentials.Certificate(key_path)
            firebase_admin.initialize_app(cred, {
                'databaseURL': RTDB_URL
            })
        else:
            raise RuntimeError("Missing firebase-key.json")
        
        _app_initialized = True

    return db.reference('/')
