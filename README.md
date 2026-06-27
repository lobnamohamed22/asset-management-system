# Asset Management System – Backend Technical Assessment

Backend Technical Assessment built with FastAPI, PostgreSQL, SQLAlchemy, Alembic, Docker and JWT Authentication. 

This system acts as an inventory for asset mapping (domains, subdomains, IP addresses, services, certificates, and technologies), automatically inferring relationships between them, handling deduplication upon bulk import, updating asset lifecycles, and displaying them on an interactive relationship graph.

---

## 🛠️ Technology Stack
- **Python 3.14**
- **FastAPI** (CRUD API & HTML Views)
- **PostgreSQL** (Database)
- **SQLAlchemy** (ORM)
- **Alembic** (Database Migrations)
- **Pydantic v2** (Data Validation & Schemas)
- **JWT Authentication** (Access protection)
- **Docker & Docker Compose** (Containerization)
- **Pytest** (Automated testing)
- **Vis.js** (Bonus Feature: Asset relationship graph visualization)
- **Git** (Version control)

---

## 📁 Project Structure
The project uses a flat, beginner-friendly structure without unnecessary abstractions, making it simple to navigate and explain in interviews:

```
asset-management-system/
├── app/
│   ├── database.py       # SQLAlchemy connection setup & session generator (get_db)
│   ├── models.py         # SQLAlchemy DB models (User, Asset, AssetRelationship)
│   ├── schemas.py        # Pydantic validation schemas (Auth, Asset, Relationships)
│   ├── auth.py           # Password hashing & JWT helpers (OAuth2 protection)
│   ├── crud.py           # Core business logic (CRUD, deduplication, relationship inference)
│   ├── main.py           # FastAPI routes, exception handlers & rate limiting
│   └── templates/
│       └── graph.html    # Interactive Vis.js relationship visualizer frontend
├── alembic/              # Alembic database migrations
├── alembic.ini           # Alembic settings
├── tests/                # Pytest testing suite
│   ├── conftest.py       # Pytest setup and transactional DB overrides
│   ├── test_auth.py      # Registration & login tests
│   ├── test_assets.py    # Asset CRUD, deduplication, & stale cleanup tests
│   └── test_relations.py # Explicit & inferred relationship tests
├── Dockerfile            # Container build instructions
├── docker-compose.yml    # App + PostgreSQL container configs
├── requirements.txt      # Dependency list
├── run.sh                # Container startup script (waits for DB, migrates, starts app)
├── sample_assets.json    # Example JSON payload for bulk import
└── README.md             # This guide
```

---

## 🚀 Quick Start (Running with Docker)

