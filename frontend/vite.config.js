import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Vite 와 Vitest 설정을 한 파일에서 함께 관리한다.
export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/setupTests.js"],
  },
});
