import os
import sys

# Ensure the project root is on sys.path so `import src...` works when pytest is run
# from either the repository root or the hybrid-router-cache subfolder.
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)
