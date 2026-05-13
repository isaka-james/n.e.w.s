"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { Loader2, CheckCircle2 } from "lucide-react";
import { api, Report, Section } from "@/lib/api";
import { useNotifications } from "@/lib/notifications-context";
import { StoryCard } from "@/components/story-card";

const LAYERS = [
  { key: "N", label: "Narrow",   desc: "Your city" },
  { key: "E", label: "Expanded", desc: "Your country" },
  { key: "W", label: "Wide",     desc: "Your continent" },
  { key: "S", label: "Sweeping", desc: "The world" },
] as const;

type LayerKey = "N" | "E" | "W" | "S";

// Human-readable label per backend stage key. Anything unknown falls back to
// a generic "Working" so a new stage added on the server still renders cleanly.
const STAGE_LABELS: Record<string, string> = {
  queued: "Queued",
  reading_cache: "Reading cache",
  fetching_news: "Fetching the wires",
  triaging: "Classifying stories",
  gap_filling: "Filling local gaps",
  writing: "Writing the briefing",
  finalizing: "Finalizing",
  completed: "Complete",
};

function stageLabel(stage: string | undefined): string {
  if (!stage) return "Working";
  return STAGE_LABELS[stage] ?? "Working";
}

// The backend emits naive UTC ISO strings (no Z, no offset) via
// `datetime.utcnow().isoformat()`. Plain `new Date(str)` treats those as local
// time, which puts duration off by the user's UTC offset on refresh. Force UTC
// by appending Z when the string carries no timezone marker.
function parseBackendUtc(iso: string): Date {
  return /[zZ]|[+-]\d{2}:?\d{2}$/.test(iso) ? new Date(iso) : new Date(iso + "Z");
}

