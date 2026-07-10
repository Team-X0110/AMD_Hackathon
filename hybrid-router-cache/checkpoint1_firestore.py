"""
checkpoint1_firestore.py — Phase 1 / Checkpoint 1 (Now Realtime DB!)

Verify Firebase connection before writing any pipeline code.
Run this FIRST after adding your firebase-key.json.

Usage:
    python checkpoint1_firestore.py
"""
import sys
import time
from src.cache.firestore_client import get_db

TEST_COLLECTION = "_connectivity_test"
TEST_DOC_ID = "ping"


def main():
    print("Connecting to Realtime Database...")
    db = get_db()

    print("Writing test document...")
    db.child(TEST_COLLECTION).child(TEST_DOC_ID).set({
        "test": True,
        "ts": int(time.time()),
    })

    print("Reading test document...")
    doc = db.child(TEST_COLLECTION).child(TEST_DOC_ID).get()
    if not isinstance(doc, dict) or not doc.get("test"):
        print("[FAIL] FAIL: document not found after write")
        sys.exit(1)

    print("Deleting test document...")
    db.child(TEST_COLLECTION).child(TEST_DOC_ID).delete()

    # Confirm deletion
    doc2 = db.child(TEST_COLLECTION).child(TEST_DOC_ID).get()
    if doc2 is not None:
        print("[FAIL] FAIL: document still exists after delete")
        sys.exit(1)

    print("\n[PASS] Checkpoint 1 PASSED — Realtime Database is connected and working.")


if __name__ == "__main__":
    main()
