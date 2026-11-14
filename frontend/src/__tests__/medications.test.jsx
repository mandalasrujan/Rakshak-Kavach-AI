import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import Medications from "../pages/Medications.jsx";
import { stubApi } from "./helpers.js";

describe("Medications page", () => {
  it("renders empty state when patient has no medications", async () => {
    stubApi({
      "GET /patient/medications": [200, { items: [], visits: [] }],
    });
    render(<Medications />);
    expect(await screen.findByText("No medications were found in your uploaded prescriptions.")).toBeInTheDocument();
  });

  it("renders multiple visits separately, preserves dosage changes, and deduplicates within visits", async () => {
    const doc1 = "11111111-1111-1111-1111-111111111111";
    const doc2 = "22222222-2222-2222-2222-222222222222";

    const v1Meds = [
      {
        id: "m1",
        document_id: doc1,
        chunk_id: "c1",
        page: 1,
        name: "Metformin",
        dose: "500 mg",
        frequency: "twice daily with meals",
        duration: null,
        start_date: "2026-01-10",
      },
      {
        id: "m2",
        document_id: doc1,
        chunk_id: "c2",
        page: 1,
        name: "Atorvastatin",
        dose: "10 mg",
        frequency: "nightly",
        duration: null,
        start_date: "2026-01-10",
      },
      {
        id: "m3",
        document_id: doc1,
        chunk_id: "c3",
        page: 1,
        name: "Vitamin D3",
        dose: "1000 IU",
        frequency: "daily",
        duration: null,
        start_date: "2026-01-10",
      },
      // Duplicate Metformin extraction in Visit 1 to test deduplication
      {
        id: "m4_dup",
        document_id: doc1,
        chunk_id: "c4",
        page: 1,
        name: "Metformin",
        dose: "500 mg",
        frequency: "twice daily with meals",
        duration: null,
        start_date: "2026-01-10",
      },
    ];

    const v2Meds = [
      {
        id: "m5",
        document_id: doc2,
        chunk_id: "c5",
        page: 1,
        name: "Metformin",
        dose: "500 mg",
        frequency: "twice daily with meals",
        duration: null,
        start_date: "2026-04-15",
      },
      {
        id: "m6",
        document_id: doc2,
        chunk_id: "c6",
        page: 1,
        name: "Atorvastatin",
        dose: "20 mg",
        frequency: "nightly",
        duration: null,
        start_date: "2026-04-15",
      },
      {
        id: "m7",
        document_id: doc2,
        chunk_id: "c7",
        page: 1,
        name: "Vitamin D3",
        dose: "2000 IU",
        frequency: "daily",
        duration: null,
        start_date: "2026-04-15",
      },
    ];

    stubApi({
      "GET /patient/medications": [
        200,
        {
          items: [...v2Meds, ...v1Meds],
          visits: [
            {
              document_id: doc2,
              date: "2026-04-15",
              page: 1,
              medications: v2Meds,
            },
            {
              document_id: doc1,
              date: "2026-01-10",
              page: 1,
              medications: v1Meds,
            },
          ],
        },
      ],
    });

    render(<Medications />);

    // Both visit headers should be present
    expect(await screen.findByText(/Visit \/ Prescription — 10 Jan 2026/)).toBeInTheDocument();
    expect(await screen.findByText(/Visit \/ Prescription — 15 Apr 2026/)).toBeInTheDocument();

    // Verify sections
    const v1Section = screen.getByLabelText("Visit dated 2026-01-10");
    const v2Section = screen.getByLabelText("Visit dated 2026-04-15");

    // In Visit 1: Atorvastatin 10 mg, Vitamin D3 1000 IU
    expect(v1Section).toHaveTextContent("Atorvastatin");
    expect(v1Section).toHaveTextContent("10 mg");
    expect(v1Section).toHaveTextContent("Vitamin D3");
    expect(v1Section).toHaveTextContent("1000 IU");
    expect(v1Section).toHaveTextContent("Metformin");
    expect(v1Section).toHaveTextContent("500 mg");

    // In Visit 2: Atorvastatin 20 mg, Vitamin D3 2000 IU
    expect(v2Section).toHaveTextContent("Atorvastatin");
    expect(v2Section).toHaveTextContent("20 mg");
    expect(v2Section).toHaveTextContent("Vitamin D3");
    expect(v2Section).toHaveTextContent("2000 IU");
    expect(v2Section).toHaveTextContent("Metformin");
    expect(v2Section).toHaveTextContent("500 mg");

    // Check intra-visit deduplication: Metformin should appear exactly once in Visit 1's list items
    const v1Items = v1Section.querySelectorAll("li");
    expect(v1Items.length).toBe(3);

    const v2Items = v2Section.querySelectorAll("li");
    expect(v2Items.length).toBe(3);
  });
});
