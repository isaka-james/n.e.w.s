"use client";

import { useState } from "react";
import type { Story } from "@/lib/api";

interface Props {
  story: Story;
  featured?: boolean;
}

function formatDate(iso: string): string {
  if (!iso) return "";
  try {
    return new Date(iso).toLocaleDateString(undefined, {
      month: "short", day: "numeric",
    });
  } catch { return ""; }
}

export function StoryCard({ story, featured = false }: Props) {
  const [imgFailed, setImgFailed] = useState(false);
  const showImage = !!story.image_url && !imgFailed;
  const aspect = featured ? "21 / 9" : "16 / 10";

  return (
    <a
      href={story.url}
      target="_blank"
      rel="noopener noreferrer"
      className="story-card group block"
      style={{ background: "#ffffff", color: "#0a0f1e" }}
    >
      {/* Image — always rendered with patterned fallback */}
      <div className="card-img-wrap" style={{ aspectRatio: aspect }}>
        {showImage ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={story.image_url!}
            alt=""
            onError={() => setImgFailed(true)}
            loading="lazy"
          />
        ) : (
          <div className="card-image-fallback" style={{ width: "100%", height: "100%" }} />
        )}
      </div>

      {/* Text block */}
      <div style={{ padding: featured ? "32px" : "24px 24px 28px" }}>

        {/* Category line: tone + source */}
        <div className="flex items-center gap-2 mb-4" style={{ minHeight: "12px" }}>
          <span className={`tone-label tone-${story.tone_label}`}>
            {story.tone_label}
          </span>
          <span style={{ color: "#d8d0c4" }}>·</span>
          <span
            className="text-[10px] tracking-[0.15em] uppercase"
            style={{ color: "#787878", fontWeight: 500 }}
          >
            {story.source_name}
          </span>
        </div>

        {/* Headline — Rufina display */}
        <h3
          className={featured ? "text-[34px] leading-[1.15]" : "text-[20px] leading-[1.25]"}
          style={{
            fontFamily: "'Rufina', Georgia, serif",
            color: "#0a0f1e",
            fontWeight: 400,
            letterSpacing: "-0.005em",
          }}
        >
          {story.headline}
        </h3>

        {/* Hook — only on featured cards */}
        {featured && story.hook && (
          <p
            className="mt-4 text-[15px] leading-relaxed italic"
            style={{ color: "#3a3a3a", fontFamily: "'Rufina', Georgia, serif" }}
          >
            {story.hook}
          </p>
        )}

        {/* Footer meta */}
        <div className="flex items-center gap-3 mt-5 pt-4" style={{ borderTop: "1px solid #ede8df" }}>
          {story.matched_tags[0] && (
            <span className="text-[10px] tracking-[0.18em] uppercase" style={{ color: "#b8962e", fontWeight: 600 }}>
              {story.matched_tags[0]}
            </span>
          )}
          {story.matched_tags[0] && story.published_at && (
            <span style={{ color: "#d8d0c4" }}>·</span>
          )}
          {story.published_at && (
            <span className="text-[11px]" style={{ color: "#787878" }}>
              {formatDate(story.published_at)}
            </span>
          )}
          <span className="flex-1" />
          <span
            className="text-[10px] tracking-[0.18em] uppercase opacity-0 group-hover:opacity-100 transition-opacity"
            style={{ color: "#b8962e", fontWeight: 600 }}
          >
            Read →
          </span>
        </div>
      </div>
    </a>
  );
}
