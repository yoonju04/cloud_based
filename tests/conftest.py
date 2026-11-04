import pytest

from fts.jobs.clock import FakeClock, SequenceIds
from fts.jobs.control import JobService
from fts.jobs.store import FileStore, MemoryStore


@pytest.fixture(params=["memory", "file"])
def store(request, tmp_path):
    if request.param == "memory":
        return MemoryStore()
    return FileStore(tmp_path / "control-plane.json")


@pytest.fixture
def clock():
    return FakeClock()


@pytest.fixture
def jobs(store, clock):
    return JobService(store, clock, SequenceIds(), lease_ttl_s=10.0)

