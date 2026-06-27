import pytest
from datetime import datetime, timezone, timedelta
from fastapi import status
from app.models import Asset

@pytest.fixture
def auth_headers(client):
    """Fixture to return auth headers for a registered test user."""
    client.post(
        "/api/v1/auth/register",
        json={"username": "assetuser", "email": "asset@example.com", "password": "password123"}
    )
    login_res = client.post(
        "/api/v1/auth/login",
        data={"username": "assetuser", "password": "password123"}
    )
    token = login_res.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}

def test_create_asset_success(client, auth_headers):
    payload = {
        "type": "domain",
        "value": "example.com",
        "source": "manual",
        "tags": ["testing"],
        "metadata": {"registrar": "Namecheap"}
    }
    response = client.post("/api/v1/assets", json=payload, headers=auth_headers)
    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()
    assert data["value"] == "example.com"
    assert data["type"] == "domain"
    assert data["tags"] == ["testing"]
    assert data["metadata"] == {"registrar": "Namecheap"}
    assert "id" in data

def test_create_asset_invalid_ip(client, auth_headers):
    payload = {
        "type": "ip_address",
        "value": "999.999.999.999", # Invalid IP address
        "source": "manual"
    }
    response = client.post("/api/v1/assets", json=payload, headers=auth_headers)
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert response.json()["error"] == "Validation Error"

def test_create_asset_invalid_domain(client, auth_headers):
    payload = {
        "type": "domain",
        "value": "example space com", # Invalid domain format
        "source": "manual"
    }
    response = client.post("/api/v1/assets", json=payload, headers=auth_headers)
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

def test_get_asset_by_id(client, auth_headers):
    payload = {"type": "domain", "value": "example.com", "source": "manual"}
    create_res = client.post("/api/v1/assets", json=payload, headers=auth_headers)
    asset_id = create_res.json()["id"]

    response = client.get(f"/api/v1/assets/{asset_id}", headers=auth_headers)
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["value"] == "example.com"

def test_get_assets_filtering_and_sorting(client, auth_headers):
    # Create several assets
    client.post("/api/v1/assets", json={"type": "domain", "value": "a.com", "source": "src1", "tags": ["t1"]}, headers=auth_headers)
    client.post("/api/v1/assets", json={"type": "domain", "value": "b.com", "source": "src2", "tags": ["t2"]}, headers=auth_headers)
    client.post("/api/v1/assets", json={"type": "ip_address", "value": "1.1.1.1", "source": "src1", "tags": ["t1"]}, headers=auth_headers)

    # Filter by type
    res = client.get("/api/v1/assets?type=domain", headers=auth_headers)
    assert len(res.json()) == 2

    # Filter by source
    res = client.get("/api/v1/assets?source=src2", headers=auth_headers)
    assert len(res.json()) == 1
    assert res.json()[0]["value"] == "b.com"

    # Filter by tag
    res = client.get("/api/v1/assets?tag=t1", headers=auth_headers)
    assert len(res.json()) == 2

    # Search query
    res = client.get("/api/v1/assets?search=1.1", headers=auth_headers)
    assert len(res.json()) == 1
    assert res.json()[0]["value"] == "1.1.1.1"

    # Sorting
    res = client.get("/api/v1/assets?sort_by=value&sort_order=desc", headers=auth_headers)
    values = [a["value"] for a in res.json()]
    assert values == ["b.com", "a.com", "1.1.1.1"]  # sorted alphabetically descending

def test_update_asset(client, auth_headers):
    create_res = client.post("/api/v1/assets", json={"type": "domain", "value": "example.com", "source": "manual"}, headers=auth_headers)
    asset_id = create_res.json()["id"]

    response = client.put(
        f"/api/v1/assets/{asset_id}",
        json={"value": "newexample.com", "status": "stale", "metadata": {"test": "value"}},
        headers=auth_headers
    )
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["value"] == "newexample.com"
    assert data["status"] == "stale"
    assert data["metadata"] == {"test": "value"}

