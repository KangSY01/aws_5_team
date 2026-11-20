import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

// Vite 와 Vitest 설정을 한 파일에서 함께 관리한다.
export default defineConfig(({ mode }) => {
  const target = loadEnv(mode, import.meta.dirname, "VITE_").VITE_API_BASE_URL?.trim();
  return {
    server: {
      proxy: target ? {
        "/__busannow_api": {
          target: target.replace(/\/+$/, ""),
          changeOrigin: true,
          rewrite: (path) => path.replace(/^\/__busannow_api/, ""),
        },
      } : undefined,
    },
    plugins: [react()],
    test: {
      environment: "jsdom",
      globals: true,
      setupFiles: ["./src/setupTests.js"],
    },
  };
});
