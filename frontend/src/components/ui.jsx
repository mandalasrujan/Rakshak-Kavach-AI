import { shortId, sourceUrl } from "../api.js";

export function Card({ title, children, actions }) {
  return (
    <section className="rounded-lg bg-white p-4 shadow-sm ring-1 ring-slate-200 sm:p-6">
      {(title || actions) && (
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          {title && <h2 className="text-lg font-semibold">{title}</h2>}
          {actions}
        </div>
      )}
      {children}
    </section>
  );
}

const BUTTON = {
  primary: "bg-emerald-700 text-white hover:bg-emerald-800",
  secondary: "bg-slate-100 text-slate-800 hover:bg-slate-200",
  danger: "bg-red-600 text-white hover:bg-red-700",
};

export function Button({ variant = "primary", className = "", ...props }) {
  return (
    <button
      className={`rounded-md px-3 py-2 text-sm font-medium focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-600 disabled:opacity-50 ${BUTTON[variant]} ${className}`}
      {...props}
    />
  );
}

export function Field({ label, id, ...props }) {
  return (
    <label htmlFor={id} className="block text-sm font-medium text-slate-700">
      {label}
      <input
        id={id}
        className="mt-1 block w-full rounded-md border border-slate-300 px-3 py-2 text-base focus:border-emerald-600 focus:outline-none focus:ring-1 focus:ring-emerald-600"
        {...props}
      />
    </label>
  );
}

export function Alert({ kind = "error", children }) {
  const styles = {
    error: "bg-red-50 text-red-800 ring-red-200",
    success: "bg-emerald-50 text-emerald-800 ring-emerald-200",
    info: "bg-sky-50 text-sky-800 ring-sky-200",
    urgent: "bg-red-600 text-white ring-red-700 font-semibold",
  };
  return (
    <div role={kind === "info" || kind === "success" ? "status" : "alert"} className={`rounded-md p-3 text-sm ring-1 ${styles[kind]}`}>
      {children}
    </div>
  );
}

export function Spinner({ label = "Loading" }) {
  return (
    <p role="status" className="p-4 text-sm text-slate-500">
      <span className="mr-2 inline-block h-3 w-3 animate-spin rounded-full border-2 border-slate-400 border-t-transparent" />
      {label}…
    </p>
  );
}

export function Empty({ children }) {
  return <p className="rounded-md border border-dashed border-slate-300 p-4 text-sm text-slate-500">{children}</p>;
}

const BADGE = {
  ready: "bg-emerald-100 text-emerald-800", active: "bg-emerald-100 text-emerald-800",
  approved: "bg-emerald-100 text-emerald-800", improved: "bg-emerald-100 text-emerald-800",
  queued: "bg-slate-100 text-slate-700", processing: "bg-sky-100 text-sky-800",
  draft: "bg-sky-100 text-sky-800", stable: "bg-slate-100 text-slate-700",
  failed: "bg-red-100 text-red-800", revoked: "bg-red-100 text-red-800",
  locked: "bg-red-100 text-red-800", worsened: "bg-amber-100 text-amber-900",
  expired: "bg-slate-200 text-slate-700", invalidated: "bg-slate-200 text-slate-700",
};

export function Badge({ value }) {
  return (
    <span className={`inline-block rounded px-2 py-0.5 text-xs font-medium ${BADGE[value] ?? "bg-slate-100 text-slate-700"}`}>
      {String(value).replaceAll("_", " ")}
    </span>
  );
}

// Every displayed value links to the exact page of the patient's own source PDF.
export function SourceLink({ documentId, page, excerpt }) {
  return (
    <a
      href={sourceUrl(documentId, page)}
      target="_blank"
      rel="noreferrer noopener"
      className="text-sm text-emerald-800 underline underline-offset-2 hover:text-emerald-900"
      title={excerpt}
    >
      Document {shortId(documentId)}, page {page}
    </a>
  );
}

export const formatDate = (value) => (value ? new Date(value).toLocaleString() : "—");
