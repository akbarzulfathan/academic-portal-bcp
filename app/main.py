import os
import time
import uuid
import random
from datetime import datetime, timezone
from fastapi import FastAPI, Header, HTTPException, Response, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import Optional

app = FastAPI(title="Portal Layanan Akademik Terpadu - Multi-Region BCP")

REGION_NAME = os.getenv("REGION_NAME", "local-dev-region")
USE_MOCK = os.getenv("USE_MOCK", "true").lower() == "true"

CHAOS_STATE = {
    "db_healthy": True,
    "redis_healthy": True,
    "kv_healthy": True,
    "latency_ms": 0,
    "error_rate": 0.0
}

# --- DATA DUMMY MAHASISWA KONSORSIUM (UNIMAL) ---
STUDENTS_DB = {
    "230170200": {"nim": "230170200", "nama": "Zulfathan Akbar", "email": "zulfathan.230170200@mhs.unimal.ac.id", "ukt": 5500000},
    "240170017": {"nim": "240170017", "nama": "Sucia Nurmadani", "email": "sucia.240170017@mhs.unimal.ac.id", "ukt": 5000000},
    "240170078": {"nim": "240170078", "nama": "Safarul Akbar", "email": "safarul.240170078@mhs.unimal.ac.id", "ukt": 5000000},
    "240170134": {"nim": "240170134", "nama": "Salma Rasika Naisyla", "email": "salma.240170134@mhs.unimal.ac.id", "ukt": 5500000},
    "240170152": {"nim": "240170152", "nama": "Reifan Aldi Putra Faisa", "email": "reifan.240170152@mhs.unimal.ac.id", "ukt": 5000000},
    "240170210": {"nim": "240170210", "nama": "Rifqa Ramadhani", "email": "rifqa.240170210@mhs.unimal.ac.id", "ukt": 5500000},
}

# --- DATA BACA-INTENSIF: PENGUMUMAN & KATALOG MATA KULIAH (COSMOS DB PATTERN) ---
MOCK_ANNOUNCEMENTS = [
    {"id": "ANN-01", "title": "Batas Akhir Pembayaran UKT Semester Ganjil (Periode Kritis)", "owner": "Keuangan", "region_origin": REGION_NAME},
    {"id": "ANN-02", "title": "Jadwal Pengisian KRS Serentak Mahasiswa", "owner": "BAAK", "region_origin": REGION_NAME},
    {"id": "ANN-03", "title": "Pemeliharaan SSO Microsoft Entra ID Terpadu", "owner": "TI", "region_origin": REGION_NAME},
]

MOCK_CATALOG = [
    {"kode": "TIF401", "mk": "Komputasi Awan & Keberlangsungan Bisnis", "sks": 3, "kuota": 45, "owner": "BAAK"},
    {"kode": "TIF402", "mk": "Arsitektur Sistem Terdistribusi", "sks": 3, "kuota": 40, "owner": "BAAK"},
    {"kode": "TIF403", "mk": "Keamanan Jaringan & Kepatuhan Data", "sks": 3, "kuota": 40, "owner": "BAAK"},
    {"kode": "TIF404", "mk": "Rekayasa Keandalan Situs (SRE)", "sks": 3, "kuota": 35, "owner": "BAAK"},
]

MOCK_KRS_DB = []
MOCK_PAYMENTS_DB = {}
MOCK_NOTIFICATIONS_LOG = []

@app.middleware("http")
async def region_and_chaos_middleware(request: Request, call_next):
    if not request.url.path.startswith("/chaos"):
        if CHAOS_STATE["latency_ms"] > 0:
            time.sleep(CHAOS_STATE["latency_ms"] / 1000.0)
        if CHAOS_STATE["error_rate"] > 0 and random.random() < CHAOS_STATE["error_rate"]:
            return Response(content='{"detail": "Simulated Gray Failure Error"}', status_code=500, media_type="application/json")

    response = await call_next(request)
    response.headers["X-Served-By-Region"] = REGION_NAME
    return response

class LoginRequest(BaseModel):
    nim: str

class KRSRequest(BaseModel):
    nim: str
    kode_mk: list[str]

class PaymentRequest(BaseModel):
    nim: str
    nominal: int

class ChaosConfig(BaseModel):
    db_healthy: Optional[bool] = None
    redis_healthy: Optional[bool] = None
    kv_healthy: Optional[bool] = None
    latency_ms: Optional[int] = None
    error_rate: Optional[float] = None

def resolve_student(nim: str) -> dict:
    return STUDENTS_DB.get(nim, {
        "nim": nim,
        "nama": "Mahasiswa Konsorsium",
        "email": f"mhs.{nim}@mhs.unimal.ac.id",
        "ukt": 5000000
    })

# --- 1. DEEP HEALTH MODEL ---
@app.get("/health/live")
def liveness_probe():
    return {"status": "ALIVE", "owner": "TI", "region": REGION_NAME}

@app.get("/health/ready")
def readiness_probe(response: Response):
    checks = {
        "database_local": CHAOS_STATE["db_healthy"],
        "redis_cache_local": CHAOS_STATE["redis_healthy"],
        "keyvault_local": CHAOS_STATE["kv_healthy"],
        "entra_id_sso_sandbox": True,
        "payment_gateway_sandbox": True,
        "email_notification_service": True
    }
    all_critical_healthy = checks["database_local"] and checks["keyvault_local"]
    health_status = "GREEN" if all(checks.values()) else ("YELLOW" if all_critical_healthy else "RED")

    if not all_critical_healthy:
        response.status_code = 503

    return {
        "status": health_status,
        "service_owner": "TI",
        "region": REGION_NAME,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "dependencies": checks
    }

