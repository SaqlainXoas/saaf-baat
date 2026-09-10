import type { Metadata, Viewport } from "next";
import "./globals.css";
import ThemeProvider from "@/components/ThemeProvider";
import { normaliseTheme } from "@/utils/theme";

const SITE_URL = process.env.NEXT_PUBLIC_SITE_URL || "http://localhost:3000";
const TITLE = "Saaf Baat — Pakistan Morning Brief";
const DESCRIPTION =
  "A calm, finite morning news brief for Pakistan. Six to twelve stories that matter, " +
  "why each one changes your day, and the original sources one tap away.";

export const metadata: Metadata = {
  metadataBase: new URL(SITE_URL),
  title: { default: TITLE, template: "%s — Saaf Baat" },
  description: DESCRIPTION,
  applicationName: "Saaf Baat",
  icons: {
    icon: "/icon.svg",
    apple: "/icon.svg",
  },
  openGraph: {
    type: "website",
    siteName: "Saaf Baat",
    title: TITLE,
    description: DESCRIPTION,
    locale: "en_PK",
  },
  twitter: { card: "summary", title: TITLE, description: DESCRIPTION },
};

// Matches --paper in globals.css for each scheme, so the browser chrome does
// not flash a colour the page never uses.
export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#f2ece4" },
    { media: "(prefers-color-scheme: dark)", color: "#0d1111" },
  ],
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const defaultTheme = normaliseTheme(process.env.NEXT_PUBLIC_DEFAULT_THEME, "system");

  return (
    <html lang="en" data-theme={defaultTheme} suppressHydrationWarning>
      <body>
        <ThemeProvider defaultTheme={defaultTheme}>{children}</ThemeProvider>
      </body>
    </html>
  );
}
