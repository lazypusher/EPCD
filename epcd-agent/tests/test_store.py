import pytest

from epcd_agent.store import SessionStore


@pytest.fixture()
def store(tmp_path):
    return SessionStore(tmp_path / "store.sqlite3")


def test_session_roundtrip(store):
    store.create_session("s1", model_config={"model": "claude-x"})
    s = store.get_session("s1")
    assert s["session_id"] == "s1"
    assert s["model_config"] == {"model": "claude-x"}
    assert s["created_at"]
    assert store.get_session("missing") is None


def test_project_roundtrip(store):
    store.create_session("s1")
    assert store.get_project("s1") is None
    store.set_project("s1", "/abs/proj", lib_name="demo", technology_digest="sha256:t")
    p = store.get_project("s1")
    assert p == {"project_dir": "/abs/proj", "lib_name": "demo", "technology_digest": "sha256:t"}


def test_instance_and_active_selection(store):
    store.create_session("s1")
    store.set_project("s1", "/abs/proj")
    store.upsert_instance("s1", "m-1", template_id="system.inductor.simple_inductor",
                          name="simple_inductor1", project_dir="/abs/proj")
    store.upsert_instance("s1", "m-2", template_id="system.inductor.simple_inductor",
                          name="simple_inductor2", project_dir="/abs/proj")
    assert store.get_active_instance("s1") is None
    store.set_active_instance("s1", "m-2")
    inst = store.get_active_instance("s1")
    assert inst["instance_id"] == "m-2"
    assert inst["template_id"] == "system.inductor.simple_inductor"
    assert inst["config_digest"] is None
    # upsert keeps active pointer and updates fields in place
    store.upsert_instance("s1", "m-2", template_id="system.inductor.simple_inductor",
                          name="renamed", project_dir="/abs/proj")
    assert store.get_active_instance("s1")["name"] == "renamed"


def test_config_digest_roundtrip(store):
    store.create_session("s1")
    assert store.get_config_digest("s1") is None
    store.set_config_digest("s1", "sha256:d1")
    assert store.get_config_digest("s1") == "sha256:d1"
    store.set_config_digest("s1", "sha256:d2")
    assert store.get_config_digest("s1") == "sha256:d2"


def test_job_lifecycle(store):
    store.create_session("s1")
    store.add_job("s1", "j-1", request_id="iteration-1", task_type="simulation-evaluation",
                  status="queued", parameters={"width": 11})
    assert store.get_job("s1", "j-1")["status"] == "queued"
    store.update_job("s1", "j-1", status="succeeded", objective_cost=0.15,
                     started_at="t0", finished_at="t1")
    job = store.get_job("s1", "j-1")
    assert job["status"] == "succeeded"
    assert job["objective_cost"] == pytest.approx(0.15)
    assert job["parameters"] == {"width": 11}
    assert job["started_at"] == "t0" and job["finished_at"] == "t1"
    assert store.find_job_by_request("s1", "iteration-1")["job_id"] == "j-1"
    assert store.find_job_by_request("s1", "iteration-9") is None
    store.add_job("s1", "j-2", request_id="iteration-2", task_type="simulation-evaluation",
                  status="queued")
    assert [j["job_id"] for j in store.list_jobs("s1")] == ["j-1", "j-2"]


def test_optimization_task_roundtrip(store):
    store.create_session("s1")
    store.create_optimization("s1", "opt-1", budget={"max_rounds": 10})
    task = store.get_optimization("s1", "opt-1")
    assert task["status"] == "pending"
    assert task["budget"] == {"max_rounds": 10}
    store.update_optimization("s1", "opt-1", status="running", rounds=[{"round": 1}])
    store.update_optimization("s1", "opt-1", best_job_id="j-3", consumed={"rounds": 1})
    task = store.get_optimization("s1", "opt-1")
    assert task["status"] == "running"
    assert task["best_job_id"] == "j-3"
    assert task["rounds"] == [{"round": 1}]
    assert task["consumed"] == {"rounds": 1}
    assert store.get_optimization("s1", "missing") is None


def test_milestones_ordered(store):
    store.create_session("s1")
    store.record_milestone("s1", "M1", "approved", snapshot={"templateId": "t"})
    store.record_milestone("s1", "M2", "approved_with_changes")
    rows = store.list_milestones("s1")
    assert [r["name"] for r in rows] == ["M1", "M2"]
    assert rows[0]["choice"] == "approved"
    assert rows[0]["snapshot"] == {"templateId": "t"}
    assert rows[1]["snapshot"] is None
    assert rows[0]["recorded_at"]


def test_kv_state_roundtrip(store):
    store.create_session("s1")
    assert store.get_state("s1", "k") is None
    assert store.get_state("s1", "k", default=7) == 7
    store.set_state("s1", "k", {"nested": [1, 2]})
    assert store.get_state("s1", "k") == {"nested": [1, 2]}
    store.set_state("s1", "k", "replaced")
    assert store.get_state("s1", "k") == "replaced"


def test_sessions_isolated(store):
    store.create_session("s1")
    store.create_session("s2")
    store.set_project("s1", "/p1")
    store.set_project("s2", "/p2")
    assert store.get_project("s1")["project_dir"] == "/p1"
    assert store.get_project("s2")["project_dir"] == "/p2"


def test_store_persists_across_instances(tmp_path):
    db = tmp_path / "store.sqlite3"
    first = SessionStore(db)
    first.create_session("s1")
    first.set_project("s1", "/abs/proj")
    second = SessionStore(db)
    assert second.get_project("s1")["project_dir"] == "/abs/proj"
