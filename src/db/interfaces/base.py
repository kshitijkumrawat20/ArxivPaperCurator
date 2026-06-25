# Define database and repository contracts.

from abc import ABC, abstractmethod 
from typing import Any, ContextManager, Generator, Optional, List, Dict 
from sqlalchemy.orm import Session 

class BaseDatabase(ABC):
    """Base class for database operation. It defines the interface for database operations."""

    @abstractmethod # why abstractmethod? because it is a method that must be implemented by any subclass of BaseDatabase. It defines the interface for database operations, but does not provide an implementation. Subclasses must provide their own implementation of this method.
    def startup(self) -> None:
        """Initialize the database connection and create tables."""
    
    @abstractmethod
    def teardown(self) -> None:
        """Close the database connection and clean up resources."""

    @abstractmethod
    def get_session(self) -> ContextManager[Session]:
        """Get a database session."""
    

class BaseRepository(ABC):
    """Base class for repository operations. It defines the interface for repository operations."""

    def __init__(self, session: Session):
        self.session = session

    @abstractmethod
    def create(self, data: Dict[str, Any]) -> Any:
        """Create a new record in the database."""

    @abstractmethod
    def get_by_id(self, record_id: Any) -> Optional[Any]:
        """Retrieve a record by its ID."""

    @abstractmethod
    def update(self, record_id: Any, data: Dict[str, Any]) -> Optional[Any]:
        """Update a record by its ID."""
    
    @abstractmethod
    def delete(self, record_id: Any) -> bool:
        """Delete a record by its ID."""
    
    @abstractmethod 
    def list(self, limit: int = 100, offset: int = 0) -> List[Any]:
        """List records with pagination."""  
