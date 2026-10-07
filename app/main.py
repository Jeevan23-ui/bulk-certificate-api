import io
import re
import zipfile
from pathlib import Path

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models  # noqa: F401  (import registers the tables)
from app import service
from app.database import Base, engine, get_db
from app.models import Certificate, Job
from app.schemas import CertificateOut, JobCreate, JobCreated, JobStatusOut

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Bulk Certificate Generator API")


@app.get("/health", tags=["System"])
def health() -> dict:
    return {"status": "ok"}

@app.get("/", include_in_schema=False)
def root() -> dict:
    return {"message": "Bulk Certificate Generator API", "docs": "/docs"}

@app.post("/jobs", response_model=JobCreated, status_code=202, tags=["Jobs"])
def create_job(
    payload: JobCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """Submit many recipients in ONE request. Generation runs in the background."""
    job, accepted, rejected = service.create_job(db, payload)
    if accepted > 0:
        background_tasks.add_task(service.process_job, job.id)
    return JobCreated(
        job_id=job.id,
        status=job.status,
        total=accepted + rejected,
        accepted=accepted,
        rejected=rejected,
    )


@app.get("/jobs/{job_id}", response_model=JobStatusOut, tags=["Jobs"])
def get_job(job_id: str, db: Session = Depends(get_db)):
    """Progress and per-recipient results (successes and failures)."""
    summary = service.get_job_summary(db, job_id)
    if summary is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return summary


@app.get("/jobs/{job_id}/certificates", response_model=list[CertificateOut], tags=["Certificates"])
def list_certificates(
    job_id: str,
    status: str | None = Query(None, description="generated | failed | invalid | pending"),
    db: Session = Depends(get_db),
):
    if db.get(Job, job_id) is None:
        raise HTTPException(status_code=404, detail="Job not found")
    query = select(Certificate).where(Certificate.job_id == job_id).order_by(Certificate.row_index)
    if status:
        query = query.where(Certificate.status == status)
    return list(db.scalars(query))


@app.get("/certificates/{certificate_id}/download", tags=["Certificates"])
def download_certificate(certificate_id: str, db: Session = Depends(get_db)):
    cert = db.get(Certificate, certificate_id)
    if cert is None:
        raise HTTPException(status_code=404, detail="Certificate not found")
    if cert.status != "generated" or not cert.file_path or not Path(cert.file_path).exists():
        raise HTTPException(status_code=409, detail=f"Certificate not available (status: {cert.status})")
    return FileResponse(cert.file_path, media_type="application/pdf", filename=f"certificate_{cert.id}.pdf")


@app.get("/jobs/{job_id}/download", tags=["Certificates"])
def download_job_zip(job_id: str, db: Session = Depends(get_db)):
    """All generated certificates of a job as one ZIP."""
    if db.get(Job, job_id) is None:
        raise HTTPException(status_code=404, detail="Job not found")
    certs = list(db.scalars(
        select(Certificate).where(Certificate.job_id == job_id, Certificate.status == "generated")
    ))
    if not certs:
        raise HTTPException(status_code=409, detail="No generated certificates yet")

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for cert in certs:
            safe_name = re.sub(r"[^A-Za-z0-9_-]+", "_", cert.recipient_name or "recipient")
            zf.write(cert.file_path, arcname=f"{safe_name}_{cert.id[:8]}.pdf")
    return Response(
        content=buffer.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="job_{job_id}.zip"'},
    )