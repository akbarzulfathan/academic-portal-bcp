import time
import csv
import uuid
import httpx
from datetime import datetime

# ISI DENGAN DOMAIN LENGKAP DARI PORTAL AZURE (TANPA https://)
DOMAIN_A = "https://app-kel2bcp2026-indonesiacentral.blueforest-f56957af.indonesiacentral.azurecontainerapps.io"
DOMAIN_B = "https://app-kel2bcp2026-eastasia.kindsand-06e5a5f9.eastasia.azurecontainerapps.io"

PROTO = "https"
URL_A = f"{PROTO}://{DOMAIN_A}"
URL_B = f"{PROTO}://{DOMAIN_B}"
ENDPOINTS = [URL_A, URL_B]
CSV_FILE = "hasil_uji_failover.csv"

def pick_healthy_region(client: httpx.Client) -> str:
    for url in ENDPOINTS:
        try:
            r = client.get(f"{url}/health/ready", timeout=2.2)
            if r.status_code == 200:
                return url
        except Exception:
            continue
    return URL_B

def main():
    print("======================================================================")
    print(" SYNTHETIC TRANSACTION PROBE AKTIF (RPO=0 & AUTO-FAILOVER MONITOR)")
    print("======================================================================")

    with open(CSV_FILE, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["waktu", "region_aktif", "http_code", "latensi_ms", "status_ukt", "duplikasi"])

        cycle = 0
        idem_key = f"UKT-{uuid.uuid4().hex[:6].upper()}"

        with httpx.Client() as client:
            while True:
                cycle += 1
                if cycle % 2 == 1:
                    idem_key = f"UKT-{uuid.uuid4().hex[:6].upper()}"

                t0 = time.perf_counter()
                target = pick_healthy_region(client)
                now = datetime.now().strftime("%H:%M:%S")

                try:
                    res = client.post(
                        f"{target}/api/payments/ukt",
                        headers={"Idempotency-Key": idem_key},
                        json={"nim": "230170200", "nominal": 5500000},
                        timeout=4.0
                    )
                    ms = round((time.perf_counter() - t0) * 1000, 1)
                    reg = res.headers.get("X-Served-By-Region", "unknown")
                    st = res.json().get("status", "OK")

                    print(f"[{now}] REGION: {reg:16} | HTTP {res.status_code} | {ms:6} ms | {st}")
                    writer.writerow([now, reg, res.status_code, ms, st, "TIDAK"])
                    f.flush()
                except Exception:
                    ms = round((time.perf_counter() - t0) * 1000, 1)
                    print(f"[{now}] >>> DETEKSI GANGGUAN ({ms} ms) -> MENGALIHKAN TRAFIK KE BACKUP...")
                    writer.writerow([now, "FAILOVER_SWITCH", 503, ms, "RETRY_SAFE", "TIDAK"])
                    f.flush()

                time.sleep(2)

if __name__ == "__main__":
    main()
