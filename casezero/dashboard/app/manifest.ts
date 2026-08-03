import type { MetadataRoute } from "next";

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "CaseZero — MYBank Dispute Tracker",
    short_name: "CaseZero",
    description: "Track and govern MYBank complaints.",
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
