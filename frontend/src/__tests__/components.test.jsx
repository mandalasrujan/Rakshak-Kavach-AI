import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Answer } from "../pages/Assistant.jsx";
import { CreatedShare } from "../pages/Sharing.jsx";

describe("assistant answers", () => {
  it("render urgent guidance as an alert with no sources", () => {
    render(<Answer reply={{ urgent: true, found: false, answer: "Please call 112 now.", citations: [] }} />);
    expect(screen.getByRole("alert")).toHaveTextContent("Please call 112 now.");
  });

  it("link every citation to its source page", () => {
    render(<Answer reply={{ urgent: false, found: true, answer: "HbA1c 7.6 %", citations: [
      { document_id: "doc-12345678", page: 2, chunk_id: "c1", excerpt: "Test: HbA1c; Result: 7.6" },
    ] }} />);
    const link = screen.getByRole("link", { name: "Document doc-1234, page 2" });
    expect(link).toHaveAttribute("href", "/api/v1/patient/documents/doc-12345678/file#page=2");
    expect(link).toHaveAttribute("rel", "noreferrer noopener");
  });
});

describe("created share", () => {
  it("shows the QR code and PIN once without storing them", async () => {
    render(<CreatedShare created={{ share_url: "https://app.example/share#t=secret-token", pin: "042137", expires_at: "2026-11-11T10:00:00Z", scope: "summary_only" }} onDone={() => {}} />);
    expect(screen.getByLabelText("Share PIN")).toHaveTextContent("042137");
    expect(await screen.findByAltText("Share QR code")).toHaveAttribute("src", expect.stringMatching(/^data:image\/png/));
    expect(window.localStorage.length + window.sessionStorage.length).toBe(0);
  });
});
