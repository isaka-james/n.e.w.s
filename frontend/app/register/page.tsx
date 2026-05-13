"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { toast } from "sonner";
import { Loader2, X, Plus } from "lucide-react";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";

const COUNTRIES = [
  "Afghanistan","Albania","Algeria","Argentina","Armenia","Australia","Austria","Azerbaijan",
  "Bahrain","Bangladesh","Belarus","Belgium","Bolivia","Bosnia and Herzegovina","Botswana",
  "Brazil","Bulgaria","Cambodia","Cameroon","Canada","Chile","China","Colombia","Costa Rica",
  "Croatia","Cuba","Czech Republic","Denmark","Dominican Republic","Ecuador","Egypt","Estonia",
  "Ethiopia","Finland","France","Georgia","Germany","Ghana","Greece","Guatemala","Honduras",
  "Hungary","Iceland","India","Indonesia","Iran","Iraq","Ireland","Israel","Italy","Jamaica",
  "Japan","Jordan","Kazakhstan","Kenya","Kuwait","Latvia","Lebanon","Libya","Lithuania",
  "Luxembourg","Malaysia","Malta","Mexico","Moldova","Mongolia","Montenegro","Morocco","Myanmar",
  "Nepal","Netherlands","New Zealand","Nicaragua","Nigeria","North Korea","North Macedonia",
  "Norway","Oman","Pakistan","Panama","Paraguay","Peru","Philippines","Poland","Portugal",
  "Qatar","Romania","Russia","Saudi Arabia","Senegal","Serbia","Singapore","Slovakia","Slovenia",
  "Somalia","South Africa","South Korea","Spain","Sri Lanka","Sudan","Sweden","Switzerland",
  "Syria","Taiwan","Tanzania","Thailand","Tunisia","Turkey","Uganda","Ukraine",
  "United Arab Emirates","United Kingdom","United States","Uruguay","Venezuela","Vietnam",
  "Yemen","Zambia","Zimbabwe",
];

const PRESET_TAGS = [
  { name: "Technology", emoji: "💻" },
  { name: "Politics",   emoji: "🏛️" },
  { name: "Business",   emoji: "📈" },
  { name: "Science",    emoji: "🔬" },
  { name: "Health",     emoji: "🏥" },
  { name: "Climate",    emoji: "🌍" },
  { name: "Sports",     emoji: "⚽" },
  { name: "Entertainment", emoji: "🎬" },
  { name: "Finance",    emoji: "💰" },
  { name: "AI",         emoji: "🤖" },
  { name: "Security",   emoji: "🔒" },
  { name: "Culture",    emoji: "🎭" },
  { name: "Education",  emoji: "📚" },
  { name: "Travel",     emoji: "✈️" },
  { name: "Food",       emoji: "🍽️" },
  { name: "Energy",     emoji: "⚡" },
];

type Priority = "high" | "medium" | "low";

interface SelectedTag { name: string; emoji: string; priority: Priority; }

