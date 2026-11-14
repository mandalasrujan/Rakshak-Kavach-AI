import { shortId, sourceUrl } from "../api.js";
import { IconExternalLink } from "./icons.jsx";

export function Card({ title, subtitle, children, actions, className = "" }) {
  return (
    <section className={`rounded-2xl border border-slate-200/80 bg-white p-5 shadow-[0_1px_3px_rgba(0,0,0,0.04)] transition-all duration-200 hover:shadow-md sm:p-6 ${className}`}>
      {(title || actions || subtitle) && (
        <div className="mb-4 flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 pb-3">
          <div>
            {title && <h2 className="text-lg font-semibold tracking-tight text-slate-900">{title}</h2>}
            {subtitle && <p className="mt-0.5 text-xs text-slate-500">{subtitle}</p>}
          </div>
          {actions && <div className="flex items-center gap-2">{actions}</div>}
        </div>
      )}
      {children}
    </section>
  );
}

const BUTTON = {
  primary:
    "bg-teal-600 text-white hover:bg-teal-700 active:bg-teal-800 shadow-sm hover:shadow focus-visible:ring-teal-500/30",
  secondary:
    "bg-slate-100 text-slate-700 hover:bg-slate-200/80 active:bg-slate-300 border border-slate-200/60 focus-visible:ring-slate-400/30",
  danger:
    "bg-rose-50 text-rose-700 hover:bg-rose-100 active:bg-rose-200 border border-rose-200/80 focus-visible:ring-rose-500/30",
  outline:
    "border border-slate-300 text-slate-700 hover:bg-slate-50 active:bg-slate-100 focus-visible:ring-teal-500/30",
};

export function Button({ variant = "primary", className = "", ...props }) {
  return (
    <button
      className={`inline-flex items-center justify-center gap-1.5 rounded-xl px-4 py-2 text-sm font-medium transition-all duration-150 active:scale-[0.98] focus:outline-none focus-visible:ring-2 disabled:opacity-50 disabled:pointer-events-none ${BUTTON[variant]} ${className}`}
      {...props}
    />
  );
}

export function Field({ label, id, ...props }) {
  return (
    <label htmlFor={id} className="block text-sm font-medium text-slate-700">
      <span className="mb-1.5 block text-xs font-semibold uppercase tracking-wider text-slate-600">
        {label}
      </span>
      <input
        id={id}
        className="mt-1 block w-full rounded-xl border border-slate-200 bg-white px-3.5 py-2.5 text-sm text-slate-900 shadow-sm placeholder:text-slate-400 transition-all duration-150 focus:border-teal-500 focus:outline-none focus:ring-4 focus:ring-teal-500/10"
        {...props}
      />
    </label>
  );
}

export function Alert({ kind = "error", children }) {
  const styles = {
    error: "bg-rose-50/90 text-rose-900 ring-1 ring-rose-200 border-l-4 border-l-rose-500",
    success: "bg-emerald-50/90 text-emerald-900 ring-1 ring-emerald-200 border-l-4 border-l-emerald-500",
    info: "bg-sky-50/90 text-sky-900 ring-1 ring-sky-200 border-l-4 border-l-sky-500",
    urgent: "bg-rose-600 text-white ring-1 ring-rose-700 shadow-md font-semibold",
  };
  return (
    <div
      role={kind === "info" || kind === "success" ? "status" : "alert"}
      className={`rounded-xl p-3.5 text-sm transition-all ${styles[kind]}`}
    >
      {children}
    </div>
  );
}

export function Spinner({ label = "Loading" }) {
  return (
    <div role="status" className="flex items-center gap-2.5 p-4 text-sm font-medium text-slate-500">
      <span className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-teal-600 border-t-transparent" />
      <span>{label}…</span>
    </div>
  );
}

export function Empty({ children }) {
  return (
    <div className="flex flex-col items-center justify-center rounded-2xl border-2 border-dashed border-slate-200 bg-slate-50/50 p-8 text-center text-sm text-slate-500">
      <p>{children}</p>
    </div>
  );
}

const BADGE = {
  ready: "bg-emerald-50 text-emerald-700 ring-emerald-600/20",
  active: "bg-emerald-50 text-emerald-700 ring-emerald-600/20",
  approved: "bg-emerald-50 text-emerald-700 ring-emerald-600/20",
  improved: "bg-emerald-50 text-emerald-700 ring-emerald-600/20",
  queued: "bg-slate-100 text-slate-600 ring-slate-500/20",
  processing: "bg-sky-50 text-sky-700 ring-sky-600/20 animate-pulse",
  draft: "bg-amber-50 text-amber-700 ring-amber-600/20",
  stable: "bg-slate-100 text-slate-700 ring-slate-600/20",
  failed: "bg-rose-50 text-rose-700 ring-rose-600/20",
  revoked: "bg-rose-50 text-rose-700 ring-rose-600/20",
  locked: "bg-rose-50 text-rose-700 ring-rose-600/20",
  worsened: "bg-amber-50 text-amber-800 ring-amber-600/20",
  expired: "bg-slate-100 text-slate-500 ring-slate-400/20",
  invalidated: "bg-slate-100 text-slate-500 ring-slate-400/20",
};

export function Badge({ value }) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium ring-1 ring-inset ${
        BADGE[value] ?? "bg-slate-100 text-slate-700 ring-slate-600/20"
      }`}
    >
      <span className="h-1.5 w-1.5 rounded-full bg-current opacity-70" />
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
      className="inline-flex items-center gap-1 rounded-lg border border-teal-200/70 bg-teal-50/70 px-2 py-0.5 text-xs font-medium text-teal-800 transition-colors hover:border-teal-300 hover:bg-teal-100/90"
      title={excerpt}
    >
      <span>Document {shortId(documentId)}, page {page}</span>
      <IconExternalLink className="h-3 w-3 opacity-70" />
    </a>
  );
}

export const formatDate = (value) => (value ? new Date(value).toLocaleString() : "—");
