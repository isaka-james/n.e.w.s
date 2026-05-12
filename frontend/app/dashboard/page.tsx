"use client";

import { useState, useEffect, useCallback } from "react";
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

export default function DashboardPage() {
  const { start, finish } = useNotifications();
  const [report, setReport] = useState<Report | null>(null);
  const [activeLayer, setActiveLayer] = useState<LayerKey>("N");
  const [fetching, setFetching] = useState(true);
  const [generating, setGenerating] = useState(false);

  const loadToday = useCallback(async () => {
    try {
      const r = await api.reports.today();
      setReport(r);
    } catch { /* no report yet */ }
    finally { setFetching(false); }
  }, []);

  useEffect(() => { loadToday(); }, [loadToday]);

  const handleGenerate = async () => {
    setGenerating(true);
    const taskId = start("Generate Report", "Fetching news from all sources and running the briefing engine…");
    try {
      const r = await api.reports.generate();
      setReport(r);
      finish(taskId, "success", "Briefing ready — stories filtered and written across all four layers.");
    } catch (err: unknown) {
      finish(taskId, "error", err instanceof Error ? err.message : "Generation failed");
    } finally {
      setGenerating(false);
    }
  };

  const section: Section | undefined = report?.sections[activeLayer];
  const today = new Date();

  return (
    <div className="min-h-screen" style={{ background: "#f5f1eb" }}>

      {/* ───── Hero / masthead ───── */}
      <div style={{ borderBottom: "1px solid #d8d0c4", background: "#ffffff" }}>
        <div className="max-w-6xl mx-auto px-12 py-12">

          <div className="flex items-end justify-between gap-8 flex-wrap">
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
                className="text-[44px] leading-[1.05]"
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
                  className="inline-flex items-center gap-2.5 px-7 py-3.5 text-[11px] tracking-[0.22em] uppercase font-semibold transition-opacity disabled:opacity-50"
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
      <div className="max-w-6xl mx-auto px-12 py-12">

        {/* Loading */}
        {fetching && (
          <div className="flex items-center justify-center gap-3 py-20 text-[12px] tracking-[0.2em] uppercase" style={{ color: "#787878" }}>
            <Loader2 size={14} className="animate-spin" />
            Loading today&apos;s briefing
          </div>
        )}

        {/* Generating overlay */}
        {generating && (
          <div className="text-center py-20" style={{ background: "#ffffff", border: "1px solid #d8d0c4" }}>
            <Loader2 size={28} className="animate-spin mx-auto mb-6" style={{ color: "#b8962e" }} strokeWidth={1.5} />
            <h3 className="text-[24px] mb-2" style={{ fontFamily: "'Rufina', Georgia, serif", color: "#0a0f1e" }}>
              Fetching the day&apos;s dispatches
            </h3>
            <p className="text-[13px] max-w-md mx-auto leading-relaxed" style={{ color: "#787878" }}>
              N.E.W.S. is querying the wires and running them through the briefing engine.
              This usually takes about 30–60 seconds.
            </p>
          </div>
        )}

        {/* Empty state */}
        {!fetching && !generating && !report && (
          <div className="text-center py-24" style={{ background: "#ffffff", border: "1px solid #d8d0c4" }}>
            <h2
              className="text-[120px] leading-none mb-6 tracking-[0.06em]"
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
            <div className="mb-14 max-w-3xl mx-auto text-center">
              <div className="gold-rule mx-auto mb-6" style={{ width: "60px" }} />
              <p
                className="text-[22px] leading-[1.45] italic"
                style={{ fontFamily: "'Rufina', Georgia, serif", color: "#3a3a3a" }}
              >
                &ldquo;{report.opening_line}&rdquo;
              </p>
              <div className="gold-rule mx-auto mt-6" style={{ width: "60px" }} />
            </div>

            {/* Layer tabs — editorial section nav */}
            <div className="flex items-end justify-center gap-10 mb-12 flex-wrap" style={{ borderBottom: "1px solid #d8d0c4" }}>
              {LAYERS.map(({ key, label, desc }) => {
                const active = activeLayer === key;
                const count = report.sections[key as LayerKey]?.stories.length ?? 0;
                return (
                  <button
                    key={key}
                    onClick={() => setActiveLayer(key as LayerKey)}
                    className="pb-4 px-1 transition-colors text-center group"
                    style={{
                      borderBottom: active ? "2px solid #b8962e" : "2px solid transparent",
                      marginBottom: "-1px",
                    }}
                  >
                    <p
                      className="text-[10px] tracking-[0.25em] uppercase mb-1.5"
                      style={{ color: active ? "#b8962e" : "#787878", fontWeight: 600 }}
                    >
                      {key} · {label}
                    </p>
                    <p
                      className="text-[28px] leading-none mb-1"
                      style={{
                        fontFamily: "'Rufina', Georgia, serif",
                        color: active ? "#0a0f1e" : "#3a3a3a",
                        fontWeight: 400,
                      }}
                    >
                      {count}
                    </p>
                    <p className="text-[10px]" style={{ color: "#a0a0a0" }}>
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
