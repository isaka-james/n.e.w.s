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
  { name: "Technology",   emoji: "💻" },
  { name: "AI",           emoji: "🤖" },
  { name: "Cybersecurity",emoji: "🔐" },
  { name: "Science",      emoji: "🔬" },
  { name: "Space",        emoji: "🚀" },
  { name: "Health",       emoji: "🏥" },
  { name: "Medicine",     emoji: "💊" },
  { name: "Mental Health",emoji: "🧠" },
  { name: "Business",     emoji: "📈" },
  { name: "Finance",      emoji: "💰" },
  { name: "Economy",      emoji: "📊" },
  { name: "Startup",      emoji: "💡" },
  { name: "Crypto",       emoji: "🪙" },
  { name: "Politics",     emoji: "🏛️" },
  { name: "Geopolitics",  emoji: "🌐" },
  { name: "Defense",      emoji: "⚔️" },
  { name: "Law",          emoji: "⚖️" },
  { name: "Climate",      emoji: "🌍" },
  { name: "Environment",  emoji: "🌿" },
  { name: "Energy",       emoji: "⚡" },
  { name: "Sports",       emoji: "⚽" },
  { name: "Entertainment",emoji: "🎬" },
  { name: "Music",        emoji: "🎵" },
  { name: "Gaming",       emoji: "🎮" },
  { name: "Culture",      emoji: "🎭" },
  { name: "Fashion",      emoji: "👗" },
  { name: "Education",    emoji: "📚" },
  { name: "Travel",       emoji: "✈️" },
  { name: "Food",         emoji: "🍽️" },
  { name: "Real Estate",  emoji: "🏠" },
  { name: "Automotive",   emoji: "🚗" },
  { name: "Philosophy",   emoji: "🦉" },
];

