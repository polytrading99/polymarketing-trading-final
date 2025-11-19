import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Poly Maker Dashboard",
  description: "Control plane for Polymarket market-making bot"
};

export default function RootLayout({
  children
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="min-h-screen">
        <div className="mx-auto max-w-6xl px-6 py-10">{children}</div>
      </body>
    </html>
  );
}


