import type { Metadata } from "next";
import "./globals.css";
import { QueueDepthBadge } from "@/components/QueueDepthBadge";

export const metadata: Metadata = {
  title: "Sales Lead Agent",
  description: "AI-powered lead enrichment and scoring dashboard",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <div className="min-h-screen flex flex-col">
          <header className="sticky top-0 z-10 border-b border-gray-200 bg-white/80 backdrop-blur">
            <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-3">
              <div className="flex items-center gap-2">
                <span className="text-lg font-bold text-brand-600">LeadAgent</span>
                <span className="rounded bg-brand-50 px-1.5 py-0.5 text-xs font-medium text-brand-700">
                  AI
                </span>
              </div>
              <QueueDepthBadge />
            </div>
          </header>
          <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-8">
            {children}
          </main>
        </div>
      </body>
    </html>
  );
}
