"use client";

import { useState, useEffect, useRef } from "react";
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
  useGnews: boolean;
  useGuardian: boolean;
  useNytimes: boolean;
  minCity: number;
  minCountry: number;
  minContinent: number;
  minWorld: number;
}

const DEFAULTS: Config = {
  temperature: 0.7,
  maxStories: 15,
  useNewsdata: true,
  useNewsapi: true,
  useNewscatcher: true,
  useGnews: true,
  useGuardian: true,
  useNytimes: true,
  minCity: 10,
  minCountry: 10,
  minContinent: 10,
  minWorld: 30,
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
  // Task-id for the active notification so we can resolve it when done
  const taskIdRef = useRef<string | null>(null);

  useEffect(() => { setConfig(loadConfig()); }, []);

  // On mount: check backend for an in-flight job and restore UI state
  useEffect(() => {
    api.reports.status().then((job) => {
      if (!job || job.status !== "running") return;
      if (job.type !== "ai-only" && job.type !== "from-scratch") return;

      const op = job.type as RunningOp;
      setRunning(op);
      const title = op === "ai-only" ? "Re-run AI Only" : "Regenerate from Scratch";
      taskIdRef.current = start(
        `${title} In Progress`,
        "This operation was in progress when you left. Picking up where you left off…"
      );
    }).catch(() => { /* ignore */ });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Poll GET /reports/status every 5 s while running
  useEffect(() => {
    if (!running) return;

    const poll = async () => {
      try {
        const job = await api.reports.status();
        if (!job || job.status === "running") return;

        setRunning(null);

        if (!taskIdRef.current) return;

        if (job.status === "completed") {
          finish(
            taskIdRef.current,
            "success",
            running === "from-scratch"
              ? "Fresh briefing ready — news re-fetched and re-written."
              : "Briefing updated — AI re-ran on today’s story cache."
          );
        } else {
          finish(taskIdRef.current, "error", job.error_message ?? "Report generation failed.");
        }
        taskIdRef.current = null;
      } catch { /* keep polling */ }
    };

    const id = setInterval(poll, 5000);
    return () => clearInterval(id);
  }, [running, finish]);

  const update = (patch: Partial<Config>) => {
    const next = { ...config, ...patch };
    setConfig(next);
    saveConfig(next);
  };

  const noSources = !config.useNewsdata && !config.useNewsapi && !config.useNewscatcher
    && !config.useGnews && !config.useGuardian && !config.useNytimes;

  const handleRegenerate = async (fromScratch: boolean) => {
    if (noSources) return;
    const op: RunningOp = fromScratch ? "from-scratch" : "ai-only";
    setRunning(op);

    const title = fromScratch ? "Regenerate from Scratch" : "Re-run AI Only";
    const startMsg = fromScratch
      ? "Discarding cached stories, re-fetching from all enabled sources, then re-running AI…"
      : "Re-running DeepSeek on today's cached stories with updated settings…";

    taskIdRef.current = start(title, startMsg);
    try {
      // POST returns immediately with job_id; polling effect drives completion
      await api.reports.generate({
        force: true,
        fresh: fromScratch,
        temperature: config.temperature,
        maxStories: config.maxStories,
        useNewsdata: config.useNewsdata,
        useNewsapi: config.useNewsapi,
        useNewscatcher: config.useNewscatcher,
        useGnews: config.useGnews,
        useGuardian: config.useGuardian,
        useNytimes: config.useNytimes,
        minCity: config.minCity,
        minCountry: config.minCountry,
        minContinent: config.minContinent,
        minWorld: config.minWorld,
        jobType: op,
      });
    } catch (err: unknown) {
      setRunning(null);
      if (taskIdRef.current) {
        finish(taskIdRef.current, "error", err instanceof Error ? err.message : "Failed");
        taskIdRef.current = null;
      }
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
            Applies on the next fresh fetch. Sources now fetch up to 15–20 targeted queries each per generation,
            making full use of their daily API quotas.
          </p>
          <div style={{ border: "1px solid #d8d0c4" }}>
            {[
              { key: "useNewsdata"    as keyof Config, label: "NewsData.io",       desc: "200 req/day · country, city, continent, tag searches + trending" },
              { key: "useNewsapi"     as keyof Config, label: "NewsAPI.org",       desc: "100 req/day · top headlines by country + category" },
              { key: "useNewscatcher" as keyof Config, label: "NewsCatcher API",   desc: "500 req/day · latest headlines, city and topic searches" },
              { key: "useGnews"       as keyof Config, label: "GNews",             desc: "100 req/day · global top-headlines by category + country" },
              { key: "useGuardian"    as keyof Config, label: "The Guardian",      desc: "5,000 req/day · world, tech, science + keyword searches" },
              { key: "useNytimes"     as keyof Config, label: "New York Times",    desc: "Generous limit · top stories, most-popular, article search" },
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

        {/* Layer minimums */}
        <Section number="IV" title="Layer minimums">
          <p className="text-[13px] mb-5" style={{ color: "#787878" }}>
            Minimum stories required per layer before the briefing is written. The AI will lower its
            score threshold to fill a layer if fewer stories are available.
          </p>
          <div className="space-y-8 p-7" style={{ background: "#ffffff", border: "1px solid #d8d0c4" }}>
            <SliderField
              label="City (N) minimum"
              value={config.minCity}
              min={3} max={30} step={1}
              display={`${config.minCity}`}
              hint={["Lean", "Dense"]}
              onChange={(v) => update({ minCity: Math.round(v) })}
            />
            <SliderField
              label="Country (E) minimum"
              value={config.minCountry}
              min={3} max={30} step={1}
              display={`${config.minCountry}`}
              hint={["Lean", "Dense"]}
              onChange={(v) => update({ minCountry: Math.round(v) })}
            />
            <SliderField
              label="Continent (W) minimum"
              value={config.minContinent}
              min={3} max={30} step={1}
              display={`${config.minContinent}`}
              hint={["Lean", "Dense"]}
              onChange={(v) => update({ minContinent: Math.round(v) })}
            />
            <SliderField
              label="World (S) minimum"
              value={config.minWorld}
              min={5} max={60} step={5}
              display={`${config.minWorld}`}
              hint={["Focused", "Expansive"]}
              onChange={(v) => update({ minWorld: Math.round(v) })}
            />
          </div>
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
