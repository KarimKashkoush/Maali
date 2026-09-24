import type { Metadata, Viewport } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";
import { Cairo } from "next/font/google";
import Navbar from "./_components/layout/navbar/Navbar";
import AuthGate from "./_components/AuthGate";


const cairo = Cairo({
  subsets: ["arabic", "latin"],
  weight: ["300", "400", "500", "600", "700"],
  variable: "--font-cairo",
});


const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "غياب المعالي",
  applicationName: "غياب المعالي",
  appleWebApp: { capable: true, title: "غياب المعالي", statusBarStyle: "default" },
  icons: { apple: "/icons/maali-192.png" },
  description: "إدارة المدارس والفصول والطلاب والحضور",
};

export const viewport: Viewport = { themeColor: "#0F4C3A" };

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="ar"
      dir="rtl"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className={`min-h-full bg-[#F7F5F0] rtl ${cairo.className}`}>
        <Navbar />

        <main className="container">
          <AuthGate>{children}</AuthGate>
        </main>
      </body>
    </html>
  );
}
