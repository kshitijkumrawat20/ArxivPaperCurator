from abc import ABC, abstractmethod 
from typing import List, Optional, Any, ContextManager, Dict, Tuple
from sqlalchemy.orm import Session

class BaseDatabase(ABC): # abstract base class for database interactions 

    @abstractmethod
    def startup(self) -> None:
        """Initializes the database connection and performs any necessary setup."""

    @abstractmethod
    def teardown(self) -> None:
        """Closes the database connection and performs any necessary cleanup."""
    
    @abstractmethod
    def get_session(self) -> ContextManager[Session]:
        """Provides a database session for executing queries."""

class BaseRepository(ABC): # abstract base class for repository pattern
    
    """
    Abstract base class for repository pattern

    """
    def __init__(self, session: Session):
        self.session = session 

    @abstractmethod
    def create(self, data: Dict[str, Any]) -> Any:
        """Creates a new record in the database."""

    @abstractmethod
    def get_by_id(self, record_id: Any) -> Optional[Any]:
        """Retrieves a record by its ID."""
    
    @abstractmethod
    def update(self, record_id: Any, data: Dict[str, Any]) -> Optional[Any]:
        """Updates an existing record in the database."""

    @abstractmethod
    def delete(self, record_id: Any) -> bool:
        """Deletes a record from the database."""

    @abstractmethod
    def list(self, limit: int = 100, offset: int = 0 ) -> List[Any]: 
        """Lists records from the database with pagination.
        Args: 
            limit (int): Maximum number of records to return.
            offset (int): Number of records to skip before starting to collect the result set.
        Returns:
            List[Any]: A list of records.
        
        """

        

    