from datetime import datetime, timezone

from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import Certificate, Job
from app.pdf import generate_certificate_pdf
from app.schemas import JobCreate, RecipientIn


def create_job(db: Session, payload: JobCreate) -> tuple[Job, int, int]:
    """Validate each recipient individually and save everything in one transaction."""
    job = Job(event_name=payload.event_name, issued_by=payload.issued_by)
    db.add(job)
    db.flush()  # assigns job.id without committing

    accepted = rejected = 0
    for index, raw in enumerate(payload.recipients):
        try:
            recipient = RecipientIn.model_validate(raw)
            db.add(Certificate(
                job_id=job.id,
                row_index=index,
                recipient_name=recipient.name,
                recipient_email=recipient.email,
                achievement=recipient.achievement,
                status="pending",
            ))
            accepted += 1
        except ValidationError as exc:
            reasons = "; ".join(
                f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors()
            )
            db.add(Certificate(
                job_id=job.id,
                row_index=index,
                recipient_name=str(raw.get("name"))[:200] if raw.get("name") else None,
                recipient_email=str(raw.get("email"))[:320] if raw.get("email") else None,
                status="invalid",
                error=reasons,
            ))
            rejected += 1

    if accepted == 0:
        job.status = "completed_with_errors"  # nothing to process

    db.commit()
    db.refresh(job)
    return job, accepted, rejected


def process_job(job_id: str) -> None:
    """Runs in the background. Generates a PDF for every pending certificate."""
    db = SessionLocal()  # own session: the request's session is closed by now
    try:
        job = db.get(Job, job_id)
        if job is None:
            return
        job.status = "processing"
        db.commit()

        pending_ids = list(db.scalars(
            select(Certificate.id)
            .where(Certificate.job_id == job_id, Certificate.status == "pending")
            .order_by(Certificate.row_index)
        ))
        issued_on = datetime.now(timezone.utc).strftime("%d %B %Y")

        for cert_id in pending_ids:
            cert = db.get(Certificate, cert_id)
            try:
                cert.file_path = generate_certificate_pdf(
                    certificate_id=cert.id,
                    job_id=job_id,
                    recipient_name=cert.recipient_name,
                    achievement=cert.achievement,
                    event_name=job.event_name,
                    issued_by=job.issued_by,
                    issued_on=issued_on,
                )
                cert.status = "generated"
                db.commit()
            except Exception as exc:  # one failure must not stop the others
                db.rollback()
                cert = db.get(Certificate, cert_id)
                cert.status = "failed"
                cert.error = f"{type(exc).__name__}: {exc}"[:500]
                db.commit()

        job = db.get(Job, job_id)
        any_bad = db.scalar(
            select(func.count()).select_from(Certificate)
            .where(Certificate.job_id == job_id, Certificate.status.in_(["failed", "invalid"]))
        )
        job.status = "completed_with_errors" if any_bad else "completed"
        db.commit()
    except Exception:
        db.rollback()
        job = db.get(Job, job_id)
        if job:
            job.status = "failed"
            db.commit()
    finally:
        db.close()


def get_job_summary(db: Session, job_id: str) -> dict | None:
    job = db.get(Job, job_id)
    if job is None:
        return None

    rows = db.execute(
        select(Certificate.status, func.count())
        .where(Certificate.job_id == job_id)
        .group_by(Certificate.status)
    ).all()
    counts = {status: n for status, n in rows}

    certificates = list(db.scalars(
        select(Certificate).where(Certificate.job_id == job_id).order_by(Certificate.row_index)
    ))
    return {
        "job_id": job.id,
        "event_name": job.event_name,
        "status": job.status,
        "created_at": job.created_at,
        "total": sum(counts.values()),
        "generated": counts.get("generated", 0),
        "failed": counts.get("failed", 0),
        "invalid": counts.get("invalid", 0),
        "pending": counts.get("pending", 0),
        "certificates": certificates,
    }