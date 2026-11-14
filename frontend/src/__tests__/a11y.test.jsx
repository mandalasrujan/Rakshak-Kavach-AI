import { render } from "@testing-library/react";
import axe from "axe-core";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { AuthProvider } from "../auth.jsx";
import { AppRoutes, ROUTER_FUTURE } from "../main.jsx";
import { Answer } from "../pages/Assistant.jsx";
import DoctorShare from "../pages/DoctorShare.jsx";
import { stubApi } from "./helpers.js";

// Automated WCAG checks (axe-core) on key screens. jsdom cannot compute colour contrast, so
// that rule is checked manually in the M17 report instead.
async function violations(container) {
  const result = await axe.run(container, { rules: { "color-contrast": { enabled: false } } });
  return result.violations.map((v) => `${v.id}: ${v.nodes.length}`);
}

describe("accessibility", () => {
  it("login page has no axe violations", async () => {
    stubApi({ "GET /patient/me": [401, { error: { code: "not_authenticated", message: "x" } }] });
    const { container, findByRole } = render(
      <MemoryRouter initialEntries={["/login"]} future={ROUTER_FUTURE}><AuthProvider><AppRoutes /></AuthProvider></MemoryRouter>,
    );
    await findByRole("heading", { name: "Sign in" });
    expect(await violations(container)).toEqual([]);
  });

  it("doctor PIN page has no axe violations", async () => {
    window.history.pushState(null, "", "/share#t=TOKEN_abcdefghijklmnopqrstuvwxyz0123456789");
    const { container, findByLabelText } = render(<DoctorShare />);
    await findByLabelText("6-digit PIN");
    expect(await violations(container)).toEqual([]);
  });

  it("answers with citations have no axe violations", async () => {
    const { container } = render(<Answer reply={{ found: true, urgent: false, answer: "HbA1c 7.6 %", citations: [
      { document_id: "doc-12345678", page: 1, chunk_id: "c1", excerpt: "Test: HbA1c; Result: 7.6" }] }} />);
    expect(await violations(container)).toEqual([]);
  });
});
