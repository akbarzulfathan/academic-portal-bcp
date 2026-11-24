import os
import time
import uuid
import random
from datetime import datetime, timezone
from fastapi import FastAPI, Header, HTTPException, Response, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import Optional

app = FastAPI(title="Portal Akademik Terpadu - Multi-Region Testbed")

# --- KONFIGURASI STATIC STABILITY (Murni membaca Environment Lokal Region) ---
REGION_NAME = os.getenv("REGION_NAME", "local-dev-region")
USE_MOCK = os.getenv("USE_MOCK", "true").lower() == "true"

# Variabel simulasi Chaos / Gangguan Lokal untuk Pengujian Tahap 8
CHAOS_STATE = {
    "db_healthy": True,
    "redis_healthy": True,
    "kv_healthy": True,
    "latency_ms": 0,      # Untuk simulasi Gray Failure (Skenario 4)
    "error_rate": 0.0     # 0.0 - 1.0 untuk simulasi error sebagian
}

# Penyimpanan In-Memory (Fallback/Mock saat dijalankan tanpa Azure DB aktif)
MOCK_ANNOUNCEMENTS = [
    {"id": "1", "title": "Batas Akhir Pembayaran UKT Semester Ganjil", "category": "Keuangan", "region_origin": REGION_NAME},
    {"id": "2", "title": "Jadwal Pengisian KRS Serentak Konsorsium", "category": "BAAK", "region_origin": REGION_NAME},
]
MOCK_KRS_DB = []
MOCK_PAYMENTS_DB = {}  # Menyimpan {idempotency_key: data_transaksi} -> Mencegah tagihan ganda!

# --- MIDDLEWARE: HEADER REGION & SIMULASI GRAY FAILURE ---
@app.middleware("http")
async def region_and_chaos_middleware(request: Request, call_next):
    # Simulasi latensi tinggi jika Chaos diaktifkan (kecuali endpoint kontrol chaos)
    if not request.url.path.startswith("/chaos"):
        if CHAOS_STATE["latency_ms"] > 0:
            time.sleep(CHAOS_STATE["latency_ms"] / 1000.0)
        if CHAOS_STATE["error_rate"] > 0 and random.random() < CHAOS_STATE["error_rate"]:
            return Response(content='{"detail": "Simulated Gray Failure Error"}', status_code=500, media_type="application/json")

    response = await call_next(request)
    # Header wajib agar Skrip Probe tahu Region mana yang membalas request
    response.headers["X-Served-By-Region"] = REGION_NAME
    return response

# --- MODEL DATA ---
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

# --- 1. DEEP HEALTH MODEL (Tahap 7) ---
@app.get("/health/live")
def liveness_probe():
    """Memastikan proses container hidup."""
    return {"status": "ALIVE", "region": REGION_NAME}

@app.get("/health/ready")
def readiness_probe(response: Response):
    """
    Diperiksa oleh Azure Front Door setiap beberapa detik.
    Memeriksa dependensi kritis regional (DB, Cache, Key Vault) agar tidak terjadi 'blind routing'.
    """
    checks = {
        "database_local": CHAOS_STATE["db_healthy"],
        "redis_cache_local": CHAOS_STATE["redis_healthy"],
        "keyvault_local": CHAOS_STATE["kv_healthy"]
    }
    
    # Di produksi Azure (USE_MOCK=false), tambahkan ping nyata ke SQL/Cosmos/KeyVault di sini
    all_critical_healthy = checks["database_local"] and checks["keyvault_local"]
    
    # Cache Redis mati tidak membuat region mati total (Static Stability: aplikasi jalan walau cache kosong)
    health_status = "GREEN" if all(checks.values()) else ("YELLOW" if all_critical_healthy else "RED")

    if not all_critical_healthy:
        response.status_code = 503  # Memberi sinyal ke Front Door untuk memindahkan trafik ke Region sebelah!

    return {
        "status": health_status,
        "region": REGION_NAME,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "dependencies": checks
    }

# --- 2. FUNGSI BISNIS (Tahap 1 & Tahap 3) ---

