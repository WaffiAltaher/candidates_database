import pytest

from candidates.database import Database


@pytest.fixture
def db(tmp_path):
    database = Database(db_path=str(tmp_path / "test.db"))
    database.initialize()
    yield database
    database.close()


def cv(**overrides):
    data = {
        "name": "Jane Doe",
        "university": "TU Delft",
        "job_title": "Developer",
        "technologies": ["Python", "SQL"],
        "experiences": [{"company": "Acme", "role": "Dev"}],
    }
    data.update(overrides)
    return data


def test_reupload_keeps_manual_data(db):
    cid, replaced = db.store_candidate(cv())
    assert not replaced
    db.add_interview(cid, 1, "Bob", "Good")
    db.add_proposed_customer(cid, "Initech")
    db.update_final_verdict(cid, "hire")

    new_id, replaced = db.store_candidate(
        cv(name="jane doe", job_title="Lead", technologies=["Go"],
           experiences=[{"company": "Globex", "role": "Lead"}])
    )

    assert replaced
    assert new_id == cid
    c = db.get_candidate(cid)
    assert c["final_verdict"] == "hire"
    assert len(c["interviews"]) == 1
    assert [x["customer_name"] for x in c["proposed_customers"]] == ["Initech"]
    assert c["job_title"] == "Lead"
    assert c["technologies"] == ["Go"]
    assert [e["company"] for e in c["experiences"]] == ["Globex"]


def test_failed_store_leaves_previous_data(db):
    cid, _ = db.store_candidate(cv())

    with pytest.raises(Exception):
        # experiences as a list of strings, as the LLM sometimes returns
        db.store_candidate(cv(job_title="Lead", technologies=["Go"], experiences=["Acme"]))

    c = db.get_candidate(cid)
    assert c["job_title"] == "Developer"
    assert sorted(c["technologies"]) == ["Python", "SQL"]
    assert [e["company"] for e in c["experiences"]] == ["Acme"]


def test_failed_first_store_creates_nothing(db):
    with pytest.raises(Exception):
        db.store_candidate(cv(experiences=["Acme"]))
    assert db.get_all_candidates() == []
