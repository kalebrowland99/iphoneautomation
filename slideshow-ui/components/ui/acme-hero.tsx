"use client";

import { Menu, RefreshCw } from "lucide-react";
import { Sheet, SheetContent, SheetTrigger } from "@/components/ui/sheet";
import { Button } from "@/components/ui/button";
import { motion } from "motion/react";

const APP_OPTIONS = [
  { id: "thrifty", label: "Thrifty" },
  { id: "valcoin", label: "Valcoin" },
  { id: "labely", label: "Labely" },
  { id: "videoUniqueizer", label: "Video Uniqueizer" },
];

function NavLinks({ appId, onAppIdChange, className = "" }) {
  return (
    <>
      {APP_OPTIONS.map(({ id, label }) => (
        <button
          key={id}
          type="button"
          onClick={() => onAppIdChange?.(id)}
          className={`${className} ${appId === id ? "active" : ""}`.trim()}
        >
          {label}
        </button>
      ))}
    </>
  );
}

export function AppNav({
  appId = "thrifty",
  onAppIdChange,
  currentSlide = 0,
  totalSlides = 1,
  cloudStatus = "",
  cloudStatusDetail = "",
  onReloadMedia,
  reloadingMedia = false,
  isExporting = false,
  isGenerating = false,
  isVideoUniqueizer = false,
  automationMode = false,
  automationTitle = "Farm automation",
  automationSubtitle = "",
}) {
  const slideLabel = isVideoUniqueizer
    ? "Video Uniqueizer"
    : `Slide ${currentSlide + 1} / ${totalSlides}`;

  return (
    <header className="relative shrink-0 pt-4">
      <nav className="flex items-center justify-between rounded-xl border bg-background py-2.5 px-4 shadow-lg">
        <div className="flex items-center gap-4 md:gap-6">
          {automationMode ? (
            <div className="min-w-0">
              <div className="text-sm font-semibold tracking-tight">{automationTitle}</div>
              {automationSubtitle ? (
                <div className="mt-0.5 truncate text-xs text-muted-foreground">{automationSubtitle}</div>
              ) : null}
            </div>
          ) : (
            <nav className="brand-nav flex min-w-0 items-center gap-1">
              <NavLinks appId={appId} onAppIdChange={onAppIdChange} />
            </nav>
          )}
        </div>
        <div className="flex shrink-0 items-center gap-3 text-xs text-muted-foreground">
          {cloudStatus ? (
            <span
              className="hidden max-w-[180px] truncate status-success lg:inline"
              title={cloudStatusDetail || cloudStatus}
            >
              {cloudStatus}
            </span>
          ) : null}
          {!isVideoUniqueizer && onReloadMedia ? (
            <button
              type="button"
              onClick={onReloadMedia}
              disabled={isGenerating || isExporting || reloadingMedia}
              className="btn-ghost hidden items-center gap-1.5 sm:inline-flex"
            >
              <RefreshCw
                className={`h-3 w-3 ${reloadingMedia ? "animate-spin" : ""}`}
              />
              {reloadingMedia ? "Reloading…" : "Reload media"}
            </button>
          ) : null}
          <span className="hidden tabular-nums sm:inline">{slideLabel}</span>
          <span className="hidden text-border md:inline">|</span>
          <Sheet>
            <SheetTrigger asChild>
              <Button variant="ghost" size="icon" className="h-7 w-7 sm:hidden">
                <Menu className="h-[15px] w-[15px]" />
                <span className="sr-only">Open menu</span>
              </Button>
            </SheetTrigger>
            <SheetContent side="right" className="w-[240px] sm:w-[300px]">
              <nav className="brand-nav flex flex-col items-stretch gap-1 pt-4">
                <NavLinks appId={appId} onAppIdChange={onAppIdChange} />
              </nav>
              {!isVideoUniqueizer && onReloadMedia ? (
                <button
                  type="button"
                  onClick={onReloadMedia}
                  disabled={isGenerating || isExporting || reloadingMedia}
                  className="btn-ghost mt-4 w-full justify-start"
                >
                  <RefreshCw
                    className={`mr-2 h-3 w-3 ${reloadingMedia ? "animate-spin" : ""}`}
                  />
                  Reload media
                </button>
              ) : null}
              <p className="mt-3 text-xs text-muted-foreground">{slideLabel}</p>
            </SheetContent>
          </Sheet>
        </div>
      </nav>
    </header>
  );
}

export function PreviewFrame({ children, subtitle, meta }) {
  const metaLine = [subtitle, meta].filter(Boolean).join(" · ");
  return (
    <div className="preview-chrome flex w-full flex-col items-center gap-3">
      {children}
      {metaLine ? <p className="preview-meta-line">{metaLine}</p> : null}
    </div>
  );
}

export function AcmeHero() {
  return (
    <div className="container mx-auto max-w-5xl px-4">
      <section className="py-16 text-center md:py-24">
        <motion.div
          className="mx-auto flex max-w-2xl flex-col items-center gap-6"
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.45 }}
        >
          <h1 className="text-4xl font-bold tracking-tighter sm:text-5xl md:text-6xl">
            Slideshows, Redefined
          </h1>
          <p className="text-muted-foreground sm:text-lg">
            TikTok-style slides with one-click export.
          </p>
          <div className="dash-card w-full overflow-hidden">
            <img
              src="https://images.unsplash.com/photo-1611162617474-5b21e939e986?w=1200&auto=format&fit=crop&q=80"
              alt="Phone showing vertical video content"
              className="aspect-[9/16] max-h-[480px] w-full object-cover"
            />
          </div>
        </motion.div>
      </section>
    </div>
  );
}
