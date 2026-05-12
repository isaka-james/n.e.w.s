"use client";

import { useState, useEffect } from "react";
import { Loader2, RefreshCw, Brain } from "lucide-react";
import { api } from "@/lib/api";
import { useNotifications } from "@/lib/notifications-context";

const STORAGE_KEY = "news_advanced_config";

interface Config {
  temperature: number;
  maxStories: number;
  useNewsdata: boolean;
  useNewsapi: boolean;
  useNewscatcher: boolean;
}

const DEFAULTS: Config = {
  temperature: 0.7,
  maxStories: 15,
  useNewsdata: true,
  useNewsapi: true,
  useNewscatcher: true,
};

function loadConfig(): Config {
  if (typeof window === "undefined") return DEFAULTS;
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? { ...DEFAULTS, ...JSON.parse(raw) } : DEFAULTS;
  } catch { return DEFAULTS; }
}

function saveConfig(cfg: Config) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(cfg));
}

type RunningOp = "ai-only" | "from-scratch" | null;

export default function AdvancedPage() {
  const { start, finish } = useNotifications();
  const [config, setConfig] = useState<Config>(DEFAULTS);
  const [running, setRunning] = useState<RunningOp>(null);

  useEffect(() => { setConfig(loadConfig()); }, []);

  const update = (patch: Partial<Config>) => {
    const next = { ...config, ...patch };
    setConfig(next);
    saveConfig(next);
  };

  const noSources = !config.useNewsdata && !config.useNewsapi && !config.useNewscatcher;

  const handleRegenerate = async (fromScratch: boolean) => {
    if (noSources) return;
    const op: RunningOp = fromScratch ? "from-scratch" : "ai-only";
    setRunning(op);

    const title = fromScratch ? "Regenerate from Scratch" : "Re-run AI Only";
    const startMsg = fromScratch
      ? "Discarding cached stories, re-fetching from all enabled sources, then re-running AI…"
      : "Re-running DeepSeek on today's cached stories with updated settings…";

    const taskId = start(title, startMsg);
    try {
      await api.reports.generate({
        force: true,
        fresh: fromScratch,
        temperature: config.temperature,
        maxStories: config.maxStories,
        useNewsdata: config.useNewsdata,
        useNewsapi: config.useNewsapi,
        useNewscatcher: config.useNewscatcher,
      });
      finish(taskId, "success", fromScratch
        ? "Fresh briefing ready — news re-fetched and re-written."
        : "Briefing updated — AI re-ran on today's story cache.");
    } catch (err: unknown) {
      finish(taskId, "error", err instanceof Error ? err.message : "Failed");
    } finally {
      setRunning(null);
    }
  };

  return (
    <div className="min-h-screen" style={{ background: "#f5f1eb" }}>

      {/* Masthead */}
      <div style={{ borderBottom: "1px solid #d8d0c4", background: "#ffffff" }}>
        <div className="max-w-3xl mx-auto px-12 py-10">
          <p className="text-[11px] tracking-[0.25em] uppercase mb-2" style={{ color: "#b8962e", fontWeight: 600 }}>
            Editorial Controls
          </p>
          <h1 className="text-[40px] leading-none mb-3" style={{ fontFamily: "'Rufina', Georgia, serif", color: "#0a0f1e" }}>
            Advanced
          </h1>
          <p className="text-[14px] max-w-xl" style={{ color: "#787878" }}>
            Override the daily limit, re-tune the briefing engine, and choose which wires you read.
            All tasks appear in <em>Activity</em>.
          </p>
        </div>
      </div>

      <div className="max-w-3xl mx-auto px-12 py-12 space-y-12">

        {/* Regenerate */}
        <Section number="I" title="Regenerate report">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-0" style={{ border: "1px solid #d8d0c4" }}>
            <button
              onClick={() => handleRegenerate(false)}
              disabled={running !== null || noSources}
              className="text-left p-7 transition-colors disabled:opacity-50"
              style={{ background: "#ffffff", borderRight: "1px solid #d8d0c4" }}
            >
              <div className="flex items-center gap-2 mb-3">
                {running === "ai-only"
                  ? <Loader2 size={14} className="animate-spin" style={{ color: "#b8962e" }} />
                  : <Brain size={14} strokeWidth={1.5} style={{ color: "#b8962e" }} />}
                <span className="text-[10px] tracking-[0.22em] uppercase" style={{ color: "#b8962e", fontWeight: 600 }}>
                  AI Only
                </span>
              </div>
              <h3 className="text-[22px] leading-tight mb-2" style={{ fontFamily: "'Rufina', Georgia, serif", color: "#0a0f1e" }}>
                Re-run the briefing engine
              </h3>
              <p className="text-[13px] leading-relaxed" style={{ color: "#787878" }}>
                Keeps today&apos;s cached stories. Re-runs DeepSeek with current settings. No API credits used.
              </p>
            </button>

            <button
              onClick={() => handleRegenerate(true)}
              disabled={running !== null || noSources}
              className="text-left p-7 transition-colors disabled:opacity-50"
              style={{ background: "#ffffff" }}
            >
              <div className="flex items-center gap-2 mb-3">
                {running === "from-scratch"
                  ? <Loader2 size={14} className="animate-spin" style={{ color: "#b8962e" }} />
                  : <RefreshCw size={14} strokeWidth={1.5} style={{ color: "#b8962e" }} />}
                <span className="text-[10px] tracking-[0.22em] uppercase" style={{ color: "#b8962e", fontWeight: 600 }}>
                  From scratch
                </span>
              </div>
              <h3 className="text-[22px] leading-tight mb-2" style={{ fontFamily: "'Rufina', Georgia, serif", color: "#0a0f1e" }}>
                Refetch & rewrite everything
              </h3>
              <p className="text-[13px] leading-relaxed" style={{ color: "#787878" }}>
                Discards cache, re-fetches from enabled sources, re-runs AI. Uses ~5–10 credits per source.
              </p>
            </button>
          </div>
        </Section>

        {/* AI settings */}
        <Section number="II" title="Briefing engine">
          <div className="space-y-8 p-7" style={{ background: "#ffffff", border: "1px solid #d8d0c4" }}>
            <SliderField
              label="Temperature"
              value={config.temperature}
              min={0.1} max={1.5} step={0.1}
              display={config.temperature.toFixed(1)}
              hint={["Precise", "Creative"]}
              onChange={(v) => update({ temperature: v })}
            />
            <SliderField
              label="Max stories in briefing"
              value={config.maxStories}
              min={3} max={25} step={1}
              display={`${config.maxStories}`}
              hint={["Tight", "Exhaustive"]}
              onChange={(v) => update({ maxStories: Math.round(v) })}
            />
          </div>
        </Section>

        {/* News sources */}
        <Section number="III" title="News sources">
          <p className="text-[13px] mb-5" style={{ color: "#787878" }}>
            Applies on the next fresh fetch.
          </p>
          <div style={{ border: "1px solid #d8d0c4" }}>
            {[
              { key: "useNewsdata"    as keyof Config, label: "NewsData.io",     desc: "200 req/day · country, city, continent, tag searches" },
              { key: "useNewsapi"     as keyof Config, label: "NewsAPI.org",     desc: "100 req/day · top headlines by country + category" },
              { key: "useNewscatcher" as keyof Config, label: "NewsCatcher API", desc: "Free trial · latest headlines + city and topic searches" },
            ].map(({ key, label, desc }, i, arr) => (
              <label
                key={key}
                className="flex items-start gap-4 cursor-pointer p-5"
                style={{
                  background: "#ffffff",
                  borderBottom: i < arr.length - 1 ? "1px solid #d8d0c4" : undefined,
                }}
              >
                <input
                  type="checkbox"
                  checked={config[key] as boolean}
                  onChange={(e) => update({ [key]: e.target.checked })}
                  className="mt-1 cursor-pointer"
                  style={{ accentColor: "#b8962e" }}
                />
                <div className="flex-1">
                  <p className="text-[16px] mb-1" style={{ fontFamily: "'Rufina', Georgia, serif", color: "#0a0f1e" }}>
                    {label}
                  </p>
                  <p className="text-[12px]" style={{ color: "#787878" }}>{desc}</p>
                </div>
              </label>
            ))}
          </div>

          {noSources && (
            <p className="text-[12px] mt-3 italic" style={{ color: "#b91c1c" }}>
              At least one source must be enabled to generate a report.
            </p>
          )}
        </Section>

        {/* Note */}
        <div className="text-center pt-4" style={{ borderTop: "1px solid #d8d0c4" }}>
          <p className="text-[11px] tracking-[0.18em] uppercase mt-6" style={{ color: "#b8962e", fontWeight: 600 }}>
            A note from the editor
          </p>
          <p
            className="text-[14px] italic max-w-md mx-auto mt-3 leading-relaxed"
            style={{ fontFamily: "'Rufina', Georgia, serif", color: "#787878" }}
          >
            Settings are saved in your browser. Generation tasks run quietly in the background —
            check Activity in the sidebar for progress.
          </p>
        </div>
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

function SliderField({
  label, value, min, max, step, display, hint, onChange,
}: {
  label: string; value: number; min: number; max: number; step: number;
  display: string; hint: [string, string]; onChange: (v: number) => void;
}) {
  return (
    <div>
      <div className="flex items-baseline justify-between mb-3">
        <label className="text-[10px] tracking-[0.22em] uppercase" style={{ color: "#3a3a3a", fontWeight: 600 }}>
          {label}
        </label>
        <span className="text-[24px]" style={{ fontFamily: "'Rufina', Georgia, serif", color: "#b8962e" }}>
          {display}
        </span>
      </div>
      <input
        type="range" min={min} max={max} step={step}
        value={value}
        onChange={(e) => onChange(parseFloat(e.target.value))}
        className="w-full h-1 cursor-pointer"
        style={{ accentColor: "#b8962e" }}
      />
      <div className="flex justify-between mt-1.5">
        <span className="text-[10px] tracking-[0.15em] uppercase" style={{ color: "#a0a0a0" }}>{hint[0]}</span>
        <span className="text-[10px] tracking-[0.15em] uppercase" style={{ color: "#a0a0a0" }}>{hint[1]}</span>
      </div>
    </div>
  );
}
