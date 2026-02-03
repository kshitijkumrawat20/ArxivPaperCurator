from fastapi import APIRouter
from sqlalchemy import text 
from ..dependencies import DatabaseDep , SettingDep
from ..schemas.health import HealthResponse, ServiceStatus
from ..services.ollama import OllamaClient 

router = APIRouter(prefix="/ping", tags=["health"])

@router.get("/ping", tags=["health"])
async def ping():
    """Simple ping endpoint to check if the service is running."""
    return {"status": "ok", "message": "pong"}

@router.get("/health", response_model=HealthResponse,description="Check the health of the services including database and ollama", response_description="Health check response", tags=["health"])
async def health_check(
    settings : SettingDep,
    database: DatabaseDep
):
    """
    Health check endpoint to verify the status of the service components.

    """
    services = {}
    overall_status = "ok"

    try:
        ## test database connectivity
        with database.engine.connect() as conn:
            conn.execute(text("SELECT 1"))
            services["database"] = ServiceStatus(status="ok", detail="Database connection successful.")
    except Exception as e:
        services["database"] = ServiceStatus(status="error", detail=f"Database connection failed: {str(e)}")
        overall_status = "error"
    
    # ollama connectivity check
    try:    
        ollama_client = OllamaClient(settings)
        ollama_health = await ollama_client.health_check()
        services["ollama"] = ServiceStatus(status="ok", detail="Ollama service is reachable.")
        if ollama_health["status"] != "healthy":
            overall_status = "degraded"
    except Exception as e:
        services["ollama"] = ServiceStatus(status="unhealthy", detail=f"Ollama service is not reachable: {str(e)}")
        overall_status = "degraded"

    return HealthResponse(
        status=overall_status,
        services=services,
        version = settings.app_version, 
        environment= settings.environment,
        service_name= settings.service_name
    )

