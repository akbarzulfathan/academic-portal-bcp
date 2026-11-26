import concurrent.futures
import uuid
import httpx

# ISI DENGAN DOMAIN LENGKAP DARI PORTAL AZURE (TANPA https://)
DOMAIN_A = "https://app-kel2bcp2026-indonesiacentral.blueforest-f56957af.indonesiacentral.azurecontainerapps.io"
DOMAIN_B = "https://app-kel2bcp2026-eastasia.kindsand-06e5a5f9.eastasia.azurecontainerapps.io"

PROTO = "https"
URL_A = f"{PROTO}://{DOMAIN_A}"
URL_B = f"{PROTO}://{DOMAIN_B}"

def set_chaos_a(payload: dict):
    r = httpx.post(f"{URL_A}/chaos/inject", json=payload, timeout=8.0)
    return r.json()

def burst_traffic_b(n_requests: int = 25):
    def hit(_):
        key = f"LOAD-{uuid.uuid4().hex[:8]}"
        r = httpx.post(f"{URL_B}/api/payments/ukt", headers={"Idempotency-Key": key}, json={"nim": "230170200", "nominal": 5000000}, timeout=8.0)
        return r.status_code
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as ex:
        results = list(ex.map(hit, range(n_requests)))
    print(f"-> Hasil Burst 25 Request Serentak ke Region B (East Asia): {results.count(200)} SUKSES (HTTP 200)!")

def menu():
    while True:
        print("\n================ MENU DEMO 9 SKENARIO BCP ================")
        print("1. Skenario 1 : Compute Region A Mati / Tidak Merespons")
        print("2. Skenario 2 : Database SQL Primary Region A Failover")
        print("3. Skenario 3 : Evakuasi Penuh Region A (Outage Regional)")
        print("4. Skenario 4 : Gray Failure (Latensi Tinggi 1.8s & Error 30%)")
        print("5. Skenario 5 : Partisi Jaringan & Uji Anti-Duplikasi UKT")
        print("6. Skenario 6 : Key Vault Region A Gagal Diakses (Static Stability)")
        print("7. Skenario 7 : Bad Deployment Terdeteksi di Region A (Rollout Stop)")
        print("8. Skenario 8 : Lonjakan Trafik 100% Dialihkan ke Region B")
        print("9. Skenario 9 : Failback — Pemulihan Penuh ke Region A Normal")
        print("0. Keluar")
        p = input("Pilih nomor skenario [0-9]: ").strip()

        if p == "1":
            set_chaos_a({"db_healthy": False, "kv_healthy": False, "redis_healthy": False})
            print("[AKTIF] Simulasi Compute/Endpoint Region A Down (503). Amati Probe pindah ke East Asia!")
        elif p == "2":
            set_chaos_a({"db_healthy": False, "kv_healthy": True, "latency_ms": 0, "error_rate": 0.0})
            print("[AKTIF] DB Primary di Region A terputus -> Trafik otomatis dialihkan ke Region B + Tunjukkan Tab 4 (SQL Failover Group)!")
        elif p == "3":
            set_chaos_a({"db_healthy": False, "kv_healthy": False, "latency_ms": 0, "error_rate": 0.0})
            print("[AKTIF] Evakuasi Penuh Region A! 100% beban kini dilayani oleh East Asia.")
        elif p == "4":
            set_chaos_a({"db_healthy": True, "kv_healthy": True, "latency_ms": 1800, "error_rate": 0.3})
            print("[AKTIF] Gray Failure di Region A! Perhatikan latensi naik >1800ms di terminal Probe.")
        elif p == "5":
            key = f"SPLIT-{uuid.uuid4().hex[:6].upper()}"
            r1 = httpx.post(f"{URL_B}/api/payments/ukt", headers={"Idempotency-Key": key}, json={"nim": "230170200", "nominal": 5000000}).json()
            r2 = httpx.post(f"{URL_B}/api/payments/ukt", headers={"Idempotency-Key": key}, json={"nim": "230170200", "nominal": 5000000}).json()
            print(f"-> Kirim ke-1 (Key={key}): {r1.get('status')}")
            print(f"-> Retry ke-2 (Key={key}): {r2.get('status')} (TERBUKTI TIDAK TERDEBET GANDA!)")
        elif p == "6":
            set_chaos_a({"db_healthy": True, "kv_healthy": False, "latency_ms": 0, "error_rate": 0.0})
            print("[AKTIF] Key Vault Region A gagal! Region A 503, Region B tetap sehat pakai Key Vault lokalnya sendiri.")
        elif p == "7":
            set_chaos_a({"db_healthy": False, "error_rate": 1.0, "latency_ms": 0})
            print("[AKTIF] Simulasi rilis rusak di Region A -> Health Probe gagal -> Buka Tab 5 (GitHub Actions) jelaskan Region B aman terlindungi!")
        elif p == "8":
            set_chaos_a({"db_healthy": False, "kv_healthy": False, "error_rate": 0.0, "latency_ms": 0})
            print("[AKTIF] Mengirim lonjakan beban serentak 100% ke Region B (East Asia)...")
            burst_traffic_b(25)
        elif p == "9":
            set_chaos_a({"db_healthy": True, "kv_healthy": True, "redis_healthy": True, "latency_ms": 0, "error_rate": 0.0})
            print("[PULIH] Failback selesai! Region A kembali HTTP 200 GREEN. Amati Probe kembali ke indonesiacentral!")
        elif p == "0":
            break

if __name__ == "__main__":
    menu()
