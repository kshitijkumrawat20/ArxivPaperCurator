import logging 
logger  = logging.getLogger(__name__)


def log_request(method: str, path: str) -> None:
    """Log incoming HTTP requests."""
    logger.info(f"Incoming request: {method} {path}")

def error_log(error: str,method: str, path: str) -> None: 
    """Simple error logging middleware."""
    logger.error(f"Error occurred: {error} during {method} {path}")