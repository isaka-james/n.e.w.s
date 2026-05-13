"use client";

import { useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { LogOut, Menu, X } from "lucide-react";
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
  // Mobile drawer state — the sidebar is hidden by default below the md breakpoint
  // and slides in as an overlay when the hamburger is tapped.
  const [drawerOpen, setDrawerOpen] = useState(false);

  const handleLogout = () => {
    logout();
    router.push("/login");
  };

  const closeDrawer = () => setDrawerOpen(false);

  return (
    <>
      {/* Mobile top bar — only visible on small screens */}
      <header
        className="md:hidden fixed top-0 left-0 right-0 z-30 flex items-center justify-between px-5 py-3"
        style={{ background: "#0a0f1e", borderBottom: "1px solid #1e2d4a" }}
      >
        <button
          onClick={() => setDrawerOpen(true)}
          className="p-1.5"
          style={{ color: "#e2e8f0" }}
          aria-label="Open navigation"
        >
          <Menu size={18} strokeWidth={1.8} />
        </button>
        <Link href="/dashboard" className="flex items-center gap-2">
          <span
            className="text-[18px] leading-none"
            style={{
              fontFamily: "'Rufina', Georgia, serif",
              color: "#ffffff",
              letterSpacing: "0.04em",
            }}
          >
            N.E.W.S.
          </span>
        </Link>
        <button
          onClick={() => setPanelOpen(true)}
          className="text-[10px] tracking-[0.18em] uppercase font-semibold"
          style={{ color: unread > 0 ? "#b8962e" : "#8b9cb8" }}
          aria-label="Activity"
        >
          {unread > 0 ? `Activity · ${unread}` : "Activity"}
        </button>
      </header>

      {/* Mobile drawer backdrop */}
      {drawerOpen && (
        <div
          className="md:hidden fixed inset-0 z-40"
          style={{ background: "rgba(10, 15, 30, 0.5)" }}
          onClick={closeDrawer}
          aria-hidden
        />
      )}

      {/* Sidebar — fixed/drawer on mobile, static on desktop */}
      <aside
        className={`editorial-pattern-dark flex flex-col flex-shrink-0 overflow-y-auto
          fixed md:sticky md:top-0 left-0 top-0 h-screen w-64 z-50
          transition-transform duration-300
          ${drawerOpen ? "translate-x-0" : "-translate-x-full"}
          md:translate-x-0`}
        style={{ borderRight: "1px solid #1e2d4a" }}
      >
        {/* Drawer close — visible only on mobile */}
        <button
          onClick={closeDrawer}
          className="md:hidden absolute top-4 right-4 p-1.5"
          style={{ color: "#8b9cb8" }}
          aria-label="Close navigation"
        >
          <X size={16} strokeWidth={1.8} />
        </button>

        {/* Wordmark */}
        <Link href="/dashboard" onClick={closeDrawer} className="block px-7 pt-9 pb-6">
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
                  onClick={closeDrawer}
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
            onClick={() => { setPanelOpen(true); closeDrawer(); }}
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
