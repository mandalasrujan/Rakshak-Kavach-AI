"""Script to verify both medication history fixes on the live running Docker stack."""

import time
import httpx
import pymupdf

BASE_URL = "http://127.0.0.1:8080"
CSRF_HEADERS = {"X-CSRF-Protection": "1", "Origin": BASE_URL}


def create_prescription_pdf(prescription_date: str, lines: list[str]) -> bytes:
    doc = pymupdf.open()
    page = doc.new_page()
    text = f"Prescription Date: {prescription_date}\n\nPrescribed Medications:\n"
    for line in lines:
        text += f"- {line}\n"
    page.insert_text((50, 72), text, fontsize=11)
    data = doc.tobytes()
    doc.close()
    return data


def main() -> None:
    client = httpx.Client(base_url=BASE_URL, headers=CSRF_HEADERS, timeout=30.0)

    # 1. Register and login test patient
    test_email = f"patient.live.{int(time.time())}@example.com"
    password = "TestPassword123!"

    reg = client.post("/api/v1/auth/register", json={"email": test_email, "password": password})
    assert reg.status_code == 201, reg.text
    login = client.post("/api/v1/auth/login", json={"email": test_email, "password": password})
    assert login.status_code == 200, login.text
    print(f"Logged in as {test_email}")

    # 2. Grant consent
    notice = client.get("/api/v1/patient/consent").json()
    consent = client.post(
        "/api/v1/patient/consent", json={"notice_version": notice["notice_version"]}
    )
    assert consent.status_code == 200, consent.text
    print("Consent granted.")

    # 3. Create and upload Visit 1:
    # Metformin 500 mg, Atorvastatin 10 mg, Vitamin D3 1000 IU + duplicate Metformin
    v1_pdf = create_prescription_pdf(
        "10/01/2026",
        [
            "Metformin 500 mg — twice daily with meals.",
            "Atorvastatin 10 mg — nightly.",
            "Vitamin D3 1000 IU — daily.",
            "Metformin 500 mg — twice daily with meals.",  # Duplicate row
        ],
    )
    u1 = client.post(
        "/api/v1/patient/documents",
        files={"file": ("visit1_prescription.pdf", v1_pdf, "application/pdf")},
    ).json()
    d1_id = u1["id"]
    print(f"Uploaded Visit 1 document: {d1_id}")

    # 4. Create and upload Visit 2:
    # Metformin 500 mg, Atorvastatin 20 mg (dosage change), Vitamin D3 2000 IU (dosage change)
    v2_pdf = create_prescription_pdf(
        "15/04/2026",
        [
            "Metformin 500 mg — twice daily with meals.",
            "Atorvastatin 20 mg — nightly.",
            "Vitamin D3 2000 IU — daily.",
        ],
    )
    u2 = client.post(
        "/api/v1/patient/documents",
        files={"file": ("visit2_prescription.pdf", v2_pdf, "application/pdf")},
    ).json()
    d2_id = u2["id"]
    print(f"Uploaded Visit 2 document: {d2_id}")

    # 5. Wait for worker to finish processing
    print("Waiting for background worker to process documents...")
    for _ in range(30):
        time.sleep(1)
        docs = client.get("/api/v1/patient/documents").json()["items"]
        statuses = {d["id"]: d["status"] for d in docs}
        if statuses.get(d1_id) == "ready" and statuses.get(d2_id) == "ready":
            print("Both documents processed and marked ready!")
            break
    else:
        raise RuntimeError(f"Timeout waiting for documents to process: {statuses}")

    # 6. Verify medications endpoint
    meds_res = client.get("/api/v1/patient/medications")
    assert meds_res.status_code == 200, meds_res.text
    data = meds_res.json()

    visits = data.get("visits", [])
    print(f"\n--- API Response Verification ---")
    print(f"Total visits found: {len(visits)}")
    assert len(visits) == 2, f"Expected 2 visits, got {len(visits)}"

    # Sort visits by date descending
    visit2 = next(v for v in visits if v["document_id"] == d2_id)
    visit1 = next(v for v in visits if v["document_id"] == d1_id)

    print(f"\nVisit 1 (Prescription Date: {visit1['date']}):")
    for m in visit1["medications"]:
        print(f"  • {m['name']} | Dose: {m['dose']} | Frequency: {m['frequency']}")
    assert len(visit1["medications"]) == 3, f"Expected 3 medications in Visit 1, got {len(visit1['medications'])}"
    assert visit1["date"] == "2026-01-10"

    print(f"\nVisit 2 (Prescription Date: {visit2['date']}):")
    for m in visit2["medications"]:
        print(f"  • {m['name']} | Dose: {m['dose']} | Frequency: {m['frequency']}")
    assert len(visit2["medications"]) == 3, f"Expected 3 medications in Visit 2, got {len(visit2['medications'])}"
    assert visit2["date"] == "2026-04-15"

    # Verify dosage changes
    v1_map = {m["name"]: m for m in visit1["medications"]}
    v2_map = {m["name"]: m for m in visit2["medications"]}

    assert v1_map["Atorvastatin"]["dose"] == "10 mg"
    assert v2_map["Atorvastatin"]["dose"] == "20 mg"
    print("\n[VERIFIED] Atorvastatin dosage change preserved: 10 mg (Visit 1) -> 20 mg (Visit 2)")

    assert v1_map["Vitamin D3"]["dose"] == "1000 IU"
    assert v2_map["Vitamin D3"]["dose"] == "2000 IU"
    print("[VERIFIED] Vitamin D3 dosage change preserved: 1000 IU (Visit 1) -> 2000 IU (Visit 2)")

    assert v1_map["Metformin"]["dose"] == "500 mg"
    assert v2_map["Metformin"]["dose"] == "500 mg"
    print("[VERIFIED] Metformin preserved across both visits: 500 mg")

    assert len(data["items"]) == 6
    print(f"[VERIFIED] Total deduplicated items count: 6 (intra-visit duplicate was eliminated)")

    # 7. Cross-patient isolation check
    other_email = f"other.live.{int(time.time())}@example.com"
    client2 = httpx.Client(base_url=BASE_URL, headers=CSRF_HEADERS, timeout=30.0)
    client2.post("/api/v1/auth/register", json={"email": other_email, "password": password})
    client2.post("/api/v1/auth/login", json={"email": other_email, "password": password})
    other_meds = client2.get("/api/v1/patient/medications").json()
    assert other_meds["items"] == []
    assert other_meds["visits"] == []
    print("[VERIFIED] Cross-patient isolation: another patient cannot see these medications.")

    print("\nALL LIVE VERIFICATIONS PASSED SUCCESSFULLY!")


if __name__ == "__main__":
    main()
