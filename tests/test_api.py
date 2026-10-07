import io
import zipfile

from app import service

PAYLOAD = {
    "event_name": "Python Workshop 2026",
    "issued_by": "Reva University",
    "recipients": [
        {"name": "Asha Rao", "email": "asha@example.com"},
        {"name": "Ravi Kumar", "email": "ravi@example.com", "achievement": "First Place"},
    ],
}


def make_payload(*recipients):
    return {**PAYLOAD, "recipients": list(recipients) or PAYLOAD["recipients"]}


# 1. Creating a generation job
def test_create_job_returns_202_and_job_id(client):
    r = client.post("/jobs", json=PAYLOAD)
    assert r.status_code == 202
    body = r.json()
    assert body["job_id"]
    assert body["total"] == 2
    assert body["accepted"] == 2
    assert body["rejected"] == 0


# 2. Input validation
def test_empty_recipient_list_is_rejected(client):
    r = client.post("/jobs", json=make_payload() | {"recipients": []})
    assert r.status_code == 422


def test_missing_event_name_is_rejected(client):
    bad = {k: v for k, v in PAYLOAD.items() if k != "event_name"}
    assert client.post("/jobs", json=bad).status_code == 422


def test_invalid_recipient_is_recorded_without_blocking_valid_ones(client):
    payload = make_payload(
        {"name": "Asha Rao", "email": "asha@example.com"},
        {"name": "", "email": "not-an-email"},
    )
    r = client.post("/jobs", json=payload)
    assert r.status_code == 202
    assert r.json()["accepted"] == 1
    assert r.json()["rejected"] == 1

    job = client.get(f"/jobs/{r.json()['job_id']}").json()
    invalid = [c for c in job["certificates"] if c["status"] == "invalid"]
    assert len(invalid) == 1
    assert invalid[0]["row_index"] == 1
    assert "email" in invalid[0]["error"]


# 3. Certificate generation
def test_certificates_are_generated_as_pdfs(client):
    job_id = client.post("/jobs", json=PAYLOAD).json()["job_id"]
    certs = client.get(f"/jobs/{job_id}/certificates?status=generated").json()
    assert len(certs) == 2

    r = client.get(f"/certificates/{certs[0]['id']}/download")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert r.content.startswith(b"%PDF")


# 4. Job status / progress
def test_job_status_reports_progress_counts(client):
    job_id = client.post("/jobs", json=PAYLOAD).json()["job_id"]
    job = client.get(f"/jobs/{job_id}").json()
    assert job["status"] == "completed"
    assert job["total"] == 2
    assert job["generated"] == 2
    assert job["failed"] == 0
    assert job["pending"] == 0


def test_unknown_job_returns_404(client):
    assert client.get("/jobs/does-not-exist").status_code == 404


# 5. Handling an individual certificate failure
def test_one_failure_does_not_stop_the_other_certificates(client, monkeypatch):
    real_generate = service.generate_certificate_pdf

    def flaky(**kwargs):
        if kwargs["recipient_name"] == "Boom":
            raise RuntimeError("disk full")
        return real_generate(**kwargs)

    monkeypatch.setattr(service, "generate_certificate_pdf", flaky)

    payload = make_payload(
        {"name": "Asha Rao", "email": "asha@example.com"},
        {"name": "Boom", "email": "boom@example.com"},
        {"name": "Ravi Kumar", "email": "ravi@example.com"},
    )
    job_id = client.post("/jobs", json=payload).json()["job_id"]
    job = client.get(f"/jobs/{job_id}").json()

    assert job["status"] == "completed_with_errors"
    assert job["generated"] == 2
    assert job["failed"] == 1
    failed = [c for c in job["certificates"] if c["status"] == "failed"][0]
    assert failed["recipient_name"] == "Boom"
    assert "disk full" in failed["error"]


# 6. Retrieving generated certificates
def test_download_all_certificates_as_zip(client):
    job_id = client.post("/jobs", json=PAYLOAD).json()["job_id"]
    r = client.get(f"/jobs/{job_id}/download")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/zip"
    with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
        assert len(zf.namelist()) == 2


def test_failed_certificate_cannot_be_downloaded(client):
    payload = make_payload({"name": "", "email": "bad"})
    job_id = client.post("/jobs", json=payload).json()["job_id"]
    cert = client.get(f"/jobs/{job_id}").json()["certificates"][0]
    assert client.get(f"/certificates/{cert['id']}/download").status_code == 409