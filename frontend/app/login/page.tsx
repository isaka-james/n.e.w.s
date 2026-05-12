"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { toast } from "sonner";
import { Eye, EyeOff, Loader2 } from "lucide-react";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";

export default function LoginPage() {
  const router = useRouter();
  const { login } = useAuth();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPw, setShowPw] = useState(false);
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    try {
      const res = await api.auth.login({ email, password });
      login(res.access_token, res.user);
      router.push("/dashboard");
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : "Login failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex" style={{ background: "#f5f1eb" }}>

      {/* Left panel — dark editorial with pattern */}
      <div className="editorial-pattern-dark hidden md:flex md:w-1/2 flex-col justify-between p-12 relative overflow-hidden">

        {/* Decorative ornament — large faded N.E.W.S. mark */}
        <div
          className="absolute pointer-events-none"
          style={{
            right: "-40px",
            top: "50%",
            transform: "translateY(-50%) rotate(-90deg)",
            fontFamily: "'Rufina', Georgia, serif",
            fontSize: "140px",
            color: "rgba(184, 150, 46, 0.06)",
            letterSpacing: "0.3em",
            fontWeight: 400,
            whiteSpace: "nowrap",
          }}
        >
          N · E · W · S
        </div>

        {/* Vertical thin gold bar — magazine spine accent */}
        <div
          className="absolute"
          style={{
            left: "0",
            top: "20%",
            bottom: "20%",
            width: "2px",
            background: "#b8962e",
            opacity: 0.5,
          }}
        />

        <div className="relative z-10">
          <h1
            className="text-[42px] leading-none"
            style={{
              fontFamily: "'Rufina', Georgia, serif",
              color: "#ffffff",
              letterSpacing: "0.03em",
            }}
          >
            N.E.W.S.
          </h1>
          <p
            className="text-[10px] tracking-[0.25em] uppercase mt-3"
            style={{ color: "#b8962e", fontWeight: 600 }}
          >
            Your world, filtered
          </p>
        </div>

        <div className="max-w-md relative z-10">
          <div className="gold-rule mb-8" style={{ width: "60px" }} />
          <p
            className="text-[26px] leading-[1.35] italic"
            style={{ fontFamily: "'Rufina', Georgia, serif", color: "#e2e8f0", fontWeight: 400 }}
          >
            A daily briefing across four layers — your city, your country, your continent, the world.
          </p>
          <p
            className="text-[11px] tracking-[0.3em] uppercase mt-8"
            style={{ color: "#6b7fa0", fontWeight: 600 }}
          >
            Narrow · Expanded · Wide · Sweeping
          </p>
        </div>

        <p className="relative z-10 text-[10px] tracking-[0.2em] uppercase" style={{ color: "#6b7fa0" }}>
          A personal news institution
        </p>
      </div>

      {/* Right panel — form */}
      <div className="flex-1 flex items-center justify-center px-6 md:px-12">
        <div className="w-full max-w-md">

          <p
            className="text-[10px] tracking-[0.3em] uppercase mb-3"
            style={{ color: "#b8962e", fontWeight: 600 }}
          >
            Sign in
          </p>
          <h2
            className="text-[36px] leading-none mb-2"
            style={{ fontFamily: "'Rufina', Georgia, serif", color: "#0a0f1e" }}
          >
            Welcome back.
          </h2>
          <p className="text-[14px] mb-10" style={{ color: "#787878" }}>
            Continue to your daily briefing.
          </p>

          <form onSubmit={handleSubmit} className="space-y-6">
            <div>
              <label
                className="block text-[10px] tracking-[0.22em] uppercase mb-2"
                style={{ color: "#3a3a3a", fontWeight: 600 }}
              >
                Email
              </label>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                placeholder="you@example.com"
                className="editorial-input"
              />
            </div>

            <div>
              <label
                className="block text-[10px] tracking-[0.22em] uppercase mb-2"
                style={{ color: "#3a3a3a", fontWeight: 600 }}
              >
                Password
              </label>
              <div className="relative">
                <input
                  type={showPw ? "text" : "password"}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                  placeholder="••••••••"
                  className="editorial-input pr-10"
                />
                <button
                  type="button"
                  onClick={() => setShowPw(!showPw)}
                  className="absolute right-3 top-1/2 -translate-y-1/2"
                  style={{ color: "#787878" }}
                >
                  {showPw ? <EyeOff size={15} /> : <Eye size={15} />}
                </button>
              </div>
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full py-3.5 text-[11px] tracking-[0.22em] uppercase font-semibold flex items-center justify-center gap-2 transition-opacity disabled:opacity-60"
              style={{ background: "#0a0f1e", color: "#ffffff" }}
            >
              {loading && <Loader2 size={13} className="animate-spin" />}
              {loading ? "Signing in" : "Sign in"}
            </button>
          </form>

          <div className="gold-rule my-10" />

          <p className="text-center text-[13px]" style={{ color: "#787878" }}>
            No account?{" "}
            <Link
              href="/register"
              style={{ color: "#b8962e", borderBottom: "1px solid #b8962e" }}
              className="font-medium pb-0.5"
            >
              Create one
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
}
