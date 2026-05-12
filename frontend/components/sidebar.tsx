"use client";

import { useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { LogOut } from "lucide-react";
import { useAuth } from "@/lib/auth-context";
import { useNotifications } from "@/lib/notifications-context";
import { NotificationPanel } from "@/components/notification-panel";

const NAV = [
  { href: "/dashboard", label: "Briefing"  },
  { href: "/settings",  label: "Settings"  },
  { href: "/advanced",  label: "Advanced"  },
];

export function Sidebar() {
  const pathname = usePathname();
  const router = useRouter();
  const { user, logout } = useAuth();
  const { unread } = useNotifications();
  const [panelOpen, setPanelOpen] = useState(false);

  const handleLogout = () => {
    logout();
    router.push("/login");
  };

  return (
    <>
      <aside
        className="editorial-pattern-dark sticky top-0 h-screen w-64 flex flex-col flex-shrink-0 overflow-y-auto"
        style={{ borderRight: "1px solid #1e2d4a" }}
      >
        {/* Wordmark */}
        <Link href="/dashboard" className="block px-7 pt-9 pb-6">
          <h1
            className="text-[26px] leading-none mb-2"
            style={{
              fontFamily: "'Rufina', Georgia, serif",
              color: "#ffffff",
              letterSpacing: "0.04em",
            }}
          >
            N.E.W.S.
          </h1>
          <p
            className="text-[9px] tracking-[0.25em] uppercase"
            style={{ color: "#b8962e", fontWeight: 600 }}
          >
            Your world, filtered
          </p>
        </Link>

        <div className="mx-7 h-px" style={{ background: "#b8962e", opacity: 0.45 }} />

        {/* Navigation */}
        <nav className="px-7 pt-8 pb-6">
          <p
            className="text-[9px] tracking-[0.28em] uppercase mb-5"
            style={{ color: "#6b7fa0", fontWeight: 600 }}
          >
            Sections
          </p>

          <div className="space-y-0.5">
            {NAV.map(({ href, label }) => {
              const active = pathname.startsWith(href);
              return (
                <Link
                  key={href}
                  href={href}
                  className="block py-2 text-[16px] transition-colors relative"
                  style={{
                    fontFamily: "'Rufina', Georgia, serif",
                    color: active ? "#ffffff" : "#8b9cb8",
                  }}
                >
                  <span
                    style={{
                      position: "absolute",
                      left: "-14px",
                      top: "50%",
                      transform: "translateY(-50%)",
                      width: "6px",
                      height: "1px",
                      background: active ? "#b8962e" : "transparent",
                    }}
                  />
                  {label}
                </Link>
              );
            })}
          </div>
        </nav>

        <div className="mx-7 h-px" style={{ background: "#1e2d4a" }} />

        {/* Activity — peer to nav, not a footer button */}
        <nav className="px-7 pt-6 pb-6">
          <p
            className="text-[9px] tracking-[0.28em] uppercase mb-5"
            style={{ color: "#6b7fa0", fontWeight: 600 }}
          >
            Desk
          </p>

          <button
            onClick={() => setPanelOpen(true)}
            className="w-full flex items-center justify-between py-2 transition-colors group"
            style={{ color: unread > 0 ? "#ffffff" : "#8b9cb8" }}
          >
            <span
              className="text-[16px]"
              style={{ fontFamily: "'Rufina', Georgia, serif" }}
            >
              Activity
            </span>
            {unread > 0 ? (
              <span
                className="text-[10px] font-semibold tracking-[0.05em] px-2 py-0.5"
                style={{ background: "#b8962e", color: "#0a0f1e" }}
              >
                {unread}
              </span>
            ) : (
              <span
                className="text-[10px] tracking-[0.15em] uppercase"
                style={{ color: "#6b7fa0" }}
              >
                —
              </span>
            )}
          </button>
        </nav>

        <div className="flex-1" />

        {/* User footer */}
        <div className="mx-7 h-px" style={{ background: "#1e2d4a" }} />
        <div className="px-7 py-6">
          {user && (
            <div className="mb-5">
              <p
                className="text-[14px] mb-0.5"
                style={{ fontFamily: "'Rufina', Georgia, serif", color: "#e2e8f0" }}
              >
                {user.name}
              </p>
              <p className="text-[10px] tracking-[0.12em]" style={{ color: "#6b7fa0" }}>
                {user.city}, {user.country}
              </p>
            </div>
          )}

          <button
            onClick={handleLogout}
            className="flex items-center gap-2 text-[10px] tracking-[0.22em] uppercase font-semibold transition-colors"
            style={{ color: "#6b7fa0" }}
          >
            <LogOut size={11} strokeWidth={1.8} />
            Sign out
          </button>
        </div>
      </aside>

      <NotificationPanel open={panelOpen} onClose={() => setPanelOpen(false)} />
    </>
  );
}
