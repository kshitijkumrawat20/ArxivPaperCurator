from typing  import Dict, Optional 
from pydantic import BaseModel, Field 

class ServiceStatus(BaseModel): 
    """Individual service status"""

    status: str = Field(..., description= "Service status", example= "healthy")
    message: Optional[str] = Field(None, description= "Additional message about the service status", example= "connected successfully")

class healthResponse(BaseModel):
    """Health check response model"""

    status: str = Field(..., description= "Overall health status of the application", example= "ok")
    version: str = Field(..., description= "Application version", example= "1.0.0")
    environment: str = Field(..., description= "Application environment", example= "production")
    service_name: str = Field(..., description= "Name of the service", example= "my_service")
    services: Optional[Dict[str, ServiceStatus]] = Field(None, description= "Dictionary of individual service statuses", example= {"database": {"status": "healthy", "message": "connected successfully"}})

    class Config:
        """Pydantic configuration for healthResponse model"""
        json_schema_extra = {
            "example" : {
                "status": "ok",
                "version": "1.0.0",
                "environment": "production",
                "service_name": "rag_service",
                "services": {
                    "database": {
                        "status": "healthy",
                        "message": "connected successfully"
                    },
                    "pdf_parser": {
                        "status": "healthy",
                        "message": "Docling parser is working"
                    },
                }
            }
        }