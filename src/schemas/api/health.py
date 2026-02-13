from typing import List , Optional, Dict
from pydantic import BaseModel, Field

class ServiceStatus(BaseModel):
    """Individual service schema."""

    status: str = Field(..., description="Service status", examples=["healthy", "ok", "error"])
    detail: Optional[str] = Field(None, description="Status detail message", examples=["Connected to database successfully"])


class HealthResponse(BaseModel):
    """Health check response schema."""
    status: str = Field(..., description="Overall system status", examples=["ok", "degraded", "error"])
    version: str = Field(..., description="Version of the application", examples=["0.1.0"])
    environment: str = Field(..., description="Environment the application is running in", examples=["production", "development"])
    service_name: str = Field(..., description="Name of the service", examples=["arxiv-rag-api-service"])
    services: Optional[Dict[str, ServiceStatus]] = Field(None, description="Statuses of individual services")

    class Config: 
        """Pydantic configuration."""
        json_schema_extra = {
            "example": {
                "status": "ok",
                "version": "0.1.0",
                "environment": "production",
                "servicename": "arxiv-rag-api-service",
                "services": {
                    "database": {
                        "status": "healthy",
                        "message": "Connected to database successfully"
                    }
                }
            }
        }
