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
  // The model occasionally drops these fields when its JSON gets truncated at
  // the tail. Defaulting here so a single bad story can't crash the layer tab.
  const matchedTags = story.matched_tags ?? [];
  const firstTag = matchedTags[0];

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

      {/* Text block — tighter padding on mobile, full on desktop */}
      <div className={featured ? "p-5 sm:p-7 md:p-8" : "p-5 sm:p-6 pb-7"}>

        {/* Category line: tone + source */}
        <div className="flex items-center gap-2 mb-3 sm:mb-4 flex-wrap" style={{ minHeight: "12px" }}>
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
          className={
            featured
              ? "text-[22px] sm:text-[28px] md:text-[34px] leading-[1.15]"
              : "text-[18px] sm:text-[20px] leading-[1.25]"
          }
          style={{
            fontFamily: "'Rufina', Georgia, serif",
            color: "#0a0f1e",
            fontWeight: 400,
            letterSpacing: "-0.005em",
            wordBreak: "break-word",
          }}
        >
          {story.headline}
        </h3>

        {/* Hook — only on featured cards */}
        {featured && story.hook && (
          <p
            className="mt-3 sm:mt-4 text-[14px] sm:text-[15px] leading-relaxed italic"
            style={{ color: "#3a3a3a", fontFamily: "'Rufina', Georgia, serif" }}
          >
            {story.hook}
          </p>
        )}

        {/* Footer meta */}
        <div className="flex items-center gap-3 mt-4 sm:mt-5 pt-4 flex-wrap" style={{ borderTop: "1px solid #ede8df" }}>
          {firstTag && (
            <span className="text-[10px] tracking-[0.18em] uppercase" style={{ color: "#b8962e", fontWeight: 600 }}>
              {firstTag}
            </span>
          )}
          {firstTag && story.published_at && (
            <span style={{ color: "#d8d0c4" }}>·</span>
          )}
          {story.published_at && (
            <span className="text-[11px]" style={{ color: "#787878" }}>
              {formatDate(story.published_at)}
            </span>
          )}
          <span className="flex-1" />
          {/* Always visible on touch devices (hover never fires there). */}
          <span
            className="text-[10px] tracking-[0.18em] uppercase md:opacity-0 md:group-hover:opacity-100 transition-opacity"
            style={{ color: "#b8962e", fontWeight: 600 }}
          >
            Read →
          </span>
        </div>
      </div>
    </a>
  );
}
