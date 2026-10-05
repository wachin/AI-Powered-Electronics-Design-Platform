"""
FastAPI Backend for AI-Powered Electronics Design Platform.

Exposes the design orchestrator as a REST API for web frontend integration.
"""

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from pathlib import Path
import uuid
import asyncio
import json
from datetime import datetime

from src.agents.orchestrator import AIDesignOrchestrator, DesignRequest, DesignSummary
from src.components.database import ComponentDatabase
from src.collaboration.server import router as collaboration_router, handle_collaboration_websocket


app = FastAPI(
    title="AI Electronics Design Platform API",
    description="REST API for AI-powered electronics design: natural language → KiCad project",
    version="0.1.0",
)

# CORS for frontend development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173", "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory job storage (use Redis/DB in production)
jobs: Dict[str, Dict[str, Any]] = {}

# Global instances
db = ComponentDatabase()
orchestrator = AIDesignOrchestrator(db=db)


class DesignRequestModel(BaseModel):
    prompt: str = Field(..., description="Natural language circuit description", min_length=5)
    project_name: str = Field(default="ai_design", description="Project name for output files")
    run_spice: bool = Field(default=True, description="Run SPICE simulation")
    run_routing: bool = Field(default=True, description="Run PCB auto-routing")


class DesignResponseModel(BaseModel):
    job_id: str
    status: str
    message: str


class JobStatusModel(BaseModel):
    job_id: str
    status: str  # pending, running, completed, failed
    progress: int
    message: str
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    created_at: str
    updated_at: str


class ComponentSearchModel(BaseModel):
    query: str = Field(default="", description="Free-text search")
    category: Optional[str] = Field(default=None, description="Category filter")
    package: Optional[str] = Field(default=None, description="Package filter")
    min_stock: int = Field(default=0, description="Minimum stock")
    limit: int = Field(default=50, description="Max results")


class ComponentResultModel(BaseModel):
    mpn: str
    manufacturer: str
    category: str
    value: str
    package: str
    symbol: str
    footprint: str
    description: str
    stock: int
    price: float
    lcsc_part: Optional[str] = None
    is_basic: bool = False
    is_preferred: bool = False
    datasheet_url: str = ""
    product_url: str = ""


@app.get("/")
async def root():
    return {
        "name": "AI Electronics Design Platform API",
        "version": "0.1.0",
        "status": "running",
        "endpoints": {
            "design": "/api/design",
            "jobs": "/api/jobs/{job_id}",
            "components": "/api/components/search",
            "categories": "/api/components/categories",
        },
    }


@app.get("/health")
async def health():
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}


@app.post("/api/design", response_model=DesignResponseModel)
async def create_design(request: DesignRequestModel, background_tasks: BackgroundTasks):
    """Start a new design job."""
    job_id = str(uuid.uuid4())[:8]
    
    job = {
        "job_id": job_id,
        "status": "pending",
        "progress": 0,
        "message": "Job queued",
        "result": None,
        "error": None,
        "created_at": datetime.utcnow().isoformat(),
        "updated_at": datetime.utcnow().isoformat(),
    }
    jobs[job_id] = job
    
    # Run in background
    background_tasks.add_task(run_design_job, job_id, request)
    
    return DesignResponseModel(
        job_id=job_id,
        status="pending",
        message="Design job started. Poll /api/jobs/{job_id} for status.",
    )


async def run_design_job(job_id: str, request: DesignRequestModel):
    """Background task to run the design pipeline."""
    job = jobs[job_id]
    
    try:
        job["status"] = "running"
        job["progress"] = 10
        job["message"] = "Initializing design pipeline..."
        job["updated_at"] = datetime.utcnow().isoformat()
        
        # Create output directory
        output_dir = Path(f"./api_output/{job_id}")
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Create design request
        design_request = DesignRequest(
            prompt=request.prompt,
            project_name=request.project_name,
            run_spice=request.run_spice,
            run_routing=request.run_routing,
        )
        
        job["progress"] = 30
        job["message"] = "Running ERC validation and component selection..."
        job["updated_at"] = datetime.utcnow().isoformat()
        
        # Run orchestrator (sync but in background task)
        loop = asyncio.get_event_loop()
        summary = await loop.run_in_executor(
            None, orchestrator.process_request, design_request, output_dir
        )
        
        job["progress"] = 90
        job["message"] = "Generating output files..."
        job["updated_at"] = datetime.utcnow().isoformat()
        
        # Convert result to JSON-serializable
        result = summary.to_dict()
        
        job["status"] = "completed"
        job["progress"] = 100
        job["message"] = "Design completed successfully"
        job["result"] = result
        job["updated_at"] = datetime.utcnow().isoformat()
        
    except Exception as e:
        job["status"] = "failed"
        job["progress"] = 0
        job["message"] = f"Design failed: {str(e)}"
        job["error"] = str(e)
        job["updated_at"] = datetime.utcnow().isoformat()


@app.get("/api/jobs/{job_id}", response_model=JobStatusModel)
async def get_job_status(job_id: str):
    """Get job status and results."""
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    return JobStatusModel(**jobs[job_id])


@app.get("/api/jobs")
async def list_jobs():
    """List all jobs."""
    return {"jobs": [JobStatusModel(**j) for j in jobs.values()]}


@app.post("/api/components/search", response_model=List[ComponentResultModel])
async def search_components(request: ComponentSearchModel):
    """Search component database."""
    results = db.search(
        query=request.query,
        category=request.category,
        package=request.package,
        min_stock=request.min_stock,
        limit=request.limit,
    )
    return [ComponentResultModel(**r.to_dict()) for r in results]


@app.get("/api/components/categories")
async def get_categories():
    """Get available component categories."""
    return {"categories": db.get_categories()}


@app.get("/api/components/{mpn}")
async def get_component(mpn: str):
    """Get component by MPN or LCSC part number."""
    part = db.get_by_mpn(mpn)
    if not part:
        # Try as LCSC part
        part = db.get_by_lcsc(mpn)
    if not part:
        raise HTTPException(status_code=404, detail="Component not found")
    return ComponentResultModel(**part.to_dict())


# Include collaboration router
app.include_router(collaboration_router)

# WebSocket endpoint for real-time collaboration
@app.websocket("/api/collaboration/ws/{room_id}/{user_id}/{user_name}")
async def collaboration_websocket(websocket: WebSocket, room_id: str, user_id: str, user_name: str):
    await handle_collaboration_websocket(websocket, room_id, user_id, user_name)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)