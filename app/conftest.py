
import os

# Keep tests isolated from the real attendance database.
os.environ["MONGO_DB"] = "attendance_test_db"

import pytest
from fastapi.testclient import TestClient
from pymongo import MongoClient

from app.main import app


@pytest.fixture(scope="session")
def api_client():
    mongo_uri = os.getenv("MONGO_URI", "mongodb://localhost:27017")

    setup_client = MongoClient(
        mongo_uri,
        serverSelectionTimeoutMS=5000,
    )

    try:
        setup_client.drop_database("attendance_test_db")
    finally:
        setup_client.close()

    with TestClient(app) as test_client:
        yield test_client

    cleanup_client = MongoClient(
        mongo_uri,
        serverSelectionTimeoutMS=5000,
    )
    try:
        cleanup_client.drop_database("attendance_test_db")
    finally:
        cleanup_client.close()