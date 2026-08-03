import type { MetadataRoute } from "next";

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "CaseZero — Governed Dispute Operations",
    short_name: "CaseZero",
    description: "Track and govern banking complaints with Axiom by CaseZero.",
    start_url: "/",
    display: "standalone",
    background_color: "#E4EAE5",
    theme_color: "#E4EAE5",
    icons: [
      { src: "/icon.svg", sizes: "any", type: "image/svg+xml", purpose: "any" },
    ],
    shortcuts: [
      { name: "Track a complaint", short_name: "Tracker", url: "/track/demo" },
      { name: "Review flagged transaction", short_name: "Was this you?", url: "/proactive/demo-proactive-techworld-2026" },
    ],
  };
}