export default function RegisterPage() {
  const router = useRouter();
  const { login } = useAuth();

  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [city, setCity] = useState("");
  const [country, setCountry] = useState("");
  const [selectedTags, setSelectedTags] = useState<SelectedTag[]>([]);
  const [blockedInput, setBlockedInput] = useState("");
  const [blockedWords, setBlockedWords] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);

  const toggleTag = (tag: { name: string; emoji: string }) => {
    const exists = selectedTags.find((t) => t.name === tag.name);
    if (exists) {
      setSelectedTags(selectedTags.filter((t) => t.name !== tag.name));
    } else {
      setSelectedTags([...selectedTags, { ...tag, priority: "medium" }]);
    }
  };

  const setPriority = (name: string, priority: Priority) => {
    setSelectedTags(selectedTags.map((t) => (t.name === name ? { ...t, priority } : t)));
  };

  const addBlocked = () => {
    const word = blockedInput.trim().toLowerCase();
    if (word && !blockedWords.includes(word)) {
      setBlockedWords([...blockedWords, word]);
    }
    setBlockedInput("");
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!country) { toast.error("Please select your country"); return; }
    if (selectedTags.length === 0) { toast.error("Pick at least one topic"); return; }
    if (password.length < 8) { toast.error("Password must be at least 8 characters"); return; }
    if (!/[A-Z]/.test(password)) { toast.error("Password must include at least one uppercase letter"); return; }
    if (!/[0-9]/.test(password)) { toast.error("Password must include at least one number"); return; }
    setLoading(true);
    try {
      const res = await api.auth.register({
        name, email, password, city, country,
        tags: selectedTags.map(({ name, emoji, priority }) => ({ name, emoji, priority })),
        blocked_words: blockedWords,
      });
      login(res.access_token, res.user);
      router.push("/dashboard");
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : "Registration failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen" style={{ background: "#f5f1eb" }}>

      {/* Masthead */}
      <div style={{ background: "#0a0f1e" }}>
        <div className="max-w-3xl mx-auto px-5 sm:px-8 md:px-12 py-8 md:py-10">
          <Link href="/login" className="inline-block">
            <h1
              className="text-[28px] sm:text-[34px] leading-none"
              style={{ fontFamily: "'Rufina', Georgia, serif", color: "#ffffff", letterSpacing: "0.04em" }}
            >
              N.E.W.S.
            </h1>
            <p className="text-[10px] tracking-[0.25em] uppercase mt-2" style={{ color: "#b8962e", fontWeight: 600 }}>
              Your world, filtered
            </p>
          </Link>
        </div>
      </div>

      <div className="max-w-3xl mx-auto px-5 sm:px-8 md:px-12 py-8 md:py-12">
        <div className="text-center mb-10 md:mb-12">
          <p className="text-[10px] tracking-[0.3em] uppercase mb-3" style={{ color: "#b8962e", fontWeight: 600 }}>
            Subscription
          </p>
          <h2
            className="text-[26px] sm:text-[32px] md:text-[38px] leading-tight mb-3"
            style={{ fontFamily: "'Rufina', Georgia, serif", color: "#0a0f1e" }}
          >
            Set up your personal briefing.
          </h2>
          <p className="text-[14px]" style={{ color: "#787878" }}>
            Tell us where you read from and what matters — under a minute.
          </p>
          <div className="gold-rule mx-auto mt-8" style={{ width: "60px" }} />
        </div>

        <form onSubmit={handleSubmit} className="space-y-10">

          {/* Identity */}
          <section>
            <p className="text-[10px] tracking-[0.25em] uppercase mb-5" style={{ color: "#b8962e", fontWeight: 600 }}>
              I. Your details
            </p>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
              <Field label="Full name">
                <input type="text" value={name} onChange={(e) => setName(e.target.value)} required placeholder="Jane Doe" className="editorial-input" />
              </Field>
              <Field label="Email">
                <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required placeholder="jane@example.com" className="editorial-input" />
              </Field>
              <Field label="Password">
                <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required minLength={8} placeholder="Min. 8 chars, 1 uppercase, 1 number" className="editorial-input" />
              </Field>
              <Field label="City">
                <input type="text" value={city} onChange={(e) => setCity(e.target.value)} required placeholder="Nairobi" className="editorial-input" />
              </Field>
            </div>
            <div className="mt-5">
              <Field label="Country">
                <select value={country} onChange={(e) => setCountry(e.target.value)} required className="editorial-input cursor-pointer">
                  <option value="" disabled>Select your country…</option>
                  {COUNTRIES.map((c) => <option key={c} value={c}>{c}</option>)}
                </select>
              </Field>
            </div>
          </section>

          {/* Topics */}
          <section>
            <p className="text-[10px] tracking-[0.25em] uppercase mb-3" style={{ color: "#b8962e", fontWeight: 600 }}>
              II. Your topics
            </p>
            <p className="text-[13px] mb-5" style={{ color: "#787878" }}>
              Choose what matters — the more you pick, the broader your briefing.
            </p>

            <div className="flex flex-wrap gap-2">
              {PRESET_TAGS.map((tag) => {
                const selected = selectedTags.find((t) => t.name === tag.name);
                return (
                  <button
                    key={tag.name}
                    type="button"
                    onClick={() => toggleTag(tag)}
                    className="px-4 py-2 text-[12px] tracking-[0.05em] font-medium transition-colors"
                    style={{
                      background: selected ? "#0a0f1e" : "#ffffff",
                      border: selected ? "1px solid #0a0f1e" : "1px solid #d8d0c4",
                      color: selected ? "#ffffff" : "#3a3a3a",
                    }}
                  >
                    {tag.emoji} {tag.name}
                  </button>
                );
              })}
            </div>

            {selectedTags.length > 0 && (
              <div className="mt-6" style={{ background: "#ffffff", border: "1px solid #d8d0c4" }}>
                <div className="px-5 py-3" style={{ background: "#ede8df" }}>
                  <p className="text-[10px] tracking-[0.22em] uppercase" style={{ color: "#3a3a3a", fontWeight: 600 }}>
                    Set priority for each topic
                  </p>
                </div>
                <div className="px-5 py-3 space-y-3">
                  {selectedTags.map((tag) => (
                    <div key={tag.name} className="flex items-center justify-between">
                      <span className="text-[14px]" style={{ fontFamily: "'Rufina', Georgia, serif", color: "#0a0f1e" }}>
                        {tag.emoji} {tag.name}
                      </span>
                      <div className="flex gap-1">
                        {(["high", "medium", "low"] as Priority[]).map((p) => (
                          <button
                            key={p}
                            type="button"
                            onClick={() => setPriority(tag.name, p)}
                            className="px-3 py-1 text-[10px] tracking-[0.15em] uppercase font-semibold transition-colors"
                            style={{
                              background: tag.priority === p ? "#b8962e" : "transparent",
                              border: tag.priority === p ? "1px solid #b8962e" : "1px solid #d8d0c4",
                              color: tag.priority === p ? "#ffffff" : "#787878",
                            }}
                          >
                            {p}
                          </button>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </section>

          {/* Blocked words */}
          <section>
            <p className="text-[10px] tracking-[0.25em] uppercase mb-3" style={{ color: "#b8962e", fontWeight: 600 }}>
              III. Filter
            </p>
            <p className="text-[13px] mb-5" style={{ color: "#787878" }}>
              Stories containing these words will be dropped before the briefing — optional.
            </p>

            <div className="flex gap-0">
              <input
                type="text"
                value={blockedInput}
                onChange={(e) => setBlockedInput(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); addBlocked(); } }}
                placeholder="e.g. celebrity"
                className="editorial-input flex-1"
              />
              <button
                type="button"
                onClick={addBlocked}
                className="px-5 transition-opacity"
                style={{ background: "#0a0f1e", color: "#ffffff", marginLeft: "-1px" }}
              >
                <Plus size={16} />
              </button>
            </div>

            {blockedWords.length > 0 && (
              <div className="flex flex-wrap gap-2 mt-4">
                {blockedWords.map((word) => (
                  <span
                    key={word}
                    className="flex items-center gap-2 px-3 py-1.5 text-[12px]"
                    style={{ background: "#ffffff", border: "1px solid #d8d0c4", color: "#3a3a3a" }}
                  >
                    {word}
                    <button type="button" onClick={() => setBlockedWords(blockedWords.filter((w) => w !== word))}>
                      <X size={11} style={{ color: "#787878" }} />
                    </button>
                  </span>
                ))}
              </div>
            )}
          </section>

          <div className="gold-rule" />

          <button
            type="submit"
            disabled={loading}
            className="w-full py-4 text-[11px] tracking-[0.22em] uppercase font-semibold flex items-center justify-center gap-2 transition-opacity disabled:opacity-60"
            style={{ background: "#0a0f1e", color: "#ffffff" }}
          >
            {loading && <Loader2 size={13} className="animate-spin" />}
            {loading ? "Creating account" : "Create account & begin reading"}
          </button>

          <p className="text-center text-[13px]" style={{ color: "#787878" }}>
            Already have an account?{" "}
            <Link href="/login" style={{ color: "#b8962e", borderBottom: "1px solid #b8962e" }} className="pb-0.5">
              Sign in
            </Link>
          </p>
        </form>
      </div>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <label className="block text-[10px] tracking-[0.22em] uppercase mb-2" style={{ color: "#3a3a3a", fontWeight: 600 }}>
        {label}
      </label>
      {children}
    </div>
  );
}
