"use client";

import CollageSlide from "./slides/CollageSlide";
import ItemRevealSlide from "./slides/ItemRevealSlide";
import ThriftySlide from "./slides/ThriftySlide";
import LabelySlide from "./slides/LabelySlide";
import LabelyShelfIntroSlide from "./slides/LabelyShelfIntroSlide";
import FullBleedSlide from "./slides/FullBleedSlide";
import IMessageMomSlide from "./slides/IMessageMomSlide";
import VoicemailMomSlide from "./slides/VoicemailMomSlide";
import IMessageTextSlide from "./slides/IMessageTextSlide";
import StarterPackSlide from "./slides/StarterPackSlide";
import {
  getSlideInfo,
  isLabelySingleSlideFormat,
  isLabelyScanTourFormat,
  skipsCollageOpening,
  scanTourSlotCount,
} from "@/lib/slideLayout";
import { getBrand } from "@/lib/brand";

// At 0.28 scale → 1080×1920 renders as ~302×538px in browser
export const DISPLAY_SCALE = 0.28;

export { getSlideInfo };

function SlideRenderer({ config, info, S }) {
  return (
    <>
      {info.type === "collage" && <CollageSlide config={config} S={S} />}
      {info.type === "reveal" && <ItemRevealSlide slot={info.slot} S={S} config={config} />}
      {info.type === "thrifty" && <ThriftySlide slot={info.slot} S={S} config={config} />}
      {info.type === "labely" && <LabelySlide slot={info.slot} S={S} config={config} itemIndex={info.itemIndex ?? 0} />}
      {info.type === "labelyShelfIntro" && (
        <LabelyShelfIntroSlide
          slot={info.slot}
          S={S}
          hidePlaceholder={config.appId === "valcoin"}
        />
      )}
      {info.type === "fullBleed" && <FullBleedSlide slot={info.slot} S={S} />}
      {info.type === "imessage"     && <IMessageMomSlide  slot={info.slot} S={S} config={config} />}
      {info.type === "voicemail"    && <VoicemailMomSlide slot={info.slot} S={S} config={config} />}
      {info.type === "imessageText" && <IMessageTextSlide  slot={info.slot} S={S} config={config} />}
      {info.type === "starterPack"  && <StarterPackSlide config={config} S={S} phase={config._spPhase ?? -1} />}
    </>
  );
}

