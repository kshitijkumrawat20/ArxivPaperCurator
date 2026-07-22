# Start with the simplest endpoint.

from fastapi import APIRouter
from sqlalchemy.orm import Session 
from ..dependencies import DatabaseDep, SettingsDep, OpenSearchDep
from ..schema.api.health import healthResponse, ServiceStatus 
from ..services.ollama import OllamaClient 
from sqlalchemy import text
from ..exception import OllamaConnectionError, OllamaException, OllamaTimeoutError
router = APIRouter()

# @router.get("/ping", tags=["Health Check"])
# async def ping():
#     """Simple health check endpoint to verify that the service is running."""
#     return {"status": "ok", "message": "pong"}

@router.get("/health", response_model=healthResponse, tags=["Health Check"])
async def health_check(settings: SettingsDep, database: DatabaseDep, opensearch_client: OpenSearchDep) -> healthResponse:
    """
    Comprehensive health check endpoint for monitoring and load balancer probes.

    :returns: healthResponse object containing the overall status and individual service statuses
    :rtype: healthResponse
    """
    services = {}
    overall_status = "ok"

    # try: 
    def _check_services(name: str, check_func, *args, **kwargs):
        """Helper to standardize service health checks """
        try: 
            if kwargs.get("is_async"): # means the check_func is async 
                # handle async function seperately in the calling code 
                return check_func(*args)
            result = check_func(*args)
            services[name] = result
            if result.status !="healthy":
                nonlocal overall_status
                overall_status = "degraded"

        except Exception as e: 
            services[name] = ServiceStatus(status="unhealthy", message={str(e)}, overall_status="degraded")
    def _check_database():
        with database.get_session() as session: 
            # simply checking database connectivity by executing a simple query
            session.execute(text("SELECT 1"))
            return ServiceStatus(status="healthy", message="Database is reachable.")
        
    def _check_opensearch():
        if not opensearch_client.health_check():
            return ServiceStatus(status="unhealthy", message="OpenSearch is not reachable.")
        stats = opensearch_client.get_index_stats()
        return ServiceStatus(status="healthy", message=f"Index '{stats.get('index_name', 'unknown')}' has {stats.get('document_count', 0)} documents.")
    
    # Run synchronous checks 
    _check_services("database", _check_database)
    _check_services("opensearch", _check_opensearch)


    # handle ollama async check seperately  
    try: 
        ollama_client  = OllamaClient(settings)
        ollama_health = await ollama_client.health_check()
        services["ollama"] = ServiceStatus(status=ollama_health["status"], message=ollama_health["message"])
        if ollama_health["status"] != "healthy":
            overall_status = "degraded"
    except Exception as e: 
        services["ollama"] = ServiceStatus(status="unhealthy", message=str(e))
        overall_status = "degraded"
        

    return healthResponse(
        status=overall_status,
        version=settings.app_version,
        environment=settings.environment,
        service_name=settings.service_name,
        services=services
    )