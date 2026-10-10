"""Keep unit tests database-independent unless an integration DB is explicitly configured."""
import os
os.environ.setdefault("DATABASE_URL", "sqlite://")