@app.get("/", response_class=HTMLResponse)
def serve_ui():
    with open(os.path.join(os.path.dirname(__file__), "index.html"), "r", encoding="utf-8") as f:
        return f.read()

@app.post("/api/login")
def mock_login(nim: str = "2026001"):
    """Simulasi token Entra ID / Managed Identity."""
    return {"message": "Login berhasil", "nim": nim, "token": f"ey-mock-{REGION_NAME}-{uuid.uuid4().hex[:6]}", "region": REGION_NAME}

@app.get("/api/announcements")
def get_announcements():
    """Pola: Active-Active Multi-Region Reads/Writes (Cosmos DB Eventual/Session)."""
    if not CHAOS_STATE["db_healthy"]:
        raise HTTPException(status_code=503, detail="Database pengumuman tidak dapat diakses")
    return {"region": REGION_NAME, "data": MOCK_ANNOUNCEMENTS}

@app.post("/api/krs")
def submit_krs(payload: KRSRequest):
    """Pola: Single-Writer dengan Auto-Failover (Mencegah bentrok pengisian KRS)."""
    if not CHAOS_STATE["db_healthy"]:
        raise HTTPException(status_code=503, detail="Database KRS sedang failover / tidak tersedia")
    
    record = {
        "krs_id": str(uuid.uuid4()),
        "nim": payload.nim,
        "kode_mk": payload.kode_mk,
        "processed_by_region": REGION_NAME,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    MOCK_KRS_DB.append(record)
    return {"status": "SUCCESS", "data": record}

@app.post("/api/payments/ukt")
def pay_ukt(
    payload: PaymentRequest,
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key")
):
    """
    Pola Kritis (RPO = 0): Single-Writer + Wajib Idempotency-Key.
    Jika klien melakukan retry saat terjadi failover dari Region A ke B, pembayaran TIDAK tercatat ganda.
    """
    if not idempotency_key:
        raise HTTPException(status_code=400, detail="Header 'Idempotency-Key' wajib disertakan untuk transaksi UKT!")
    
    if not CHAOS_STATE["db_healthy"]:
        raise HTTPException(status_code=503, detail="Database Transaksi tidak tersedia")

    # Cek apakah transaksi dengan kunci ini sudah pernah diproses sebelumnya
    if idempotency_key in MOCK_PAYMENTS_DB:
        existing_tx = MOCK_PAYMENTS_DB[idempotency_key]
        return {
            "status": "IDEMPOTENT_REPLAY",
            "message": "Transaksi sudah pernah dicatat. Mencegah pendebetan ganda!",
            "current_region": REGION_NAME,
            "transaction": existing_tx
        }

    # Simpan transaksi baru
    new_tx = {
        "tx_id": f"PAY-{uuid.uuid4().hex[:8].upper()}",
        "idempotency_key": idempotency_key,
        "nim": payload.nim,
        "nominal": payload.nominal,
        "status": "PAID",
        "origin_region": REGION_NAME,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    MOCK_PAYMENTS_DB[idempotency_key] = new_tx
    return {"status": "CREATED", "current_region": REGION_NAME, "transaction": new_tx}

@app.get("/api/documents/{doc_type}")
def download_document(doc_type: str, nim: str = "2026001"):
    """Pola: Active-Passive Read-Access Geo-Redundant Storage (Blob RA-GZRS)."""
    return {
        "doc_type": doc_type,
        "nim": nim,
        "storage_mode": "RA-GZRS",
        "served_from_region": REGION_NAME,
        "download_url": f"https://mockstorage.{REGION_NAME}.blob.core.windows.net/docs/{doc_type}-{nim}.pdf"
    }

# --- 3. ENDPOINT KONTROL CHAOS (Memudahkan Pengujian Mandiri Tahap 8) ---
@app.post("/chaos/inject")
def inject_chaos(config: ChaosConfig):
    """Endpoint khusus pengujian untuk menyuntikkan kegagalan DB, KeyVault, atau Gray Failure."""
    for key, value in config.model_dump(exclude_none=True).items():
        CHAOS_STATE[key] = value
    return {"message": f"Konfigurasi Chaos di {REGION_NAME} diperbarui", "current_chaos_state": CHAOS_STATE}
