import type { Metadata } from "next";
import "./globals.css";
import ThemeProvider from "@/components/ThemeProvider";
import { normaliseTheme } from "@/utils/theme";

export const metadata: Metadata = {
  title: "Saaf Baat — Morning Brief",
  description:
    "A calm, finite morning news brief for Pakistan. Trust signals and original sources, one tap away.",
  icons: { icon: "/icon.svg" },
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
