import type { Metadata } from "next";
import "./globals.css";
import { AuthProvider } from "@/lib/auth-context";
import { NotificationsProvider } from "@/lib/notifications-context";
import { Toaster } from "@/components/ui/sonner";

export const metadata: Metadata = {
  title: "N.E.W.S. — Your World, Filtered",
  description: "A personal AI news briefing system across four geographic layers.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className="h-full">
      <body className="min-h-full" style={{ background: "#f5f1eb" }}>
        <AuthProvider>
          <NotificationsProvider>
            {children}
            <Toaster
              theme="light"
              toastOptions={{
                style: {
                  background: "#ffffff",
                  border: "1px solid #d8d0c4",
                  color: "#0a0f1e",
                  borderRadius: "2px",
                  fontFamily: "Inter, sans-serif",
                },
              }}
            />
          </NotificationsProvider>
        </AuthProvider>
      </body>
    </html>
  );
}