const PRESET_TAG_NAMES = new Set(PRESET_TAGS.map((p) => p.name));

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
  const [customTagInput, setCustomTagInput] = useState("");
  const [customTagEmoji, setCustomTagEmoji] = useState("🏷️");
  const [autoEnabled, setAutoEnabled] = useState(false);
  const [autoTime, setAutoTime] = useState("07:00");
  // Display current UTC time so users can calibrate
  const [utcNow, setUtcNow] = useState("");

  useEffect(() => {
    const fmt = () => {
      const d = new Date();
      setUtcNow(`${String(d.getUTCHours()).padStart(2, "0")}:${String(d.getUTCMinutes()).padStart(2, "0")} UTC`);
    };
    fmt();
    const id = setInterval(fmt, 30_000);
    return () => clearInterval(id);
  }, []);

  useEffect(() => {
    if (user) {
      setName(user.name);
      setCity(user.city);
      setCountry(user.country);
      setTags(user.tags);
      setBlockedWords(user.blocked_words);
      if (user.auto_generate_time) {
        setAutoEnabled(true);
        setAutoTime(user.auto_generate_time);
      } else {
        setAutoEnabled(false);
      }
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

  const addCustomTag = () => {
    const name = customTagInput.trim();
    if (!name) return;
    if (tags.find((t) => t.name.toLowerCase() === name.toLowerCase())) return;
    setTags([...tags, { name, emoji: customTagEmoji || "🏷️", priority: "medium" }]);
    setCustomTagInput("");
    setCustomTagEmoji("🏷️");
    markDirty();
  };

  const removeCustomTag = (tagName: string) => {
    setTags(tags.filter((t) => t.name !== tagName));
    markDirty();
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
      await api.users.update({
        name,
        city,
        country,
        tags,
        blocked_words: blockedWords,
        auto_generate_time: autoEnabled ? autoTime : null,
      });
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
        <div className="max-w-3xl mx-auto px-5 sm:px-8 md:px-12 py-8 md:py-10 flex items-end justify-between gap-4 flex-wrap">
          <div>
            <p className="text-[11px] tracking-[0.25em] uppercase mb-2" style={{ color: "#b8962e", fontWeight: 600 }}>
              Profile · Preferences
            </p>
            <h1 className="text-[28px] sm:text-[34px] md:text-[40px] leading-none" style={{ fontFamily: "'Rufina', Georgia, serif", color: "#0a0f1e" }}>
              Settings
            </h1>
          </div>
          <button
            onClick={handleSave}
            disabled={saving || !dirty}
            className="flex items-center gap-2 px-5 sm:px-6 py-3 text-[11px] tracking-[0.22em] uppercase font-semibold transition-opacity disabled:opacity-40"
            style={{ background: "#0a0f1e", color: "#ffffff" }}
          >
            {saving ? <Loader2 size={13} className="animate-spin" /> : <Save size={13} />}
            {saving ? "Saving" : "Save changes"}
          </button>
        </div>
      </div>

      <div className="max-w-3xl mx-auto px-5 sm:px-8 md:px-12 py-8 md:py-12 space-y-10 md:space-y-12">

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
          <div className="flex flex-wrap gap-2 mb-5">
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

          {/* Custom topic input */}
          <div className="mb-6">
            <p className="text-[10px] tracking-[0.22em] uppercase mb-3" style={{ color: "#3a3a3a", fontWeight: 600 }}>
              Add custom topic
            </p>
            <div className="flex gap-0">
              <input
                type="text"
                value={customTagEmoji}
                onChange={(e) => setCustomTagEmoji(e.target.value || "🏷️")}
                maxLength={2}
                className="editorial-input text-center"
                style={{ width: "52px", flexShrink: 0 }}
                placeholder="🏷️"
              />
              <input
                type="text"
                value={customTagInput}
                onChange={(e) => setCustomTagInput(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); addCustomTag(); } }}
                placeholder="Topic name…"
                className="editorial-input flex-1"
                style={{ marginLeft: "-1px" }}
              />
              <button
                type="button"
                onClick={addCustomTag}
                className="px-5"
                style={{ background: "#0a0f1e", color: "#ffffff", marginLeft: "-1px" }}
              >
                <Plus size={16} />
              </button>
            </div>
          </div>

          {tags.length > 0 && (
            <div style={{ background: "#ffffff", border: "1px solid #d8d0c4" }}>
              <div className="px-5 py-3" style={{ background: "#ede8df" }}>
                <p className="text-[10px] tracking-[0.22em] uppercase" style={{ color: "#3a3a3a", fontWeight: 600 }}>
                  Priority
                </p>
              </div>
              <div className="px-4 sm:px-5 py-4 space-y-3">
                {tags.map((tag) => (
                  <div key={tag.name} className="flex items-center justify-between gap-3 flex-wrap">
                    <span className="text-[14px]" style={{ fontFamily: "'Rufina', Georgia, serif", color: "#0a0f1e" }}>
                      {tag.emoji ?? "🏷️"} {tag.name}
                    </span>
                    <div className="flex items-center gap-3">
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
                      {!PRESET_TAG_NAMES.has(tag.name) && (
                        <button
                          type="button"
                          onClick={() => removeCustomTag(tag.name)}
                          title="Remove custom topic"
                        >
                          <X size={13} style={{ color: "#aaa" }} />
                        </button>
                      )}
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

        {/* Automation */}
        <Section number="V" title="Automation">
          <div
            className="p-5 sm:p-6"
            style={{ background: "#ffffff", border: "1px solid #d8d0c4" }}
          >
            {/* Enable toggle */}
            <label className="flex items-start gap-4 cursor-pointer">
              <div
                role="switch"
                aria-checked={autoEnabled}
                tabIndex={0}
                onClick={() => { setAutoEnabled(!autoEnabled); markDirty(); }}
                onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { setAutoEnabled(!autoEnabled); markDirty(); } }}
                className="mt-0.5 flex-shrink-0 cursor-pointer"
                style={{
                  width: 40, height: 22,
                  borderRadius: 11,
                  background: autoEnabled ? "#0a0f1e" : "#d8d0c4",
                  position: "relative",
                  transition: "background 0.2s",
                }}
              >
                <span
                  style={{
                    position: "absolute",
                    top: 3,
                    left: autoEnabled ? 21 : 3,
                    width: 16, height: 16,
                    borderRadius: "50%",
                    background: "#ffffff",
                    transition: "left 0.2s",
                  }}
                />
              </div>
              <div>
                <p className="text-[16px] mb-1" style={{ fontFamily: "'Rufina', Georgia, serif", color: "#0a0f1e" }}>
                  Auto-generate daily briefing
                </p>
                <p className="text-[12px] leading-relaxed" style={{ color: "#787878" }}>
                  N.E.W.S. will automatically fetch news and write your briefing every day at the
                  scheduled time. If the server restarts after the scheduled time, your briefing
                  will be prepared immediately on startup.
                </p>
              </div>
            </label>

            {/* Time picker — only shown when enabled */}
            {autoEnabled && (
              <div className="mt-5 pt-5" style={{ borderTop: "1px solid #ede8df" }}>
                <Field label="Daily generation time (UTC 24-hour)">
                  <div className="flex items-center gap-3 sm:gap-4 flex-wrap">
                    <input
                      type="time"
                      value={autoTime}
                      onChange={(e) => { setAutoTime(e.target.value); markDirty(); }}
                      className="editorial-input"
                      style={{ width: "auto" }}
                    />
                    <span className="text-[12px]" style={{ color: "#787878" }}>
                      Current UTC: <strong style={{ color: "#3a3a3a" }}>{utcNow}</strong>
                    </span>
                  </div>
                </Field>
                <p className="text-[11px] mt-3 leading-relaxed" style={{ color: "#aaa" }}>
                  Set this in UTC. Example: if you want a 7 AM briefing in UTC+3, enter 04:00.
                </p>
              </div>
            )}
          </div>
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
