from types import SimpleNamespace

from src.utils.rfq_lifecycle import calculate_rfq_lifecycle_progress


def test_calculate_rfq_lifecycle_progress_uses_completed_stage_ratio():
    stages = [
        SimpleNamespace(status="Completed", progress=100),
        SimpleNamespace(status="Completed", progress=100),
        SimpleNamespace(status="In Progress", progress=90),
        SimpleNamespace(status="Not Started", progress=0),
        SimpleNamespace(status="Not Started", progress=0),
    ]

    assert calculate_rfq_lifecycle_progress(stages, "In preparation") == 40


def test_calculate_rfq_lifecycle_progress_ignores_skipped_stages():
    stages = [
        SimpleNamespace(status="Completed", progress=100),
        SimpleNamespace(status="In Progress", progress=75),
        SimpleNamespace(status="Skipped", progress=0),
    ]

    assert calculate_rfq_lifecycle_progress(stages, "In preparation") == 50


def test_calculate_rfq_lifecycle_progress_terminal_status_forces_100():
    stages = [
        SimpleNamespace(status="Completed", progress=100),
        SimpleNamespace(status="Skipped", progress=0),
    ]

    assert calculate_rfq_lifecycle_progress(stages, "Cancelled") == 100
