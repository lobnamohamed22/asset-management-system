import os
os.environ["TESTING"] = "True"
import sys
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

# Add workspace directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import Base, get_db
from app.main import app

# Use the environment database URL (usually postgresql in Docker)
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://ams_user:ams_password@localhost:5432/asset_management")

# Create engine for test database
engine = create_engine(DATABASE_URL)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@pytest.fixture(scope="session", autouse=True)
def setup_database():
    """
    Ensure the database schema exists by creating all missing tables,
    and truncate tables to ensure a clean slate for the test session
    without dropping the tables.
    """
    Base.metadata.create_all(bind=engine)
    from sqlalchemy import text
    with engine.connect() as conn:
        conn.execute(text("TRUNCATE TABLE asset_relationships, assets, users CASCADE;"))
        conn.commit()
    yield

@pytest.fixture
def db():
    """
    Yields a database session nested inside a transaction.
    Rolls back after each test so the database remains clean.
    """
    connection = engine.connect()
    transaction = connection.begin()
    session = TestingSessionLocal(bind=connection)

    yield session

    session.close()
    transaction.rollback()
    connection.close()

@pytest.fixture
def client(db):
    """
    Yields a FastAPI TestClient with the database session overridden.
    """
    def override_get_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
