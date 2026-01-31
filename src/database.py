from contextlib import contextmanager
from src.db.factory import make_database

_database = None # it is the global variable to store the database instance

def get_database(): 
    """Get or create the database instance."""
    global _database
    if _database is None:
        _database = make_database()
    return _database


