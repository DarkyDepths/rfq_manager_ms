"""Shared pytest fixtures for rfq_manager_ms tests.

This file provides a minimal, real shared foundation without introducing a large
fixture framework:
- ``db_engine`` / ``db_session``: isolated in-memory SQLite DB per test
- ``app`` / ``client``: FastAPI app and TestClient wired to the shared test DB
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.app import create_app
from src.app_context import get_db
from src.config.settings import settings
from src.database import Base

# Ensure all model metadata is registered for Base.metadata.create_all().
import src.models.workflow  # noqa: F401
import src.models.rfq  # noqa: F401
import src.models.rfq_stage  # noqa: F401
import src.models.subtask  # noqa: F401
import src.models.rfq_note  # noqa: F401
import src.models.rfq_file  # noqa: F401
import src.models.rfq_stage_field_value  # noqa: F401
import src.models.rfq_history  # noqa: F401
import src.models.reminder  # noqa: F401
import src.models.rfq_code_counter  # noqa: F401


@pytest.fixture
def db_engine():
	engine = create_engine("sqlite:///:memory:")
	Base.metadata.create_all(bind=engine)
	try:
		yield engine
	finally:
		engine.dispose()


@pytest.fixture
def db_session(db_engine):
	TestingSessionLocal = sessionmaker(bind=db_engine, autocommit=False, autoflush=False)
	session = TestingSessionLocal()
	try:
		yield session
	finally:
		session.close()


@pytest.fixture
def app(db_session):
	original_auth_bypass = settings.AUTH_BYPASS_ENABLED
	settings.AUTH_BYPASS_ENABLED = True
	application = create_app()

	def _override_get_db():
		yield db_session

	application.dependency_overrides[get_db] = _override_get_db
	try:
		yield application
	finally:
		application.dependency_overrides.clear()
		settings.AUTH_BYPASS_ENABLED = original_auth_bypass


@pytest.fixture
def client(app):
	with TestClient(app) as test_client:
		yield test_client
