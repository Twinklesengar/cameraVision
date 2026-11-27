"""AnalysisScheduler: shared budget + bounded pool sanity checks."""

from app.services.analysis_scheduler import analysis_scheduler


def test_pool_runs_job():
    fut = analysis_scheduler.run(lambda: 42)
    assert fut.result(timeout=5) == 42


def test_token_bucket_drains():
    # Burning without a pause should empty the global budget and it must be
    # exhausted for a moment rather than never returning False.
    for _ in range(1000):
        analysis_scheduler.try_acquire()
    assert analysis_scheduler.try_acquire() is False


def test_available_is_bounded():
    cap = analysis_scheduler._capacity
    assert 0.0 <= analysis_scheduler.available() <= cap + 0.01