import type { Metadata, Viewport } from "next";
import { Instrument_Sans, Martian_Mono } from "next/font/google";
import { ServiceWorkerRegister } from "@/components/service-worker-register";
import "./globals.css";

const instrument = Instrument_Sans({
  subsets: ["latin"],
  variable: "--font-instrument",
  display: "swap",
});
const martian = Martian_Mono({
  subsets: ["latin"],
  variable: "--font-martian",
  display: "swap",
});

export const metadata: Metadata = {
  title: { default: "CaseZero — Governed dispute operations", template: "%s · CaseZero" },
  description: "Axiom and six governed agents resolve banking disputes with deterministic financial and compliance controls.",
  applicationName: "CaseZero",
  manifest: "/manifest.webmanifest",
};

export const viewport: Viewport = { themeColor: "#E4EAE5", colorScheme: "light" };

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className={`${instrument.variable} ${martian.variable}`}>
      <body>
        <ServiceWorkerRegister />
        <a className="skip-link" href="#main-content">Skip to case workspace</a>
        {children}
      </body>
    </html>
  );
}
