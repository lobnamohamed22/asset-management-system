import pytest
from fastapi import status

def test_register_user_success(client):
    response = client.post(
        "/api/v1/auth/register",
        json={"username": "testuser", "email": "test@example.com", "password": "password123"}
    )
    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()
    assert data["username"] == "testuser"
    assert data["email"] == "test@example.com"
    assert "id" in data

def test_register_user_duplicate_username(client):
    # Register first user
    client.post(
        "/api/v1/auth/register",
        json={"username": "testuser", "email": "test@example.com", "password": "password123"}
    )
    # Register second user with same username
    response = client.post(
        "/api/v1/auth/register",
        json={"username": "testuser", "email": "other@example.com", "password": "password123"}
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.json()["detail"] == "Username already registered"

def test_register_user_validation_error(client):
    # Short password
    response = client.post(
        "/api/v1/auth/register",
        json={"username": "usr", "email": "invalid-email", "password": "123"}
    )
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert response.json()["error"] == "Validation Error"

def test_login_success(client):
    # Register user
    client.post(
        "/api/v1/auth/register",
        json={"username": "loginuser", "email": "login@example.com", "password": "password123"}
    )
    # Login
    response = client.post(
        "/api/v1/auth/login",
        data={"username": "loginuser", "password": "password123"}
    )
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"

def test_login_invalid_credentials(client):
    # Register user
    client.post(
        "/api/v1/auth/register",
        json={"username": "loginuser", "email": "login@example.com", "password": "password123"}
    )
    # Try invalid password
    response = client.post(
        "/api/v1/auth/login",
        data={"username": "loginuser", "password": "wrongpassword"}
    )
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert response.json()["detail"] == "Incorrect username or password"

def test_protected_routes(client):
    # Try listing assets without token
    response = client.get("/api/v1/assets")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
