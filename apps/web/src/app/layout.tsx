import type { Metadata } from "next";
import { Geist, Geist_Mono, Fraunces } from "next/font/google";
import { AppShell } from "@/components/app-shell";
import { ChatStoreProvider } from "@/components/chat/chat-store-context";
import "./globals.css";

const geistSans = Geist({ variable: "--font-sans", subsets: ["latin"] });
const geistMono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] });
const fraunces = Fraunces({ variable: "--font-serif", subsets: ["latin"], weight: ["400", "500", "600"] });

export const metadata: Metadata = {
  title: "CSI Bid Assistant",
  description: "Central Specialties' estimating copilot — ask the plans, flag the gotchas, cite every figure.",
};

// Chat is still the home route ("/"), but the CI-data admin pages (bid results, pit list,
// competitor registry) need real navigation between pages, so the shell is on for all of them.
export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} ${fraunces.variable} h-full antialiased`}
    >
      <body className="h-full">
        <ChatStoreProvider>
          <AppShell>{children}</AppShell>
        </ChatStoreProvider>
      </body>
    </html>
  );
}
