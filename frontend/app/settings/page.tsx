"use client";

import { useState, useEffect } from "react";
import { toast } from "sonner";
import { Loader2, Plus, X, Save } from "lucide-react";
import { api, Tag } from "@/lib/api";
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

export default function SettingsPage() {
  const { user, refreshUser } = useAuth();

  const [name, setName] = useState("");
  const [city, setCity] = useState("");
  const [country, setCountry] = useState("");
  const [tags, setTags] = useState<Tag[]>([]);
  const [blockedWords, setBlockedWords] = useState<string[]>([]);
  const [blockedInput, setBlockedInput] = useState("");
  const [saving, setSaving] = useState(false);
  const [dirty, setDirty] = useState(false);

  useEffect(() => {
    if (user) {
      setName(user.name);
      setCity(user.city);
      setCountry(user.country);
      setTags(user.tags);
      setBlockedWords(user.blocked_words);
    }
  }, [user]);

  const markDirty = () => setDirty(true);

  const toggleTag = (preset: { name: string; emoji: string }) => {
    markDirty();
    const exists = tags.find((t) => t.name === preset.name);
    if (exists) setTags(tags.filter((t) => t.name !== preset.name));
    else setTags([...tags, { name: preset.name, emoji: preset.emoji, priority: "medium" }]);
  };

  const setPriority = (tagName: string, priority: Priority) => {
    markDirty();
    setTags(tags.map((t) => (t.name === tagName ? { ...t, priority } : t)));
  };

  const addBlocked = () => {
    const word = blockedInput.trim().toLowerCase();
    if (word && !blockedWords.includes(word)) {
      setBlockedWords([...blockedWords, word]);
      markDirty();
    }
    setBlockedInput("");
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      await api.users.update({ name, city, country, tags, blocked_words: blockedWords });
      await refreshUser();
      setDirty(false);
      toast.success("Settings saved.");
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : "Save failed");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="min-h-screen" style={{ background: "#f5f1eb" }}>

      {/* Masthead */}
      <div style={{ borderBottom: "1px solid #d8d0c4", background: "#ffffff" }}>
        <div className="max-w-3xl mx-auto px-12 py-10 flex items-end justify-between gap-6 flex-wrap">
          <div>
            <p className="text-[11px] tracking-[0.25em] uppercase mb-2" style={{ color: "#b8962e", fontWeight: 600 }}>
              Profile · Preferences
            </p>
            <h1 className="text-[40px] leading-none" style={{ fontFamily: "'Rufina', Georgia, serif", color: "#0a0f1e" }}>
              Settings
            </h1>
          </div>
          <button
            onClick={handleSave}
            disabled={saving || !dirty}
            className="flex items-center gap-2 px-6 py-3 text-[11px] tracking-[0.22em] uppercase font-semibold transition-opacity disabled:opacity-40"
            style={{ background: "#0a0f1e", color: "#ffffff" }}
          >
            {saving ? <Loader2 size={13} className="animate-spin" /> : <Save size={13} />}
            {saving ? "Saving" : "Save changes"}
          </button>
        </div>
      </div>

      <div className="max-w-3xl mx-auto px-12 py-12 space-y-12">

        {/* Account */}
        <Section number="I" title="Account">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
            <Field label="Name">
              <input type="text" value={name} onChange={(e) => { setName(e.target.value); markDirty(); }} className="editorial-input" />
            </Field>
            <Field label="Email">
              <input type="email" value={user?.email ?? ""} disabled className="editorial-input" />
            </Field>
          </div>
        </Section>

        {/* Location */}
        <Section number="II" title="Location">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
            <Field label="City">
              <input type="text" value={city} onChange={(e) => { setCity(e.target.value); markDirty(); }} className="editorial-input" />
            </Field>
            <Field label="Country">
              <select
                value={country}
                onChange={(e) => { setCountry(e.target.value); markDirty(); }}
                className="editorial-input cursor-pointer"
              >
                {COUNTRIES.map((c) => <option key={c} value={c}>{c}</option>)}
              </select>
            </Field>
          </div>
          {user && (
            <p className="text-[11px] mt-4" style={{ color: "#787878" }}>
              Continent auto-derived: <span style={{ color: "#3a3a3a", fontWeight: 500 }}>{user.continent}</span>
            </p>
          )}
        </Section>

        {/* Topics */}
        <Section number="III" title="Topics">
          <div className="flex flex-wrap gap-2 mb-6">
            {PRESET_TAGS.map((preset) => {
              const selected = tags.find((t) => t.name === preset.name);
              return (
                <button
                  key={preset.name}
                  type="button"
                  onClick={() => toggleTag(preset)}
                  className="px-4 py-2 text-[12px] tracking-[0.05em] font-medium transition-colors"
                  style={{
                    background: selected ? "#0a0f1e" : "#ffffff",
                    border: selected ? "1px solid #0a0f1e" : "1px solid #d8d0c4",
                    color: selected ? "#ffffff" : "#3a3a3a",
                  }}
                >
                  {preset.emoji} {preset.name}
                </button>
              );
            })}
          </div>

          {tags.length > 0 && (
            <div style={{ background: "#ffffff", border: "1px solid #d8d0c4" }}>
              <div className="px-5 py-3" style={{ background: "#ede8df" }}>
                <p className="text-[10px] tracking-[0.22em] uppercase" style={{ color: "#3a3a3a", fontWeight: 600 }}>
                  Priority
                </p>
              </div>
              <div className="px-5 py-4 space-y-3">
                {tags.map((tag) => (
                  <div key={tag.name} className="flex items-center justify-between">
                    <span className="text-[14px]" style={{ fontFamily: "'Rufina', Georgia, serif", color: "#0a0f1e" }}>
                      {tag.emoji ?? "🏷️"} {tag.name}
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
        </Section>

        {/* Blocked words */}
        <Section number="IV" title="Blocked words">
          <p className="text-[13px] mb-5" style={{ color: "#787878" }}>
            Stories containing these words (case-insensitive) are removed before the briefing.
          </p>

          <div className="flex gap-0">
            <input
              type="text"
              value={blockedInput}
              onChange={(e) => setBlockedInput(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); addBlocked(); } }}
              placeholder="Add a word…"
              className="editorial-input flex-1"
            />
            <button
              type="button"
              onClick={addBlocked}
              className="px-5"
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
        </Section>
      </div>
    </div>
  );
}

function Section({ number, title, children }: { number: string; title: string; children: React.ReactNode }) {
  return (
    <section>
      <div className="flex items-baseline gap-4 mb-5">
        <span className="text-[11px] tracking-[0.3em] uppercase" style={{ color: "#b8962e", fontWeight: 600 }}>
          {number}
        </span>
        <h2 className="text-[24px] leading-none" style={{ fontFamily: "'Rufina', Georgia, serif", color: "#0a0f1e" }}>
          {title}
        </h2>
        <div className="flex-1 h-px" style={{ background: "#d8d0c4" }} />
      </div>
      {children}
    </section>
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