### 1. Prerequisites
Make sure you have [Docker](https://docs.docker.com/get-docker/) and [Docker Compose](https://docs.docker.com/compose/install/) installed.

### 2. Run the System
Simply run the following command in the project root:
```bash
docker-compose up --build
```
This command will:
1. Spin up the **PostgreSQL** database.
2. Build the **FastAPI** web application.
3. Wait for PostgreSQL to start up.
4. Run all **Alembic** database migrations automatically.
5. Start the web server on `http://localhost:8000`.

### 3. Verify
- **Interactive API Docs (Swagger):** `http://localhost:8000/docs`
- **Asset Relationship Graph Visualizer:** `http://localhost:8000/graph`

---

## 💡 Out-of-the-Box Usability (Self-Healing & Local Scripts)
- **Automatic Database Seeding:** On startup, if the application detects that the database is empty (for example, after running tests or initializing on a fresh PostgreSQL instance), it will automatically register the default user account (`integrationuser` with password `password123`) and pre-populate the database with all 9 assets from `sample_assets.json`. This enables immediate graph visualization without any manual configuration!
- **Local Script Serving (Offline Capable):** The network visualizer serves `vis-network.min.js` locally from the backend static folder. This prevents modern browser privacy settings (such as Edge/Brave Tracking Prevention or Chrome Incognito) from blocking the script as a third-party tracker, providing a robust, standalone, offline-capable interface.

---

## 🧪 Running Automated Tests

Tests use a dedicated transactional rollback pattern. Every test runs inside a database transaction that is rolled back at the end of the test, ensuring tests are fast and isolated.

To execute tests within the running Docker setup, execute:
```bash
docker-compose run web pytest -v
```

---

## ⚙️ Core Feature Implementation

### 1. JWT Authentication
- Registration: `POST /api/v1/auth/register` (creates user, hashes password using `bcrypt`).
- Login: `POST /api/v1/auth/login` (verifies password and issues JWT token).
- Swagger Authorize integration is wired up via the `OAuth2PasswordBearer` scheme.

### 2. Bulk Import & Deduplication Logic (`POST /api/v1/assets/import`)
When bulk-importing a list of assets, the system checks if an asset with the same `type` and `value` already exists:
- **Deduplication:** Merges metadata (new keys added, existing keys updated) and performs a union on tags (no duplicates).
- **Lifecycle:** Updates `last_seen` to the current time. If the asset status was "stale", it is restored to "active".

### 3. Automated Relationship Inference
During asset import/creation, connections are automatically inferred:
1. **subdomain → domain:** If subdomain `api.google.com` is imported and `google.com` exists, a `subdomain_of` relationship is created.
2. **service → ip_address:** If service `80/tcp` contains `ip_address` in its metadata, a `runs_on` relationship is established to that IP asset.
3. **ip_address ↔ subdomain:** If subdomain `api.google.com` lists `8.8.8.8` in its metadata, a `resolves_to` relationship is created.
4. **certificate → domain/subdomain:** If a cert metadata secures `google.com`, a `secures` relationship is established.
5. **technology → service/subdomain:** If technology `nginx` lists service `80/tcp` in its metadata, a `used_by` relationship is established.

### 4. Lifecycle Stale Marking (`POST /api/v1/assets/cleanup-stale`)
Marks active assets as "stale" if they have not been seen (i.e. `last_seen`) in a configured number of days (default: 30 days).

---

## 🛡️ API Endpoints Summary

### Authentication
- `POST /api/v1/auth/register` - Create a user account
- `POST /api/v1/auth/login` - Obtain JWT access token

### Assets (Protected)
- `POST /api/v1/assets` - Create an asset
- `GET /api/v1/assets` - Search, filter, page, and sort assets
- `GET /api/v1/assets/{id}` - View specific asset
- `PUT /api/v1/assets/{id}` - Update asset fields
- `DELETE /api/v1/assets/{id}` - Delete asset
- `POST /api/v1/assets/import` - Bulk import assets with auto-deduplication & relationship mapping

### Tags (Protected)
- `POST /api/v1/assets/{id}/tags?tag=name` - Add tag
- `DELETE /api/v1/assets/{id}/tags/{tag}` - Remove tag
- `GET /api/v1/tags` - List all unique tags

### Relationships (Protected)
- `POST /api/v1/relationships` - Create custom connections
- `GET /api/v1/assets/{id}/relationships` - View connections for a specific asset
- `DELETE /api/v1/relationships/{id}` - Remove a connection

### Visualization & Bonus Features
- `GET /graph` - Visual network webpage (requires logging in using API credentials)
- `GET /api/v1/assets/graph` (Protected) - Fetches nodes and links data for Vis.js

---

## 💡 Example: Import the Sample Dataset
You can import the preconfigured dataset (`sample_assets.json`) using Swagger or `curl`:

1. Register and Log In to obtain your `<JWT_TOKEN>` token.
2. Run the bulk import:
```bash
curl -X 'POST' \
  'http://localhost:8000/api/v1/assets/import' \
  -H 'accept: application/json' \
  -H 'Authorization: Bearer <JWT_TOKEN>' \
  -H 'Content-Type: application/json' \
  -d @sample_assets.json
```
3. Open `http://localhost:8000/graph` to view the inferred relationships!
