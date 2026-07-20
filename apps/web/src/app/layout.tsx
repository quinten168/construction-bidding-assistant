import type { Metadata } from "next";
import { Geist, Geist_Mono, Fraunces } from "next/font/google";
import "./globals.css";

const geistSans = Geist({ variable: "--font-sans", subsets: ["latin"] });
const geistMono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] });
const fraunces = Fraunces({ variable: "--font-serif", subsets: ["latin"], weight: ["400", "500", "600"] });

export const metadata: Metadata = {
  title: "CSI Bid Assistant",
  description: "Central Specialties' estimating copilot — ask the plans, flag the gotchas, cite every figure.",
};

// Chatbot-only MVP — no app shell. The whole product is the chat.
export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} ${fraunces.variable} h-full antialiased`}
    >
      <body className="h-full">{children}</body>
    </html>
  );
}
