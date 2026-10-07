import type { MetadataRoute } from "next";

/** Makes KAFRIADA NET installable on a phone's home screen (the PWA in the plan's Phase 8). */
export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "KAFRIADA NET",
    short_name: "KAFRIADA NET",
    description: "Your permanent football ID. Free.",
    start_url: "/me",
    scope: "/",
    display: "standalone",
    background_color: "#FFFFFF",
    theme_color: "#0EAD2C",
    lang: "en-NG",
    icons: [
      { src: "/icons/icon-192.png", sizes: "192x192", type: "image/png", purpose: "any" },
      { src: "/icons/icon-512.png", sizes: "512x512", type: "image/png", purpose: "any" },
      { src: "/icons/maskable-192.png", sizes: "192x192", type: "image/png", purpose: "maskable" },
      { src: "/icons/maskable-512.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
    ],
  };
}
