import { defineConfig, type Plugin } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// Every build gets an id, baked into the bundle and published as
// /version.json. Installed apps (an iOS home-screen app can stay in memory
// for days) compare the two and reload themselves when they differ.
const BUILD_ID = new Date().toISOString();

function versionFile(): Plugin {
  return {
    name: "openunifi-version-file",
    apply: "build",
    generateBundle() {
      this.emitFile({ type: "asset", fileName: "version.json", source: JSON.stringify({ build: BUILD_ID }) });
    },
  };
}

export default defineConfig({
  plugins: [react(), tailwindcss(), versionFile()],
  define: {
    __BUILD_ID__: JSON.stringify(BUILD_ID),
  },
  server: {
    proxy: {
      "/api": "http://localhost:8000",
      "/rss": "http://localhost:8000",
    },
  },
});
