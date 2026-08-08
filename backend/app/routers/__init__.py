# SoloPrac Backend Routers

from fastapi import APIRouter

from app.routers import (
    admin,
    agent,
    auth,
    backup,
    calendar,
    certificates,
    documents,
    dpdp,
    evaluation,
    health,
    images,
    invoices,
    jobs,
    patient_documents,
    patients,
    portal,
    prescriptions,
    risk_alerts,
    security,
    voice,
    weekly_report,
)

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(health.router, tags=["health"])
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(patients.router, prefix="/patients", tags=["patients"])
api_router.include_router(agent.router, tags=["agent"])
api_router.include_router(images.router, tags=["images"])
api_router.include_router(evaluation.router, tags=["evaluation"])
api_router.include_router(documents.router, tags=["documents"])
api_router.include_router(security.router, tags=["security"])
api_router.include_router(prescriptions.router, tags=["prescriptions"])
api_router.include_router(prescriptions.approve_router, tags=["prescriptions"])
api_router.include_router(certificates.router, tags=["certificates"])
api_router.include_router(certificates.verify_router, tags=["certificates-public"])
api_router.include_router(invoices.router, tags=["invoices"])
api_router.include_router(calendar.router, tags=["calendar"])
api_router.include_router(portal.router, tags=["portal"])
api_router.include_router(portal.public_router, tags=["portal-public"])
api_router.include_router(portal.patient_router, tags=["portal-patient"])
api_router.include_router(weekly_report.router, tags=["weekly_report"])
api_router.include_router(risk_alerts.router, tags=["risk-alerts"])
api_router.include_router(admin.router, tags=["admin"])
api_router.include_router(dpdp.router, tags=["dpdp-consent"])
api_router.include_router(backup.router, tags=["admin-backup"])
api_router.include_router(voice.router, tags=["voice"])
api_router.include_router(patient_documents.router, tags=["patient-documents"])
api_router.include_router(jobs.router, tags=["jobs"])
