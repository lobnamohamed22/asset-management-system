import os
import time
from collections import defaultdict
from typing import List, Optional
from uuid import UUID
from fastapi import FastAPI, Depends, HTTPException, status, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app import database, models, schemas, auth, crud

# Initialize Database tables if not using Alembic (useful for quick starts / tests)
# models.Base.metadata.create_all(bind=database.engine)

import urllib.request
from fastapi.staticfiles import StaticFiles

app = FastAPI(
    title="Asset Management System",
    description="A simple, beginner-friendly Asset Management API built with FastAPI.",
    version="1.0.0",
)

# Download vis-network.min.js locally on startup to bypass browser tracking preventions
static_dir = os.path.join(os.path.dirname(__file__), "static")
os.makedirs(static_dir, exist_ok=True)
js_path = os.path.join(static_dir, "vis-network.min.js")
if not os.path.exists(js_path):
    print("Downloading vis-network.min.js locally...")
    url = "https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"
    try:
        urllib.request.urlretrieve(url, js_path)
        print("Download complete!")
    except Exception as e:
        print(f"Warning: Failed to download vis-network.min.js locally: {e}")

# Mount static folder
app.mount("/static", StaticFiles(directory=static_dir), name="static")

@app.on_event("startup")
def startup_populate_db():
    """Automatically seeds default integrationuser and sample assets if database is empty."""
    if os.getenv("TESTING") == "True":
        return
    db = database.SessionLocal()
    try:
        # Check and create default user
        user = db.query(models.User).filter_by(username="integrationuser").first()
        if not user:
            print("Seeding default user 'integrationuser'...")
            hashed_pwd = auth.get_password_hash("password123")
            default_user = models.User(
                username="integrationuser",
                email="integration@example.com",
                hashed_password=hashed_pwd
            )
            db.add(default_user)
            db.commit()
            print("Default user seeded successfully!")

        # Check and seed sample assets
        asset_count = db.query(models.Asset).count()
        if asset_count == 0:
            print("Seeding database with sample assets...")
            import json
            sample_path = "sample_assets.json"
            if os.path.exists(sample_path):
                with open(sample_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                assets_in = [schemas.AssetCreate(**a) for a in data["assets"]]
                crud.bulk_import_assets(db, assets_in)
                print("Sample assets seeded successfully!")
    except Exception as e:
        print(f"Warning: Failed to seed database on startup: {e}")
    finally:
        db.close()

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ----------------- CUSTOM RATE LIMITER -----------------
RATE_LIMIT_WINDOW = 60  # seconds
RATE_LIMIT_MAX_REQUESTS = 100
request_history = defaultdict(list)

def check_rate_limit(request: Request):
    """
    Lightweight client IP-based rate limiter dependency.
    Allows up to 100 requests per 60 seconds per IP address.
    """
    client_ip = request.client.host if request.client else "unknown"
    now = time.time()
    
    # Filter out timestamps older than the window
    request_history[client_ip] = [t for t in request_history[client_ip] if now - t < RATE_LIMIT_WINDOW]
    
    if len(request_history[client_ip]) >= RATE_LIMIT_MAX_REQUESTS:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests. Please try again later."
        )
    
    request_history[client_ip].append(now)

# Apply rate limiter globally
app.router.dependencies.append(Depends(check_rate_limit))

