import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// One origin for the browser: each backend service sits behind a path prefix.
// docker/nginx.conf does the same in production.
const services: Record<string, number> = {
  auth: 8001,
  projects: 8002,
  viva: 8006,
};

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: Object.fromEntries(
      Object.entries(services).map(([name, port]) => [
        `/svc/${name}`,
        {
          target: `http://localhost:${port}`,
          rewrite: (path: string) => path.replace(`/svc/${name}`, ""),
        },
      ]),
    ),
  },
});