# --- 2. FUNGSI BISNIS LENGKAP BESERTA PEMILIKNYA (TI, BAAK, KEUANGAN) ---
@app.get("/", response_class=HTMLResponse)
def serve_ui():
    with open(os.path.join(os.path.dirname(__file__), "index.html"), "r", encoding="utf-8") as f:
        return f.read()

@app.get("/api/students")
def list_students():
    return {"service_owner": "BAAK", "region": REGION_NAME, "students": list(STUDENTS_DB.values())}

@app.post("/api/login")
def mock_login(payload: Optional[LoginRequest] = None, nim: str = "230170200"):
    target_nim = payload.nim if payload else nim
    mhs = resolve_student(target_nim)
    return {
        "service": "Autentikasi SSO (Microsoft Entra ID Sandbox)",
        "service_owner": "TI",
        "status": "AUTHENTICATED",
        "student": mhs,
        "entra_token": f"eyJ0eXAiOiJKV1QiLCJyZWciOiJ{REGION_NAME[:5]}-{uuid.uuid4().hex[:6]}",
        "region": REGION_NAME
    }

@app.get("/api/announcements")
def get_announcements():
    if not CHAOS_STATE["db_healthy"]:
        raise HTTPException(status_code=503, detail="Cosmos DB pengumuman tidak dapat diakses")
    return {"service": "Pengumuman Kampus", "service_owner": "BAAK & Keuangan", "region": REGION_NAME, "data": MOCK_ANNOUNCEMENTS}

@app.get("/api/catalog")
def get_catalog():
    if not CHAOS_STATE["db_healthy"]:
        raise HTTPException(status_code=503, detail="Cosmos DB katalog mata kuliah tidak dapat diakses")
    return {"service": "Katalog Mata Kuliah (Read-Intensive)", "service_owner": "BAAK", "region": REGION_NAME, "courses": MOCK_CATALOG}

@app.post("/api/krs")
def submit_krs(payload: KRSRequest):
    if not CHAOS_STATE["db_healthy"]:
        raise HTTPException(status_code=503, detail="SQL Database KRS sedang failover / tidak tersedia")

    mhs = resolve_student(payload.nim)
    notif = f"Email konfirmasi KRS dikirim ke {mhs['email']}"
    record = {
        "krs_id": f"KRS-{uuid.uuid4().hex[:6].upper()}",
        "service_owner": "BAAK",
        "nim": mhs["nim"],
        "nama": mhs["nama"],
        "email": mhs["email"],
        "kode_mk": payload.kode_mk,
        "notification": notif,
        "processed_by_region": REGION_NAME,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    MOCK_KRS_DB.append(record)
    return {"status": "SUCCESS", "service_owner": "BAAK", "data": record}

@app.post("/api/payments/ukt")
def pay_ukt(
    payload: PaymentRequest,
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key")
):
    if not idempotency_key:
        raise HTTPException(status_code=400, detail="Header 'Idempotency-Key' wajib disertakan!")

    if not CHAOS_STATE["db_healthy"]:
        raise HTTPException(status_code=503, detail="SQL Database Transaksi UKT tidak tersedia")

    mhs = resolve_student(payload.nim)

    if idempotency_key in MOCK_PAYMENTS_DB:
        existing_tx = MOCK_PAYMENTS_DB[idempotency_key]
        return {
            "status": "IDEMPOTENT_REPLAY",
            "service_owner": "Keuangan",
            "message": "Transaksi sudah pernah dicatat. Mencegah pendebetan ganda!",
            "current_region": REGION_NAME,
            "transaction": existing_tx
        }

    gateway_ref = f"SBX-GW-{uuid.uuid4().hex[:8].upper()}"
    email_receipt = {
        "to": mhs["email"],
        "subject": f"Bukti Lunas UKT - {mhs['nama']} ({mhs['nim']})",
        "status": "SENT_VIA_SMTP_SANDBOX"
    }
    MOCK_NOTIFICATIONS_LOG.append(email_receipt)

    new_tx = {
        "tx_id": f"PAY-{uuid.uuid4().hex[:8].upper()}",
        "idempotency_key": idempotency_key,
        "service_owner": "Keuangan",
        "nim": mhs["nim"],
        "nama": mhs["nama"],
        "email": mhs["email"],
        "nominal": payload.nominal,
        "payment_gateway_sandbox_ref": gateway_ref,
        "email_notification": email_receipt,
        "status": "PAID",
        "origin_region": REGION_NAME,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    MOCK_PAYMENTS_DB[idempotency_key] = new_tx
    return {"status": "CREATED", "service_owner": "Keuangan", "current_region": REGION_NAME, "transaction": new_tx}

@app.get("/api/documents/{doc_type}")
def download_document(doc_type: str, nim: str = "230170200"):
    mhs = resolve_student(nim)
    return {
        "service": " Penyimpanan Dokumen Akademik (Azure Blob Storage)",
        "service_owner": "BAAK",
        "doc_type": doc_type.upper(),
        "nim": mhs["nim"],
        "nama": mhs["nama"],
        "served_from_region": REGION_NAME,
        "blob_file": f"{doc_type.lower()}_{mhs['nim']}_{REGION_NAME}.pdf"
    }

@app.post("/chaos/inject")
def inject_chaos(config: ChaosConfig):
    for key, value in config.model_dump(exclude_none=True).items():
        CHAOS_STATE[key] = value
    return {"message": f"Konfigurasi Chaos di {REGION_NAME} diperbarui", "current_chaos_state": CHAOS_STATE}
