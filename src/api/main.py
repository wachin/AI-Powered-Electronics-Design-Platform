"""
FastAPI Backend for AI-Powered Electronics Design Platform.

Exposes the design orchestrator as a REST API for web frontend integration.
"""

from fastapi import FastAPI, HTTPException, BackgroundTasks, Query, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from contextlib import asynccontextmanager
from pathlib import Path
import uuid
import asyncio
import threading
from datetime import datetime

from src.agents.orchestrator import AIDesignOrchestrator, DesignRequest
from src.components.database import ComponentDatabase
from src.collaboration.server import router as collaboration_router, handle_collaboration_websocket


# In-memory job storage (use Redis/DB in production)
jobs: Dict[str, Dict[str, Any]] = {}

# Global instances
db = ComponentDatabase()
orchestrator = AIDesignOrchestrator(db=db)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """
    Parse the component catalog in the background as the API starts.

    Building the parametric index takes a few seconds for 180,000 parts, so
    doing it here keeps that cost off the first user-visible search. A daemon
    thread is used so that a failure to build — or a missing catalog — cannot
    stop the API from serving requests; the search simply falls back.
    """
    threading.Thread(target=db.warm, name="catalog-warm", daemon=True).start()
    yield


app = FastAPI(
    title="AI Electronics Design Platform API",
    description="REST API for AI-powered electronics design: natural language → KiCad project",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS for frontend development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173", "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


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
    query: str = Field(
        default="",
        description=(
            "Query. Values are matched numerically: '10k 0603' returns 10 kΩ "
            "parts, not 110 kΩ; '100nF 50V' matches the 50 V rating as a "
            "minimum. Names such as 'esp32' fall back to a text search."
        ),
    )
    category: Optional[str] = Field(default=None, description="Category filter")
    package: Optional[str] = Field(default=None, description="Package filter")
    min_stock: int = Field(default=0, description="Minimum stock")
    limit: int = Field(default=50, description="Max results")
    sort: str = Field(default="stock", description="stock | price | value")


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
    attributes: Dict[str, Any] = Field(default_factory=dict)
    # The distributor's own ordering figures. `min_order` matters when a bill of
    # materials is turned into an order: it is not always 1.
    min_order: int = 1
    attrition: Dict[str, Any] = Field(default_factory=dict)


class ComponentSearchResponseModel(BaseModel):
    """
    Search results together with how the query was interpreted.

    The interpretation is returned because a parametric search that silently
    understood the wrong thing is worse than one that returns nothing: the user
    sees "10k, package 0603" and can tell immediately if that is not what they
    asked for.
    """

    components: List[ComponentResultModel]
    notes: List[str] = Field(default_factory=list)
    interpretation: str = ""
    source: str = ""


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
            "substitutes": "/api/components/{lcsc}/substitutes",
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


@app.post("/api/components/search", response_model=ComponentSearchResponseModel)
async def search_components(request: ComponentSearchModel):
    """
    Search the component catalog.

    Returns the interpretation alongside the results so the UI can show what the
    search understood rather than presenting an unexplained list.
    """
    outcome = db.search_explained(
        query=request.query,
        category=request.category,
        package=request.package,
        min_stock=request.min_stock,
        limit=request.limit,
        sort=request.sort,
    )
    return ComponentSearchResponseModel(
        components=[ComponentResultModel(**c) for c in outcome["components"]],
        notes=outcome["notes"],
        interpretation=outcome["interpretation"],
        source=outcome["source"],
    )


@app.get("/api/components/categories")
async def get_categories():
    """
    Available component categories.

    ``categories`` are the names search accepts, with their part counts;
    ``catalog_categories`` are the catalogue's own broader category names, shown
    for reference.
    """
    return {
        "categories": db.get_categories(),
        "category_counts": db.internal_category_counts(),
        "catalog_categories": db.catalog_category_counts(),
    }


@app.post("/api/components/warm")
async def warm_component_index():
    """
    Build the parametric index ahead of the first search.

    Building it takes a few seconds for 180,000 parts; doing it here means the
    first real search is fast. Called on startup by the API itself.
    """
    return {"indexed": db.warm()}


@app.get("/api/components/{lcsc}/substitutes")
async def get_substitutes(
    lcsc: str,
    limit: int = Query(default=10, ge=1, le=50),
    min_stock: Optional[int] = Query(default=None, ge=0),
    same_package: bool = Query(default=True),
):
    """
    Parts that can replace the given part, with the checks that were made.

    Each result carries ``reasons`` (what matched) and ``caveats`` (what
    differs or could not be verified). An empty list means no numeric
    comparison was possible, not that no part exists.
    """
    substitutes = db.find_substitutes(
        lcsc, limit=limit, min_stock=min_stock, same_package=same_package
    )
    if not substitutes:
        return {
            "lcsc_part": lcsc,
            "substitutes": [],
            "notes": [
                "No comparable part found. Either the catalog is not installed, "
                "or the part has no numeric specification to compare on."
            ],
        }
    return {
        "lcsc_part": lcsc,
        "substitutes": substitutes,
        "notes": [
            "A substitute is a candidate, not a guarantee: verify the "
            "datasheet, particularly the pinout, before ordering."
        ],
    }


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