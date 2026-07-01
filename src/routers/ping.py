# Start with the simplest endpoint.

from fastapi import APIRouter
from sqlalchemy.orm import Session 
from ..dependencies import DatabaseDep, SettingsDep
from ..schema.api.health import healthResponse, ServiceStatus 
from ..services.ollama import OllamaClient 
from sqlalchemy import text
from ..exception import OllamaConnectionError, OllamaException, OllamaTimeoutError
router = APIRouter()

@router.get("/ping", tags=["Health Check"])
async def ping():
    """Simple health check endpoint to verify that the service is running."""
    return {"status": "ok", "message": "pong"}

@router.get("/health", response_model=healthResponse, tags=["Health Check"])
async def health_check(settings: SettingsDep, database: DatabaseDep) -> healthResponse:
    """
    Comprehensive health check endpoint for monitoring and load balancer probes.

    This endpoint provides information about the service health, version,
    environment, and checks connectivity to dependent services like database.

    Returns:
        HealthResponse: Contains service status, version, environment, and service checks

    Example:
        Response:
        ```
        {
            "status": "ok",
            "version": "0.1.0",
            "environment": "development",
            "service_name": "rag-api",
            "services": {
                "database": {"status": "healthy", "message": "Connected successfully"}
            }
        }
        ```
    """
    services = { }
    overall_status = "ok"

    try: 
        with database.get_session() as session: 
            # simply checking database connectivity by executing a simple query
            session.execute(text("SELECT 1"))
            services["database"] = ServiceStatus(status="healthy", message="Connected successfully")
    except Exception as e:
        services["database"] = ServiceStatus(status="unhealthy", message=f"Database connection failed: {str(e)}")
        overall_status = "degraded"
    
    # testing ollama service health checks 
    try: 
        ollama_client  = OllamaClient(settings)
        ollama_health = await ollama_client.health_check()
        services["ollama"] = ServiceStatus(status=ollama_health["status"], message=ollama_health["message"])
        if ollama_health["status"] != "healthy":
            overall_status = "degraded"
    except OllamaConnectionError as e:
        services["ollama"] = ServiceStatus(status="unhealthy", message=f"Cannot connect to Ollama: {str(e)}")
        overall_status = "degraded"
    except OllamaTimeoutError as e:
        services["ollama"] = ServiceStatus(status="unhealthy", message=f"Ollama timeout: {str(e)}")
        overall_status = "degraded"
    except OllamaException as e:
        services["ollama"] = ServiceStatus(status="unhealthy", message=f"Ollama error: {str(e)}")
        overall_status = "degraded"
    except Exception as e:
        services["ollama"] = ServiceStatus(status="unhealthy", message=f"Unexpected Ollama error: {str(e)}")
        overall_status = "degraded"

    return healthResponse(
        status=overall_status,
        version=settings.app_version,
        environment=settings.environment,
        service_name=settings.service_name,
        services=services
    )