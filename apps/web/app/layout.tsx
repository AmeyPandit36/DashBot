import type { Metadata, Viewport } from "next";
import "@fontsource-variable/inter";
import "@fontsource-variable/sora";
import "./globals.css";
import { Providers } from "@/components/providers";

export const metadata: Metadata = {
  title: {
    default: "Agentic BI — Your data, an intelligent perspective",
    template: "%s · Agentic BI",
  },
  description:
    "Upload business data, generate interactive dashboards and interrogate performance with an AI analyst that answers from real SQL execution.",
  icons: { icon: "/branding/favicon.svg" },
  openGraph: {
    title: "Agentic BI",
    description: "AI-powered business intelligence with verified, SQL-backed answers.",
    type: "website",
  },
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#F4F6FF" },
    { media: "(prefers-color-scheme: dark)", color: "#090D1C" },
  ],
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
