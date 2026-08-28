import { defineConfig, type Plugin } from "vite";
import react from "@vitejs/plugin-react";
import { VitePWA } from "vite-plugin-pwa";
import pkg from "./package.json";
import { CHANGELOG } from "./src/changelog";

/** Info versi yang dipublish sebagai /version.json (tidak di-precache SW).
 *  Klien lama mengambilnya saat SW baru terdeteksi → tampilkan "apa yang baru"
 *  sebelum reload (lihat src/ui/UpdateButton.tsx). */
function versionInfo(): string {
  const latest = CHANGELOG[0];
  return JSON.stringify(
    {
      version: pkg.version,
      builtAt: new Date().toISOString(),
      notes: latest && latest.version === pkg.version ? latest.notes : [],
      history: CHANGELOG,
    },
    null,
    2,
  );
}

function versionJsonPlugin(): Plugin {
  return {
    name: "octopus-version-json",
    generateBundle() {
      this.emitFile({ type: "asset", fileName: "version.json", source: versionInfo() });
    },
    configureServer(server) {
      server.middlewares.use((req, res, next) => {
        const url = (req as { url?: string }).url ?? "";
        if (url.split("?")[0] !== "/version.json") return next();
        res.setHeader("Content-Type", "application/json");
        res.setHeader("Cache-Control", "no-store");
        res.end(versionInfo());
      });
    },
  };
}

export default defineConfig({
  define: {
    __APP_VERSION__: JSON.stringify(pkg.version),
  },
  server: {
    host: true,
    allowedHosts: true, // izinkan host tunnel (trycloudflare) di dev
    proxy: {
      "/chat": { target: "http://localhost:8080", changeOrigin: true },
      "/room": { target: "http://localhost:8080", changeOrigin: true },
      "/auth": { target: "http://localhost:8080", changeOrigin: true },
      "/push": { target: "http://localhost:8080", changeOrigin: true },
    },
  },
  plugins: [
    react(),
    versionJsonPlugin(),
    VitePWA({
      // "prompt": SW baru menunggu (waiting) sampai user tekan "Perbarui" di
      // UpdateButton → tidak reload mendadak saat user sedang mengetik/approve.
      registerType: "prompt",
      strategies: "injectManifest",
      srcDir: "src",
      filename: "sw.ts",
      injectManifest: {
        globPatterns: ["**/*.{js,css,html,svg,png,woff2}"],
        globIgnores: ["**/version.json"],
      },
      includeAssets: ["favicon.svg", "apple-touch-icon.png"],
      manifest: {
        name: "Ruang Octopus",
        short_name: "Octopus",
        description:
          "Gather-room untuk AI IT-Manager — office virtual tempat Manajer AI mengoordinasi pasukan agen.",
        theme_color: "#0d9e88",
        background_color: "#0b111c",
        display: "standalone",
        orientation: "any",
        start_url: "/",
        icons: [
          { src: "pwa-192.svg", sizes: "192x192", type: "image/svg+xml", purpose: "any maskable" },
          { src: "pwa-512.svg", sizes: "512x512", type: "image/svg+xml", purpose: "any maskable" },
          { src: "pwa-192.png", sizes: "192x192", type: "image/png", purpose: "any" },
          { src: "pwa-512.png", sizes: "512x512", type: "image/png", purpose: "any" },
          { src: "pwa-512.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
        ],
      },
    }),
  ],
});