export default function DashboardPage() {
  const { start, finish, update } = useNotifications();
  const [report, setReport] = useState<Report | null>(null);
  const [activeLayer, setActiveLayer] = useState<LayerKey>("N");
  const [fetching, setFetching] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [progress, setProgress] = useState(0);
  const [stage, setStage] = useState<string>("queued");
  // Task-id for the running notification so we can resolve it when done
  const taskIdRef = useRef<string | null>(null);

  // On mount: load today's report AND check backend for an in-flight job
  const bootstrap = useCallback(async () => {
    try {
      const [report, job] = await Promise.all([
        api.reports.today(),
        api.reports.status(),
      ]);

      if (report) {
        setReport(report);
        return; // done — no need to show generating state
      }

      // Restore generating state for any in-flight job (manual or auto-scheduled)
      if (job && job.status === "running" && (job.type === "generate" || job.type === "auto")) {
        setGenerating(true);
        setProgress(job.progress ?? 0);
        setStage(job.stage ?? "queued");
        const label = job.type === "auto"
          ? "Your scheduled briefing is being prepared"
          : "Report Generation In Progress";
        const detail = job.type === "auto"
          ? "Your daily auto-generation is running. The briefing will be ready shortly."
          : "A report was being generated when you left. Picking up where you left off.";
        // Use the backend's created_at as the task's start time so the Activity
        // panel's "Duration" stays correct across page refreshes.
        const startedAt = job.created_at ? parseBackendUtc(job.created_at) : new Date();
        const taskId = start(label, detail, startedAt);
        taskIdRef.current = taskId;
        update(taskId, { progress: job.progress ?? 0, stage: job.stage ?? "queued" });
      }
    } catch { /* ignore */ }
    finally { setFetching(false); }
  }, [start, update]);

  useEffect(() => { bootstrap(); }, [bootstrap]);

  // Poll GET /reports/today every 5 s while generating
  useEffect(() => {
    if (!generating) return;

    const poll = async () => {
      try {
        // Fetch report and live job state on every tick — job state drives the
        // progress bar even while the report itself is not yet written.
        const [r, job] = await Promise.all([
          api.reports.today(),
          api.reports.status(),
        ]);
        if (r) {
          setReport(r);
          setGenerating(false);
          setProgress(100);
          setStage("completed");
          if (taskIdRef.current) {
            finish(taskIdRef.current, "success", "Briefing ready, stories filtered and written across all four layers.");
            taskIdRef.current = null;
          }
          return;
        }
        if (job && job.status === "running") {
          setProgress(job.progress ?? 0);
          setStage(job.stage ?? "queued");
          // Mirror into the Activity panel so users see live progress there too.
          if (taskIdRef.current) {
            update(taskIdRef.current, {
              progress: job.progress ?? 0,
              stage: job.stage ?? "queued",
            });
          }
        }
        if (job && job.status === "failed") {
          setGenerating(false);
          if (taskIdRef.current) {
            finish(taskIdRef.current, "error", job.error_message ?? "Report generation failed.");
            taskIdRef.current = null;
          }
        }
      } catch { /* keep polling */ }
    };

    // Poll every 2s while generating — short enough for a smooth bar without
    // hammering the API. Each call is cheap (single DB row + ETag-friendly).
    const id = setInterval(poll, 2000);
    return () => clearInterval(id);
  }, [generating, finish]);

  const handleGenerate = async () => {
    setGenerating(true);
    setProgress(0);
    setStage("queued");
    taskIdRef.current = start("Generate Report", "Fetching news from all sources and running the briefing engine.");
    try {
      const res = await api.reports.generate({ jobType: "generate" });
      // If report came back immediately (cached), resolve right away
      if (res.report) {
        setReport(res.report);
        setGenerating(false);
        finish(taskIdRef.current!, "success", "Briefing ready — stories filtered and written across all four layers.");
        taskIdRef.current = null;
      }
      // Otherwise the polling effect above will drive completion
    } catch (err: unknown) {
      setGenerating(false);
      finish(taskIdRef.current!, "error", err instanceof Error ? err.message : "Generation failed");
      taskIdRef.current = null;
    }
  };

  const rawSection: Section | undefined = report?.sections[activeLayer];
  // Defend against partial backend payloads — stories should always be an
  // array, even when the AI returned null or omitted it entirely.
  const section: Section | undefined = rawSection
    ? { ...rawSection, stories: rawSection.stories ?? [] }
    : undefined;
  const today = new Date();

  return (
    <div className="min-h-screen" style={{ background: "#f5f1eb" }}>

      {/* ───── Hero / masthead ───── */}
      <div style={{ borderBottom: "1px solid #d8d0c4", background: "#ffffff" }}>
        <div className="max-w-6xl mx-auto px-5 sm:px-8 md:px-12 py-8 md:py-12">

          <div className="flex items-end justify-between gap-6 flex-wrap">
            <div className="flex-1 min-w-0">
              <p
                className="text-[11px] tracking-[0.25em] uppercase mb-3"
                style={{ color: "#b8962e", fontWeight: 600 }}
              >
                The Daily Briefing · {today.toLocaleDateString(undefined, {
                  weekday: "long", year: "numeric", month: "long", day: "numeric"
                })}
              </p>

              <h1
                className="text-[28px] sm:text-[36px] md:text-[44px] leading-[1.05]"
                style={{
                  fontFamily: "'Rufina', Georgia, serif",
                  color: "#0a0f1e",
                  fontWeight: 400,
                  letterSpacing: "-0.015em",
                  maxWidth: "650px",
                }}
              >
                {report ? report.report_title : "A briefing awaits."}
              </h1>
            </div>

            <div>
              {report ? (
                <div
                  className="inline-flex items-center gap-2 text-[10px] tracking-[0.2em] uppercase px-4 py-2.5"
                  style={{ background: "#ede8df", color: "#3a3a3a", fontWeight: 600 }}
                >
                  <CheckCircle2 size={12} style={{ color: "#b8962e" }} strokeWidth={2} />
                  Generated today
                </div>
              ) : (
                <button
                  onClick={handleGenerate}
                  disabled={generating || fetching}
                  className="inline-flex items-center gap-2.5 px-5 sm:px-7 py-3.5 text-[11px] tracking-[0.22em] uppercase font-semibold transition-opacity disabled:opacity-50"
                  style={{ background: "#0a0f1e", color: "#ffffff" }}
                >
                  {generating
                    ? <><Loader2 size={13} className="animate-spin" /> Generating</>
                    : "Generate Today's Report"}
                </button>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* ───── Body ───── */}
      <div className="max-w-6xl mx-auto px-5 sm:px-8 md:px-12 py-8 md:py-12">

        {/* Loading */}
        {fetching && (
          <div className="flex items-center justify-center gap-3 py-20 text-[12px] tracking-[0.2em] uppercase" style={{ color: "#787878" }}>
            <Loader2 size={14} className="animate-spin" />
            Loading today&apos;s briefing
          </div>
        )}

        {/* Generating overlay */}
        {generating && (
          <div className="py-16 md:py-20 px-6 md:px-12" style={{ background: "#ffffff", border: "1px solid #d8d0c4" }}>
            <div className="max-w-md mx-auto text-center">
              <Loader2 size={28} className="animate-spin mx-auto mb-6" style={{ color: "#b8962e" }} strokeWidth={1.5} />
              <h3 className="text-[24px] mb-2" style={{ fontFamily: "'Rufina', Georgia, serif", color: "#0a0f1e" }}>
                {stageLabel(stage)}
              </h3>
              <p className="text-[13px] leading-relaxed mb-8" style={{ color: "#787878" }}>
                N.E.W.S. is preparing today&apos;s briefing. Usually about 30 to 90 seconds.
              </p>

              {/* Progress bar */}
              <div
                className="w-full h-[6px] mb-3"
                style={{ background: "#ede8df", overflow: "hidden" }}
                role="progressbar"
                aria-valuenow={progress}
                aria-valuemin={0}
                aria-valuemax={100}
              >
                <div
                  className="h-full transition-all duration-500 ease-out"
                  style={{ width: `${Math.max(2, progress)}%`, background: "#b8962e" }}
                />
              </div>

              {/* Stage key + percent */}
              <div className="flex items-center justify-between text-[10px] tracking-[0.22em] uppercase" style={{ color: "#787878", fontWeight: 600 }}>
                <span>{stage.replace(/_/g, " ")}</span>
                <span style={{ color: "#b8962e" }}>{progress}%</span>
              </div>
            </div>
          </div>
        )}

        {/* Empty state */}
        {!fetching && !generating && !report && (
          <div className="text-center py-16 md:py-24 px-4" style={{ background: "#ffffff", border: "1px solid #d8d0c4" }}>
            <h2
              className="text-[64px] sm:text-[90px] md:text-[120px] leading-none mb-6 tracking-[0.06em]"
              style={{ fontFamily: "'Rufina', Georgia, serif", color: "#ede8df", fontWeight: 400 }}
            >
              N·E·W·S
            </h2>
            <p className="text-[18px] mb-3" style={{ fontFamily: "'Rufina', Georgia, serif", color: "#0a0f1e" }}>
              No briefing yet for today.
            </p>
            <p className="text-[13px] mb-8 max-w-sm mx-auto" style={{ color: "#787878" }}>
              Press <em>Generate Today&apos;s Report</em> to pull stories across all four layers.
            </p>
          </div>
        )}

        {/* Report */}
        {!fetching && !generating && report && (
          <article>

            {/* Opening line — editorial pullquote */}
            <div className="mb-10 md:mb-14 max-w-3xl mx-auto text-center">
              <div className="gold-rule mx-auto mb-6" style={{ width: "60px" }} />
              <p
                className="text-[17px] sm:text-[20px] md:text-[22px] leading-[1.45] italic"
                style={{ fontFamily: "'Rufina', Georgia, serif", color: "#3a3a3a" }}
              >
                &ldquo;{report.opening_line}&rdquo;
              </p>
              <div className="gold-rule mx-auto mt-6" style={{ width: "60px" }} />
            </div>

            {/* Layer tabs — editorial section nav. Grid keeps all four tabs
                visible on every viewport instead of wrapping awkwardly. */}
            <div
              className="grid grid-cols-4 gap-2 sm:gap-6 md:gap-10 mb-10 md:mb-12"
              style={{ borderBottom: "1px solid #d8d0c4" }}
            >
              {LAYERS.map(({ key, label, desc }) => {
                const active = activeLayer === key;
                const count = report.sections[key as LayerKey]?.stories?.length ?? 0;
                return (
                  <button
                    key={key}
                    onClick={() => setActiveLayer(key as LayerKey)}
                    className="pb-3 md:pb-4 px-1 transition-colors text-center group"
                    style={{
                      borderBottom: active ? "2px solid #b8962e" : "2px solid transparent",
                      marginBottom: "-1px",
                    }}
                  >
                    <p
                      className="text-[9px] sm:text-[10px] tracking-[0.18em] sm:tracking-[0.25em] uppercase mb-1.5"
                      style={{ color: active ? "#b8962e" : "#787878", fontWeight: 600 }}
                    >
                      {key} · {label}
                    </p>
                    <p
                      className="text-[22px] sm:text-[28px] leading-none mb-1"
                      style={{
                        fontFamily: "'Rufina', Georgia, serif",
                        color: active ? "#0a0f1e" : "#3a3a3a",
                        fontWeight: 400,
                      }}
                    >
                      {count}
                    </p>
                    <p className="text-[9px] sm:text-[10px]" style={{ color: "#a0a0a0" }}>
                      {desc}
                    </p>
                  </button>
                );
              })}
            </div>

            {/* Section content */}
            {section && (
              <section>
                {/* Section label */}
                <div className="text-center mb-10">
                  <p
                    className="text-[11px] tracking-[0.3em] uppercase mb-3"
                    style={{ color: "#b8962e", fontWeight: 600 }}
                  >
                    {section.label}
                  </p>
                  <p
                    className="text-[18px] italic leading-relaxed max-w-2xl mx-auto"
                    style={{ fontFamily: "'Rufina', Georgia, serif", color: "#3a3a3a" }}
                  >
                    {section.mood_line}
                  </p>
                </div>

                {section.stories.length === 0 ? (
                  <div className="text-center py-16" style={{ background: "#ffffff", border: "1px solid #d8d0c4" }}>
                    <p className="text-[14px] italic" style={{ fontFamily: "'Rufina', Georgia, serif", color: "#787878" }}>
                      Nothing notable here today.
                    </p>
                  </div>
                ) : (
                  <>
                    {/* Featured (first story, full width) */}
                    {section.stories[0] && (
                      <div className="mb-8" style={{ border: "1px solid #d8d0c4" }}>
                        <StoryCard story={section.stories[0]} featured />
                      </div>
                    )}

                    {/* Remaining in 2-col grid */}
                    {section.stories.length > 1 && (
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
                        {section.stories.slice(1).map((story) => (
                          <div key={story.article_id} style={{ border: "1px solid #d8d0c4" }}>
                            <StoryCard story={story} />
                          </div>
                        ))}
                      </div>
                    )}
                  </>
                )}
              </section>
            )}

            {/* Closing line */}
            <div className="mt-20 max-w-3xl mx-auto text-center">
              <div className="gold-rule mx-auto mb-6" style={{ width: "60px" }} />
              <p
                className="text-[16px] leading-[1.6] italic"
                style={{ fontFamily: "'Rufina', Georgia, serif", color: "#787878" }}
              >
                {report.closing_line}
              </p>
              <p
                className="text-[10px] tracking-[0.3em] uppercase mt-6"
                style={{ color: "#b8962e", fontWeight: 600 }}
              >
                End of briefing
              </p>
            </div>
          </article>
        )}
      </div>
    </div>
  );
}
