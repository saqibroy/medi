import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  build: {
    chunkSizeWarningLimit: 1300,
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.includes("@cornerstonejs")) {
            return "viewer";
          }
          if (id.includes("react") || id.includes("react-dom")) {
            return "react";
          }
        },
      },
    },
  },
});
