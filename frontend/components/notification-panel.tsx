"use client";

import { useEffect, useRef } from "react";
import { X, CheckCircle2, XCircle, Loader2, Trash2, Clock } from "lucide-react";
import { useNotifications, Task } from "@/lib/notifications-context";

function duration(task: Task): string {
  const end = task.finishedAt ?? new Date();
  const secs = Math.round((end.getTime() - task.startedAt.getTime()) / 1000);
  if (secs < 60) return `${secs}s`;
  return `${Math.floor(secs / 60)}m ${secs % 60}s`;
}

function timeAgo(date: Date): string {
  const secs = Math.round((Date.now() - date.getTime()) / 1000);
  if (secs < 60) return "just now";
  if (secs < 3600) return `${Math.floor(secs / 60)}m ago`;
  return `${Math.floor(secs / 3600)}h ago`;
}

const STATUS_ICON = {
  running: <Loader2 size={13} className="animate-spin" style={{ color: "#b8962e" }} strokeWidth={1.8} />,
  success: <CheckCircle2 size={13} style={{ color: "#5b8a4e" }} strokeWidth={1.8} />,
  error:   <XCircle size={13} style={{ color: "#b91c1c" }} strokeWidth={1.8} />,
};

const STATUS_LABEL = {
  running: { text: "In Progress", color: "#b8962e" },
  success: { text: "Complete",    color: "#5b8a4e" },
  error:   { text: "Failed",      color: "#b91c1c" },
};

// Mirrors STAGE_LABELS in the dashboard so the Activity panel speaks the same
// language as the inline progress bar.
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

function stageLabel(stage?: string): string {
  if (!stage) return "Working";
  return STAGE_LABELS[stage] ?? "Working";
}

interface Props {
  open: boolean;
  onClose: () => void;
}

export function NotificationPanel({ open, onClose }: Props) {
  const { tasks, clear, markAllRead } = useNotifications();
  const panelRef = useRef<HTMLDivElement>(null);

  useEffect(() => { if (open) markAllRead(); }, [open, markAllRead]);

  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (panelRef.current && !panelRef.current.contains(e.target as Node)) {
        onClose();
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open, onClose]);

  return (
    <>
      {open && (
        <div
          className="fixed inset-0 z-40"
          style={{ background: "rgba(10, 15, 30, 0.5)" }}
          aria-hidden
        />
      )}

      <div
        ref={panelRef}
        className="fixed top-0 right-0 h-full z-50 flex flex-col transition-transform duration-300 w-full sm:w-[380px] max-w-full"
        style={{
          background: "#0a0f1e",
          borderLeft: "1px solid #1e2d4a",
          transform: open ? "translateX(0)" : "translateX(100%)",
        }}
      >
        {/* Header */}
        <div
          className="px-7 py-7"
          style={{ borderBottom: "1px solid #1e2d4a" }}
        >
          <div className="flex items-start justify-between">
            <div>
              <p
                className="text-[10px] tracking-[0.3em] uppercase mb-2"
                style={{ color: "#b8962e", fontWeight: 600 }}
              >
                Editorial Desk
              </p>
              <h2
                className="text-[26px] leading-none"
                style={{ fontFamily: "'Rufina', Georgia, serif", color: "#ffffff" }}
              >
                Activity
              </h2>
            </div>
            <div className="flex items-center gap-2">
              {tasks.length > 0 && (
                <button
                  onClick={clear}
                  className="p-1.5 transition-colors"
                  style={{ color: "#6b7fa0" }}
                  title="Clear all"
                >
                  <Trash2 size={13} strokeWidth={1.5} />
                </button>
              )}
              <button
                onClick={onClose}
                className="p-1.5 transition-colors"
                style={{ color: "#6b7fa0" }}
              >
                <X size={15} strokeWidth={1.5} />
              </button>
            </div>
          </div>
          <p className="text-[11px] mt-3" style={{ color: "#6b7fa0" }}>
            Long-running tasks from this session.
          </p>
        </div>

        {/* Task list */}
        <div className="flex-1 overflow-y-auto px-7 py-5 space-y-0">
          {tasks.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-64 gap-4">
              <Clock size={26} style={{ color: "#1e2d4a" }} strokeWidth={1.5} />
              <p
                className="text-[14px] italic"
                style={{ fontFamily: "'Rufina', Georgia, serif", color: "#6b7fa0" }}
              >
                No activity yet.
              </p>
            </div>
          ) : (
            tasks.map((task, i) => (
              <div
                key={task.id}
                className="py-5"
                style={{ borderBottom: i < tasks.length - 1 ? "1px solid #1e2d4a" : undefined }}
              >
                <div className="flex items-center gap-2 mb-2">
                  {STATUS_ICON[task.status]}
                  <span
                    className="text-[9px] tracking-[0.22em] uppercase"
                    style={{ color: STATUS_LABEL[task.status].color, fontWeight: 600 }}
                  >
                    {STATUS_LABEL[task.status].text}
                  </span>
                  <span className="flex-1" />
                  <span className="text-[10px]" style={{ color: "#6b7fa0" }}>
                    {timeAgo(task.startedAt)}
                  </span>
                </div>

                <h3
                  className="text-[18px] leading-tight mb-2"
                  style={{ fontFamily: "'Rufina', Georgia, serif", color: "#ffffff" }}
                >
                  {task.title}
                </h3>

                <p className="text-[12px] leading-relaxed mb-2" style={{ color: "#8b9cb8" }}>
                  {task.message}
                </p>

                {/* Live progress bar — only while running */}
                {task.status === "running" && (
                  <div className="mt-3 mb-3">
                    <div className="flex items-center justify-between mb-2">
                      <span
                        className="text-[10px] tracking-[0.18em] uppercase"
                        style={{ color: "#8b9cb8", fontWeight: 600 }}
                      >
                        {stageLabel(task.stage)}
                      </span>
                      <span
                        className="text-[10px] tracking-[0.18em] uppercase"
                        style={{ color: "#b8962e", fontWeight: 600 }}
                      >
                        {task.progress ?? 0}%
                      </span>
                    </div>
                    <div
                      className="w-full h-[4px]"
                      style={{ background: "#1e2d4a", overflow: "hidden" }}
                      role="progressbar"
                      aria-valuenow={task.progress ?? 0}
                      aria-valuemin={0}
                      aria-valuemax={100}
                    >
                      <div
                        className="h-full transition-all duration-500 ease-out"
                        style={{ width: `${Math.max(2, task.progress ?? 0)}%`, background: "#b8962e" }}
                      />
                    </div>
                  </div>
                )}

                <p className="text-[10px] tracking-[0.15em] uppercase" style={{ color: "#6b7fa0" }}>
                  Duration · {duration(task)}
                </p>
              </div>
            ))
          )}
        </div>

        {/* Footer */}
        <div
          className="px-7 py-4 text-[10px] tracking-[0.18em] uppercase"
          style={{ borderTop: "1px solid #1e2d4a", color: "#6b7fa0" }}
        >
          Session-only
        </div>
      </div>
    </>
  );
}