def test_delete_asset(client, auth_headers):
    create_res = client.post("/api/v1/assets", json={"type": "domain", "value": "example.com", "source": "manual"}, headers=auth_headers)
    asset_id = create_res.json()["id"]

    del_res = client.delete(f"/api/v1/assets/{asset_id}", headers=auth_headers)
    assert del_res.status_code == status.HTTP_204_NO_CONTENT

    # Check it is deleted
    get_res = client.get(f"/api/v1/assets/{asset_id}", headers=auth_headers)
    assert get_res.status_code == status.HTTP_404_NOT_FOUND

def test_tag_management(client, auth_headers):
    create_res = client.post("/api/v1/assets", json={"type": "domain", "value": "example.com", "source": "manual"}, headers=auth_headers)
    asset_id = create_res.json()["id"]

    # Add tag
    add_res = client.post(f"/api/v1/assets/{asset_id}/tags?tag=newtag", headers=auth_headers)
    assert add_res.status_code == status.HTTP_200_OK
    assert "newtag" in add_res.json()["tags"]

    # List unique tags
    tags_res = client.get("/api/v1/tags", headers=auth_headers)
    assert "newtag" in tags_res.json()

    # Remove tag
    rem_res = client.delete(f"/api/v1/assets/{asset_id}/tags/newtag", headers=auth_headers)
    assert rem_res.status_code == status.HTTP_200_OK
    assert "newtag" not in rem_res.json()["tags"]

def test_bulk_import_and_deduplication(client, auth_headers):
    # Import first time
    payload = {
        "assets": [
            {
                "type": "domain",
                "value": "target.com",
                "source": "recon",
                "tags": ["recon"],
                "metadata": {"owner": "internal"}
            }
        ]
    }
    import_res1 = client.post("/api/v1/assets/import", json=payload, headers=auth_headers)
    assert import_res1.status_code == status.HTTP_200_OK
    assert len(import_res1.json()) == 1
    assert import_res1.json()[0]["value"] == "target.com"
    first_seen = import_res1.json()[0]["first_seen"]

    # Import second time with modified tags, metadata and source (Deduplication)
    payload_dup = {
        "assets": [
            {
                "type": "domain",
                "value": "target.com",
                "source": "scanner",
                "tags": ["scan", "recon"],
                "metadata": {"owner": "internal", "version": 2}
            }
        ]
    }
    import_res2 = client.post("/api/v1/assets/import", json=payload_dup, headers=auth_headers)
    assert import_res2.status_code == status.HTTP_200_OK
    data = import_res2.json()[0]
    
    assert data["value"] == "target.com"
    # Metadata should be merged
    assert data["metadata"] == {"owner": "internal", "version": 2}
    # Tags should be merged (union)
    assert set(data["tags"]) == {"recon", "scan"}
    # first_seen should NOT change
    assert data["first_seen"] == first_seen

def test_lifecycle_cleanup_stale(client, auth_headers, db):
    # Create an asset manually
    asset = Asset(
        type="domain",
        value="old-asset.com",
        status="active",
        first_seen=datetime.now(timezone.utc) - timedelta(days=40),
        last_seen=datetime.now(timezone.utc) - timedelta(days=40),
        source="scanner",
        tags=[],
        metadata_={}
    )
    db.add(asset)
    db.commit()
    db.refresh(asset)

    # Call stale endpoint
    res = client.post("/api/v1/assets/cleanup-stale?days=30", headers=auth_headers)
    assert res.status_code == status.HTTP_200_OK
    assert "marked 1 assets as stale" in res.json()["message"]

    # Verify status in database
    db.refresh(asset)
    assert asset.status == "stale"

    # Re-import should restore it to active
    payload = {
        "assets": [
            {
                "type": "domain",
                "value": "old-asset.com",
                "source": "scanner"
            }
        ]
    }
    reimport_res = client.post("/api/v1/assets/import", json=payload, headers=auth_headers)
    assert reimport_res.json()[0]["status"] == "active"
