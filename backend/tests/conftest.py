import os
import uuid

import pytest
from app.db import Base, get_db, make_engine
from app.main import app
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker
from sqlalchemy.schema import CreateSchema, DropSchema


@pytest.fixture
def system(tmp_path, monkeypatch):
    from app import ingestion, worker

    database_url = os.environ.get("TEST_DATABASE_URL", f"sqlite:///{tmp_path / 'test.db'}")
    engine = make_engine(database_url)
    schema = None
    if database_url.startswith("postgresql"):
        schema = "test_" + uuid.uuid4().hex
        with engine.begin() as connection:
            connection.execute(CreateSchema(schema))
        engine = engine.execution_options(schema_translate_map={None: schema})
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)

    def dependency():
        with factory() as db:
            try:
                yield db
                db.commit()
            except Exception:
                db.rollback()
                raise

    app.dependency_overrides[get_db] = dependency
    monkeypatch.setattr(worker, "SessionLocal", factory)
    monkeypatch.setattr(ingestion, "STAGING", tmp_path / "staging")
    with TestClient(app) as client:
        response = client.post(
            "/api/auth/setup",
            json={
                "email": "admin@example.com",
                "password": "Admin-Test-Password!",
                "name": "Test Admin",
                "workspace": "Test workspace",
            },
        )
        assert response.status_code == 201, response.text
        client.headers["x-csrf-token"] = client.cookies["ls_csrf"]
        yield client, factory, worker
    app.dependency_overrides.clear()
    if schema:
        with engine.begin() as connection:
            connection.execute(DropSchema(schema, cascade=True))
    engine.dispose()


@pytest.fixture
def client(system):
    return system[0]


@pytest.fixture
def source(client):
    response = client.post(
        "/api/sources", json={"name": "Test auth", "parser": "json", "type": "linux_auth"}
    )
    assert response.status_code == 201
    return response.json()
