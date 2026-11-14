"""Script to verify both medication history fixes on the live running Docker stack."""

import os
import secrets
import time

import httpx
import pymupdf

BASE_URL = os.environ.get("VERIFY_BASE_URL", "http://127.0.0.1:8080")
CSRF_HEADERS = {"X-CSRF-Protection": "1"}


def _check(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def _get_test_auth_credentials() -> str:
    env_secret = os.environ.get("TEST_VERIFY_PASSWORD")
    if env_secret:
        return env_secret
    return f"T!{secrets.token_urlsafe(16)}9x"


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
    test_auth_secret = _get_test_auth_credentials()

    reg = client.post(
        "/api/v1/auth/register",
        json={"email": test_email, "password": test_auth_secret},
    )
    _check(reg.status_code == 201, reg.text)
    login = client.post(
        "/api/v1/auth/login",
        json={"email": test_email, "password": test_auth_secret},
    )
    _check(login.status_code == 200, login.text)
    print(f"Logged in as {test_email}")

    # 2. Grant consent
    notice = client.get("/api/v1/patient/consent").json()
    consent = client.post(
        "/api/v1/patient/consent", json={"notice_version": notice["notice_version"]}
    )
    _check(consent.status_code == 200, consent.text)
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
    statuses: dict[str, str] = {}
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
    _check(meds_res.status_code == 200, meds_res.text)
    data = meds_res.json()

    visits = data.get("visits", [])
    print("\n--- API Response Verification ---")
    print(f"Total visits found: {len(visits)}")
    _check(len(visits) == 2, f"Expected 2 visits, got {len(visits)}")

    # Sort visits by date descending
    visit2 = next(v for v in visits if v["document_id"] == d2_id)
    visit1 = next(v for v in visits if v["document_id"] == d1_id)

    print(f"\nVisit 1 (Prescription Date: {visit1['date']}):")
    for m in visit1["medications"]:
        print(f"  • {m['name']} | Dose: {m['dose']} | Frequency: {m['frequency']}")
    _check(
        len(visit1["medications"]) == 3,
        f"Expected 3 medications in Visit 1, got {len(visit1['medications'])}",
    )
    _check(visit1["date"] == "2026-01-10", f"Unexpected Visit 1 date: {visit1['date']}")

    print(f"\nVisit 2 (Prescription Date: {visit2['date']}):")
    for m in visit2["medications"]:
        print(f"  • {m['name']} | Dose: {m['dose']} | Frequency: {m['frequency']}")
    _check(
        len(visit2["medications"]) == 3,
        f"Expected 3 medications in Visit 2, got {len(visit2['medications'])}",
    )
    _check(visit2["date"] == "2026-04-15", f"Unexpected Visit 2 date: {visit2['date']}")

    # Verify dosage changes
    v1_map = {m["name"]: m for m in visit1["medications"]}
    v2_map = {m["name"]: m for m in visit2["medications"]}

    _check(
        v1_map["Atorvastatin"]["dose"] == "10 mg",
        f"Expected Atorvastatin 10 mg in Visit 1, got {v1_map.get('Atorvastatin', {}).get('dose')}",
    )
    _check(
        v2_map["Atorvastatin"]["dose"] == "20 mg",
        f"Expected Atorvastatin 20 mg in Visit 2, got {v2_map.get('Atorvastatin', {}).get('dose')}",
    )
    print("\n[VERIFIED] Atorvastatin dosage change preserved: 10 mg (Visit 1) -> 20 mg (Visit 2)")

    _check(
        v1_map["Vitamin D3"]["dose"] == "1000 IU",
        f"Expected Vitamin D3 1000 IU in Visit 1, got {v1_map.get('Vitamin D3', {}).get('dose')}",
    )
    _check(
        v2_map["Vitamin D3"]["dose"] == "2000 IU",
        f"Expected Vitamin D3 2000 IU in Visit 2, got {v2_map.get('Vitamin D3', {}).get('dose')}",
    )
    print("[VERIFIED] Vitamin D3 dosage change preserved: 1000 IU (Visit 1) -> 2000 IU (Visit 2)")

    _check(
        v1_map["Metformin"]["dose"] == "500 mg",
        f"Expected Metformin 500 mg in Visit 1, got {v1_map.get('Metformin', {}).get('dose')}",
    )
    _check(
        v2_map["Metformin"]["dose"] == "500 mg",
        f"Expected Metformin 500 mg in Visit 2, got {v2_map.get('Metformin', {}).get('dose')}",
    )
    print("[VERIFIED] Metformin preserved across both visits: 500 mg")

    _check(
        len(data["items"]) == 6,
        f"Expected 6 total items, got {len(data['items'])}",
    )
    print("[VERIFIED] Total deduplicated items count: 6 (intra-visit duplicate was eliminated)")

    # 7. Cross-patient isolation check
    other_email = f"other.live.{int(time.time())}@example.com"
    client2 = httpx.Client(base_url=BASE_URL, headers=CSRF_HEADERS, timeout=30.0)
    reg2 = client2.post(
        "/api/v1/auth/register",
        json={"email": other_email, "password": test_auth_secret},
    )
    _check(reg2.status_code == 201, reg2.text)
    login2 = client2.post(
        "/api/v1/auth/login",
        json={"email": other_email, "password": test_auth_secret},
    )
    _check(login2.status_code == 200, login2.text)
    other_meds = client2.get("/api/v1/patient/medications").json()
    _check(other_meds["items"] == [], f"Expected empty items, got {other_meds['items']}")
    _check(other_meds["visits"] == [], f"Expected empty visits, got {other_meds['visits']}")
    print("[VERIFIED] Cross-patient isolation: another patient cannot see these medications.")

    print("\nALL LIVE VERIFICATIONS PASSED SUCCESSFULLY!")


if __name__ == "__main__":
    main()
