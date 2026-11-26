import type { Metadata } from "next";
import "./globals.css";
import Providers from "@/components/Providers";
import AppLayout from "@/components/AppLayout";

export const metadata: Metadata = {
  title: "AI Consulting Workflow",
  description:
    "An AI-powered consulting workflow platform for end-to-end project management.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="h-full">
      <body className="min-h-full font-sans antialiased text-slate-900 dark:text-slate-50 bg-slate-50 dark:bg-slate-950">
        <Providers>
          <AppLayout>{children}</AppLayout>
        </Providers>
      </body>
    </html>
  );
}