export default function VideoPreview({ config, currentSlide, setCurrentSlide, totalSlides, isGenerating, onRefreshSlide }) {
  const S = DISPLAY_SCALE;
  const W = Math.round(1080 * S);
  const H = Math.round(1920 * S);

  const info = getSlideInfo(config, currentSlide);

  const fmt = config.outputFormat ?? "standard";
  const brand = getBrand(config);
  const labelySingleSlide = isLabelySingleSlideFormat(config);
  const valcoinScanTour = brand.appId === "valcoin" && isLabelyScanTourFormat(config);

  const slideLabel = () => {
    if (isLabelyScanTourFormat(config)) {
      const tourSlots = scanTourSlotCount(config);
      if (currentSlide === 0) {
        return brand.appId === "valcoin" ? "6-coin collage" : "Intro (scan source)";
      }
      return `${brand.appId === "valcoin" ? "Valcoin" : "Labely"} ${currentSlide} of ${tourSlots} · scan → slide (export)`;
    }
    if (labelySingleSlide) {
      return "Labely";
    }
    if (fmt === "posePerson") {
      return `Pose ${currentSlide + 1}`;
    }
    if (currentSlide === 0) return "Collage";
    if (fmt === "appOnly") {
      return `Item ${currentSlide} — App`;
    }
    if (fmt === "imessageMom") {
      if (currentSlide === 0) return "iMessage (photo)";
      if (currentSlide === 1) return "Voicemail";
      if (currentSlide === 2) return "iMessage (texts)";
      return brand.appId === "labely" ? "Labely" : `${brand.appName} Price`;
    }
    if (fmt === "starterPack") return "Starter Pack";
    const item = Math.floor((currentSlide - 1) / 2) + 1;
    const appSlideLabel = brand.appId === "labely" ? "Labely" : `${brand.appName} Price`;
    const type = (currentSlide - 1) % 2 === 0 ? "Reveal" : appSlideLabel;
    return `Item ${item} — ${type}`;
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 12 }}>
      {/* Slide label */}
      <div
        className="flex items-center gap-3"
        aria-label={
          valcoinScanTour ? `Slide ${currentSlide + 1} of ${totalSlides}` : undefined
        }
      >
        <button
          onClick={() => setCurrentSlide((s) => Math.max(0, s - 1))}
          disabled={currentSlide === 0}
          className="flex h-7 w-7 items-center justify-center rounded-full border border-border bg-background text-sm text-foreground transition-colors hover:bg-muted/50 disabled:opacity-25"
        >
          ←
        </button>
        {!valcoinScanTour ? (
          <span className="min-w-[140px] text-center text-xs font-medium text-muted-foreground">{slideLabel()}</span>
        ) : (
          <span className="min-w-[140px]" aria-hidden />
        )}
        <button
          onClick={() => setCurrentSlide((s) => Math.min(totalSlides - 1, s + 1))}
          disabled={currentSlide === totalSlides - 1}
          className="flex h-7 w-7 items-center justify-center rounded-full border border-border bg-background text-sm text-foreground transition-colors hover:bg-muted/50 disabled:opacity-25"
        >
          →
        </button>
      </div>

      {/* Slide frame */}
      <div
        style={{
          width: W,
          height: H,
          borderRadius: Math.round(20 * S),
          boxShadow: "0 24px 64px rgba(0,0,0,0.7), 0 0 0 1px rgba(255,255,255,0.08)",
          flexShrink: 0,
          position: "relative",
        }}
      >
        <div
          id="video-preview-root"
          style={{ width: "100%", height: "100%", borderRadius: "inherit", overflow: "hidden", position: "relative" }}
        >
          <SlideRenderer config={config} info={info} S={S} />
        </div>

        {/* Per-slide AI refresh button */}
        <button
          onClick={() => !isGenerating && onRefreshSlide?.(currentSlide)}
          disabled={isGenerating}
          title={
            isGenerating
              ? "Generating…"
              : brand.appId === "labely"
                ? "Re-analyze this slot (uses uploaded photo)"
                : "Regenerate with AI"
          }
          style={{
            position: "absolute",
            bottom: Math.round(14 * S),
            right: Math.round(14 * S),
            width: Math.round(64 * S),
            height: Math.round(64 * S),
            borderRadius: "50%",
            background: isGenerating ? "rgba(109,40,217,0.85)" : "rgba(30,30,30,0.75)",
            border: "1.5px solid rgba(255,255,255,0.18)",
            backdropFilter: "blur(8px)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            cursor: isGenerating ? "default" : "pointer",
            fontSize: Math.round(26 * S),
            zIndex: 20,
            boxShadow: "0 2px 12px rgba(0,0,0,0.5)",
            transition: "background 0.2s",
          }}
        >
          {isGenerating ? (
            <div style={{
              width: Math.round(16 * S),
              height: Math.round(16 * S),
              border: `${Math.round(2 * S)}px solid rgba(255,255,255,0.3)`,
              borderTop: `${Math.round(2 * S)}px solid #fff`,
              borderRadius: "50%",
              animation: "spin 0.7s linear infinite",
            }} />
          ) : "🔄"}
        </button>
      </div>

      {/* Slide dots */}
      <div className="flex gap-1 flex-wrap justify-center max-w-[340px]">
        {Array.from({ length: totalSlides }).map((_, i) => {
          const isCollage =
            !skipsCollageOpening(config) &&
            fmt !== "posePerson" &&
            fmt !== "imessageMom" &&
            i === 0;
          const isReveal =
            fmt === "standard" && i > 0 && (i - 1) % 2 === 0;
          const momPhoto = false;
          const momMsg     = fmt === "imessageMom" && i === 0;
          const momVm      = fmt === "imessageMom" && i === 1;
          const momTxt     = fmt === "imessageMom" && i === 2;
          const momThrifty = fmt === "imessageMom" && i === 3;
          const isPose = fmt === "posePerson";
          const dotColor = isCollage
            ? "bg-muted-foreground/50"
            : isReveal
            ? "bg-muted-foreground/70"
            : momVm
            ? "bg-[#b45309]"
            : "bg-[#059669]";
          return (
            <button
              key={i}
              onClick={() => setCurrentSlide(i)}
              className={`h-2 w-2 rounded-full transition-all ${
                i === currentSlide
                  ? `${dotColor} scale-125 ring-2 ring-border`
                  : "bg-border hover:bg-muted-foreground/40"
              }`}
            />
          );
        })}
      </div>
      {fmt === "posePerson" ? (
        <div className="flex gap-4 text-xs text-muted-foreground">
          <span className="flex items-center gap-1"><span className="inline-block h-2 w-2 rounded-full bg-muted-foreground/60"/>Pose</span>
        </div>
      ) : (
        <div className="flex flex-wrap justify-center gap-4 text-xs text-muted-foreground">
          {fmt === "imessageMom" ? (
            <>
              <span className="flex items-center gap-1"><span className="inline-block h-2 w-2 rounded-full bg-muted-foreground/60"/>iMessage</span>
              <span className="flex items-center gap-1"><span className="inline-block h-2 w-2 rounded-full bg-[#b45309]"/>Voicemail</span>
              <span className="flex items-center gap-1"><span className="inline-block h-2 w-2 rounded-full bg-muted-foreground/40"/>Text reply</span>
              <span className="flex items-center gap-1"><span className="inline-block h-2 w-2 rounded-full bg-[#059669]"/>{brand.appId === "labely" ? "Labely" : brand.appName}</span>
            </>
          ) : skipsCollageOpening(config) ? (
            !valcoinScanTour ? (
              <>
                <span className="flex items-center gap-1"><span className="inline-block h-2 w-2 rounded-full bg-[#059669]"/>{brand.appId === "valcoin" ? "Valcoin" : "Labely"}</span>
                {(config.outputFormat ?? "standard") === "labelyScan" && (
                  <>
                    <span className="flex items-center gap-1"><span className="inline-block h-2 w-2 rounded-full bg-[#2563eb]"/>Scan × {scanTourSlotCount(config)} → slide</span>
                    <span className="text-muted-foreground/70">· includes intro</span>
                  </>
                )}
              </>
            ) : null
          ) : valcoinScanTour ? (
            <>
              <span className="flex items-center gap-1"><span className="inline-block h-2 w-2 rounded-full bg-muted-foreground/50"/>Collage</span>
              <span className="flex items-center gap-1"><span className="inline-block h-2 w-2 rounded-full bg-[#2563eb]"/>Scan × {scanTourSlotCount(config)} → Valcoin slide-up</span>
            </>
          ) : (
            <>
              <span className="flex items-center gap-1"><span className="inline-block h-2 w-2 rounded-full bg-muted-foreground/50"/>Collage</span>
              {fmt === "standard" && (
                <span className="flex items-center gap-1"><span className="inline-block h-2 w-2 rounded-full bg-muted-foreground/70"/>Reveal</span>
              )}
              <span className="flex items-center gap-1"><span className="inline-block h-2 w-2 rounded-full bg-[#059669]"/>{brand.appId === "labely" ? "Labely" : brand.appName}</span>
            </>
          )}
        </div>
      )}

    </div>
  );
}
