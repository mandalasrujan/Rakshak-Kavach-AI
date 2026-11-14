import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import DoctorShare from "../pages/DoctorShare.jsx";
import { stubApi } from "./helpers.js";

const VIEW = {
  scope: "summary_only", session_expires_at: "2026-11-11T10:30:00Z", snapshot_version: 1,
  approved_at: "2026-11-11T09:00:00Z",
  summary: { medications: [{ name: "Metformin 500 mg", dose: "1 tablet", frequency: "Twice daily", duration: "90 days" }],
    labs: [], missing: { labs: "No lab results were found." }, narrative: { status: "empty" }, note: "Not a diagnosis." },
};

describe("doctor share page", () => {
  it("strips the token from the URL, never stores it, and opens the view with the PIN", async () => {
    window.history.pushState(null, "", "/share#t=TOKEN_abcdefghijklmnopqrstuvwxyz0123456789");
    const calls = stubApi({ "POST /share/sessions": [200, { scope: "summary_only", expires_at: VIEW.session_expires_at }], "GET /share/view": [200, VIEW] });
    render(<DoctorShare />);
    expect(window.location.hash).toBe("");
    expect(window.location.href).not.toContain("TOKEN_");
    await userEvent.type(screen.getByLabelText("6-digit PIN"), "123456");
    await userEvent.click(screen.getByRole("button", { name: "Open read-only summary" }));
    expect(await screen.findByText(/Metformin 500 mg/)).toBeInTheDocument();
    const exchange = calls.find((c) => c.path === "/share/sessions");
    expect(JSON.parse(exchange.init.body)).toMatchObject({ token: "TOKEN_abcdefghijklmnopqrstuvwxyz0123456789", pin: "123456" });
    expect(exchange.init.headers["X-CSRF-Protection"]).toBe("1");
    expect(window.localStorage.length + window.sessionStorage.length).toBe(0);
    expect(screen.queryByText(/Source:/)).not.toBeInTheDocument();  // summary_only: no sources
  });

  it("explains a wrong PIN and clears the field", async () => {
    window.history.pushState(null, "", "/share#t=TOKEN_abcdefghijklmnopqrstuvwxyz0123456789");
    stubApi({ "POST /share/sessions": [401, { error: { code: "invalid_pin", message: "Incorrect PIN." } }] });
    render(<DoctorShare />);
    await userEvent.type(screen.getByLabelText("6-digit PIN"), "000000");
    await userEvent.click(screen.getByRole("button", { name: "Open read-only summary" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("locks after five wrong attempts");
    expect(screen.getByLabelText("6-digit PIN")).toHaveValue("");
  });
});
