# Global DB accessor and session context helper.

from contextlib import contextmanager 
from src.db.factory import make_database

# Global database instance 

def get_database(): 
    """Get or create database instance"""

    global _database # this is the global variable that will hold the database instance. It allows the function to access and modify the variable defined outside its scope.
    if _database is None: 
        _database = make_database()
    return _database

@contextmanager 
def get_db_session():
    """Get a database session context manager."""
    database = get_database() # Get the global database instance.
    with database.get_session() as session: # Use the database's get_session method to obtain a session context manager.
        yield session # Yield the session to the caller, allowing them to use it within a context manager.