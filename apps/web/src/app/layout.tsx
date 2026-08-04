import type { Metadata, Viewport } from "next";

import { ToastProvider } from "@shield/design-system";

import { AuthSessionProvider } from "@/components/AuthSessionProvider";

import "./globals.css";

export const metadata: Metadata = {
  title: {
    default: "SHIELD by Kentro",
    template: "%s · SHIELD by Kentro",
  },
  description:
    "SHIELD by Kentro - enterprise cybersecurity assessment platform. Technical Debt, Zero Trust, NIST CSF 2.0, MITRE ATT&CK Coverage.",
  applicationName: "SHIELD by Kentro",
  robots: { index: false, follow: false },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: "#0e1220",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="min-h-screen font-sans">
        <AuthSessionProvider>
          <ToastProvider>{children}</ToastProvider>
        </AuthSessionProvider>
      </body>
    </html>
  );
}
