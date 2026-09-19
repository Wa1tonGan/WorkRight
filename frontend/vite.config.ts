import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The backend (FastAPI + the agent loop) runs on :8000. Proxying here keeps
// everything SAME-ORIGIN for the browser, so the httpOnly session cookie
// flows naturally and no CORS configuration is needed in the backend.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/auth": "http://127.0.0.1:8000",
      "/chat": "http://127.0.0.1:8000",
      "/health": "http://127.0.0.1:8000",
      "/policy": "http://127.0.0.1:8000",
      "/requests": "http://127.0.0.1:8000",
      "/pending": "http://127.0.0.1:8000",
      "/conversations": "http://127.0.0.1:8000",
    },
  },
});
