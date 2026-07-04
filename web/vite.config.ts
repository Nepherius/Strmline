import { sveltekit } from "@sveltejs/kit/vite";
import { loadEnv } from "vite";
import { defineConfig } from "vitest/config";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, ".", "");
  const apiTarget = env["STRMLINE_API_PROXY_TARGET"] ?? "http://127.0.0.1:8001";
  return {
    plugins: [sveltekit()],
    server: {
      proxy: {
        "/api": apiTarget,
        "/play": apiTarget,
      },
    },
  };
});
