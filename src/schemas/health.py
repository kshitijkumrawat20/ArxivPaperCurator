from typing import List , Optional, Dict
from pydantic import BaseModel, Field

class ServiceStatus(BaseModel):
    """Individual service  schema."""

    status : str = Field(..., description="service status", examples="healthy")
    message: Optional[str] = Field(..., description="Status message", example = "Connected to database successfully")


class HealthResponse(BaseModel):
    """Health check response schema."""
    status : str = Field (..., description="Overall system status", example="ok")
    version: str = Field(..., description="Version of the application", example="0.1.0")
    environment: str = Field(..., description="Environment the application is running in", example="production")
    servicename :  str = Field(..., description="Name of the service", example="arxiv-rag-api-service")
    services : Optional[Dict[str, ServiceStatus]] = Field(None, description="Statuses of individual services")

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
