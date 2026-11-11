import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The dev server proxies /api to the API, so the browser sees one origin and the
// httpOnly session cookie flows without CORS. The API's FRONTEND_ORIGIN must match this origin.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { "/api": { target: "http://127.0.0.1:8000", changeOrigin: false } },
  },
});