# ----------------- CUSTOM ERROR HANDLERS -----------------

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handle Pydantic validation errors and return structured JSON."""
    details = []
    for err in exc.errors():
        details.append({
            "loc": err.get("loc"),
            "msg": err.get("msg"),
            "type": err.get("type")
        })
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error": "Validation Error",
            "detail": details
        }
    )

@app.exception_handler(IntegrityError)
async def integrity_exception_handler(request: Request, exc: IntegrityError):
    """Handle database constraints (e.g. unique keys) and return structured JSON."""
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={
            "error": "Database Conflict",
            "detail": "A database constraint was violated. This resource may already exist."
        }
    )

# ----------------- USER AUTHENTICATION ENDPOINTS -----------------

@app.post("/api/v1/auth/register", response_model=schemas.UserOut, status_code=status.HTTP_201_CREATED, tags=["Authentication"])
def register(user_in: schemas.UserCreate, db: Session = Depends(database.get_db)):
    """Register a new user account."""
    db_user_username = crud.get_user_by_username(db, user_in.username)
    if db_user_username:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already registered"
        )
    
    db_user_email = crud.get_user_by_email(db, user_in.email)
    if db_user_email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )

    # Hash the password and save
    hashed_password = auth.get_password_hash(user_in.password)
    user_data = {
        "username": user_in.username,
        "email": user_in.email,
        "hashed_password": hashed_password
    }
    return crud.create_user(db, user_data)

@app.post("/api/v1/auth/login", response_model=schemas.Token, tags=["Authentication"])
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(database.get_db)):
    """Log in to retrieve a JWT token. Compatible with Swagger Authorize button."""
    user = crud.get_user_by_username(db, form_data.username)
    if not user or not auth.verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    access_token = auth.create_access_token(data={"sub": user.username})
    return {"access_token": access_token, "token_type": "bearer"}

# ----------------- ASSET MANAGEMENT ENDPOINTS -----------------

@app.post("/api/v1/assets", response_model=schemas.AssetOut, status_code=status.HTTP_201_CREATED, tags=["Assets"])
def create_new_asset(
    asset_in: schemas.AssetCreate,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    """Create a single asset. Requires authentication."""
    existing = crud.get_asset_by_type_value(db, asset_in.type, asset_in.value)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Asset of type '{asset_in.type}' with value '{asset_in.value}' already exists."
        )
    return crud.create_asset(db, asset_in)

@app.get("/api/v1/assets", response_model=List[schemas.AssetOut], tags=["Assets"])
def list_assets(
    skip: int = 0,
    limit: int = 100,
    search: Optional[str] = None,
    type: Optional[str] = None,
    status: Optional[str] = None,
    source: Optional[str] = None,
    tag: Optional[str] = None,
    sort_by: str = "first_seen",
    sort_order: str = "asc",
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    """List assets with filtering, searching, sorting, and pagination. Requires authentication."""
    return crud.get_assets(
        db, skip=skip, limit=limit, search=search, asset_type=type,
        status=status, source=source, tag=tag, sort_by=sort_by, sort_order=sort_order
    )

@app.get("/api/v1/assets/graph", tags=["Visualization"])
def get_graph_data(
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    """
    Retrieves all nodes and edges formatted for Vis.js visualization.
    Requires authentication.
    """
    assets = db.query(models.Asset).all()
    relationships = db.query(models.AssetRelationship).all()

    # Define color scheme for types
    colors = {
        "domain": "#4F46E5",       # Indigo
        "subdomain": "#06B6D4",    # Cyan
        "ip_address": "#F59E0B",   # Amber
        "service": "#10B981",      # Emerald
        "certificate": "#EC4899",  # Pink
        "technology": "#8B5CF6"    # Purple
    }

    nodes = []
    for a in assets:
        nodes.append({
            "id": str(a.id),
            "label": f"{a.value}\n({a.type})",
            "title": f"Type: {a.type}<br>Status: {a.status}<br>Source: {a.source}",
            "color": colors.get(a.type, "#9CA3AF"),
            "font": {"color": "#ffffff"}
        })

    edges = []
    for r in relationships:
        edges.append({
            "id": str(r.id),
            "from": str(r.source_id),
            "to": str(r.target_id),
            "label": r.type,
            "arrows": "to",
            "color": {"color": "#9CA3AF", "highlight": "#4F46E5"}
        })

    return {"nodes": nodes, "edges": edges}

@app.get("/api/v1/assets/{asset_id}", response_model=schemas.AssetOut, tags=["Assets"])
def read_asset(
    asset_id: UUID,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    """Retrieve details of a specific asset. Requires authentication."""
    asset = crud.get_asset(db, asset_id)
    if not asset:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found")
    return asset

@app.put("/api/v1/assets/{asset_id}", response_model=schemas.AssetOut, tags=["Assets"])
def update_existing_asset(
    asset_id: UUID,
    asset_in: schemas.AssetUpdate,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    """Update asset fields. Requires authentication."""
    asset = crud.update_asset(db, asset_id, asset_in)
    if not asset:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found")
    return asset

@app.delete("/api/v1/assets/{asset_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["Assets"])
def delete_existing_asset(
    asset_id: UUID,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    """Delete an asset. Requires authentication."""
    success = crud.delete_asset(db, asset_id)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found")
    return None

# ----------------- TAG MANAGEMENT ENDPOINTS -----------------

@app.post("/api/v1/assets/{asset_id}/tags", response_model=schemas.AssetOut, tags=["Tags"])
def add_tag(
    asset_id: UUID,
    tag: str,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    """Add a tag to an asset. Requires authentication."""
    asset = crud.add_tag_to_asset(db, asset_id, tag.strip())
    if not asset:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found")
    return asset

@app.delete("/api/v1/assets/{asset_id}/tags/{tag}", response_model=schemas.AssetOut, tags=["Tags"])
def remove_tag(
    asset_id: UUID,
    tag: str,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    """Remove a tag from an asset. Requires authentication."""
    asset = crud.remove_tag_from_asset(db, asset_id, tag)
    if not asset:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found")
    return asset

@app.get("/api/v1/tags", response_model=List[str], tags=["Tags"])
def list_unique_tags(
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    """Get all unique tags across all assets. Requires authentication."""
    return crud.get_all_tags(db)

# ----------------- BULK IMPORT & LIFECYCLE -----------------

@app.post("/api/v1/assets/import", response_model=List[schemas.AssetOut], tags=["Assets"])
def bulk_import(
    request: schemas.BulkImportRequest,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    """Bulk import assets from a JSON payload. Handles deduplication & relationship auto-inference. Requires authentication."""
    return crud.bulk_import_assets(db, request.assets)

@app.post("/api/v1/assets/cleanup-stale", tags=["Lifecycle"])
def cleanup_stale(
    days: int = 30,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    """Mark assets that have not been seen in the specified number of days as stale. Requires authentication."""
    count = crud.mark_stale_assets(db, days)
    return {"message": f"Successfully marked {count} assets as stale."}

# ----------------- RELATIONSHIPS ENDPOINTS -----------------

@app.post("/api/v1/relationships", response_model=schemas.RelationshipOut, status_code=status.HTTP_201_CREATED, tags=["Relationships"])
def add_explicit_relationship(
    rel_in: schemas.RelationshipCreate,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    """Manually define a connection between two assets. Requires authentication."""
    source_asset = crud.get_asset(db, rel_in.source_id)
    target_asset = crud.get_asset(db, rel_in.target_id)
    
    if not source_asset or not target_asset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Source or Target asset not found."
        )
    return crud.create_relationship(db, rel_in)

@app.get("/api/v1/assets/{asset_id}/relationships", response_model=List[schemas.RelationshipOut], tags=["Relationships"])
def get_asset_relationships(
    asset_id: UUID,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    """Get all connections involving a specific asset. Requires authentication."""
    asset = crud.get_asset(db, asset_id)
    if not asset:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found")
    return crud.get_relationships_for_asset(db, asset_id)

@app.delete("/api/v1/relationships/{rel_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["Relationships"])
def delete_asset_relationship(
    rel_id: UUID,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    """Delete a relationship between assets. Requires authentication."""
    success = crud.delete_relationship(db, rel_id)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Relationship not found")
    return None

# ----------------- GRAPH VISUALIZATION ENDPOINTS (BONUS FEATURE) -----------------

@app.get("/graph", response_class=HTMLResponse, tags=["Visualization"])
def render_graph_page():
    """
    Serves a beautiful, interactive, single-page UI visualizing the asset network.
    Uses Vis.js served from CDN.
    """
    # Read the template from templates/graph.html
    template_path = os.path.join(os.path.dirname(__file__), "templates", "graph.html")
    try:
        with open(template_path, "r", encoding="utf-8") as f:
            html_content = f.read()
        return HTMLResponse(content=html_content)
    except FileNotFoundError:
        return HTMLResponse(
            content="<h1>Graph Template Not Found</h1><p>Ensure app/templates/graph.html exists.</p>",
            status_code=status.HTTP_404_NOT_FOUND
        )
