"use client";

import { useState, useCallback, useRef, useMemo, useEffect } from "react";
import VideoPreview from "@/components/VideoPreview";
import LabelyScanSequencePreview from "@/components/LabelyScanSequencePreview";
import ConfigPanel from "@/components/ConfigPanel";
import GlobalJobBar from "@/components/GlobalJobBar";
import GalleryRail from "@/components/GalleryRail";
import VideoUniqueizer from "@/components/VideoUniqueizer";
import { AppNav, PreviewFrame } from "@/components/ui/acme-hero";
import { getTotalSlides, normalizeValcoinOutputFormat, LABELY_SCAN_TOUR_SLOTS } from "@/lib/slideLayout";
import {
  mergePersistedConfig,
  readHomeSession,
  writeHomeSession,
} from "@/lib/homeSessionStorage";
import { initFirebaseWebAnalytics, isFirebaseConfigured } from "@/lib/firebaseClient";
import { firebaseFriendlyError } from "@/lib/firebaseFriendlyError";
import { savedShowMatchesApp } from "@/lib/showAppId";
import { pruneBlankSavedSlideshows } from "@/lib/galleryShow";
export const emptySlot = (i) => ({
  imageUrl: null,
  prompt: "",
  itemName: `Item ${i + 1}`,
  spentPrice: "",
  soldPrice: "",
  date: new Date().toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" }),
  matchItems: [
    { title: "", source: "eBay", price: "", inStock: true },
    { title: "", source: "Poshmark", price: "", inStock: true },
  ],
  // Reveal slide caption style (mirrors collage caption design)
  revealCaptionBg:       "#000000",
  revealCaptionColor:    "#ffffff",
  revealCaptionPosition: "bottom",   // "top" | "middle" | "bottom"
  revealCaptionSize:     72,
  revealCaptionBold:     true,
  // Thrifty slide caption (mirrors collage caption design)
  thriftyCaptionText:     "",        // auto-generated from prices if empty
  thriftyCaptionBg:       "",   // empty = randomise per render
  thriftyCaptionColor:    "",   // empty = randomise per render
  thriftyCaptionPosition: "top",     // "top" | "middle" | "bottom"
  thriftyCaptionSize:     72,
  thriftyCaptionBold:     true,
  /** iMessage mom — voicemail slide transcript (empty → auto from item name) */
  voicemailTranscript: "",
  /** iMessage mom — AI-generated text thread [{from:"mom"|"son", text:string}] (null → seeded fallback) */
  imessageThread: null,
  /** Labely (nutrition-style UI) — filled when appId is labely */
  labelyBrand: "",
  labelyScore: 0,
  labelyVerdict: "",
  labelyAnalysis: "",
  labelyAnalysisTitle: "Labely's Analysis",
  labelyLegalNote: "No lawsuits found.",
  labelyShelfImageUrl: null,
  labelyDbImageUrl: null,
});

export const defaultConfig = {
  captionText: "",
  captionStyle: "tiktok",      // "tiktok" | "tickerBox"
  captionBg: "#e03030",
  captionColor: "#ffffff",

  // 6 image slots
  slots: Array.from({ length: 6 }, (_, i) => emptySlot(i)),

  // Video settings
  slideDuration: 2,    // seconds per slide
  transitionMs: 220,   // swipe transition duration ms

  /** Shown on iMessage-mom slides (TikTok-style corner). Empty → "@mom". */
  tiktokWatermark: "",
  /** Voicemail caller ID override (iMessage mom format). Empty → dynamic contact name. */
  voicemailDisplayNumber: "",
  /** Add a random track from public/audio/ to the exported video. */
  useRandomAudio: false,
  outputFormat: "standard", // "standard" | "appOnly" | … | "labelyOnly" | "labelyScan" (Labely app)
  appId: "thrifty", // "thrifty" | "valcoin" | "labely" | "videoUniqueizer"
  /** Headline text shown at the top of the Starter Pack slide */
  starterPackHeadline: "",
  /** Changed each generation so every export has unique pixel-level layout (anti-fingerprint). */
  jitterSeed: 0,
  /** @type {{ id: string, dataUrl: string }[]} */
  poseReferenceImages: [],

  /** Labely only: true = AI-generated packaged-food cards + product images (no uploads). */
  labelyAiProducts: true,
  /** Labely: product photos from Brave Image Search (not GPT pack shots). */
  labelyUseBraveImages: true,
  /** Labely AI-products only: use the pilates mirror selfie prompt for the first generated photo. */
  labelyUseSelfieImage: false,
  /** Labely scan tour: number of food scan/result pairs in the current saved slideshow. */
  labelyScanSlotCount: 3,
  /** Labely food list (newline-separated); persisted in home session so removals survive refresh. */
  labelyFoodItemsRaw: "",

};

export default function Home() {
  const [config, setConfig] = useState(defaultConfig);
  const [currentSlide, setCurrentSlide] = useState(0);
  const [isExporting, setIsExporting] = useState(false);
  const [exportProgress, setExportProgress] = useState(0);
  const [exportStatus, setExportStatus] = useState("");
  const [isGenerating, setIsGenerating] = useState(false);
  const refreshHandlerRef = useRef(null);
  /** Skip persisting until the first restore from localStorage has finished (avoids overwriting with defaults). */
  const skipSaveUntilHydrated = useRef(true);
  /** Serialize Firestore+Storage saves so rapid updates cannot exhaust the client write queue. */
  const firebaseRemoteSaveChainRef = useRef(Promise.resolve());

  // ── Batch slideshow gallery ──────────────────────────────────────────────────
  const [savedSlideshows, setSavedSlideshows] = useState([]);
  const [activeShowIdx, setActiveShowIdx] = useState(null);
  /** Batch generator slideshow count (persisted with home session). */
  const [numSlideshows, setNumSlideshows] = useState(3);
  /** Flat queue of workspace photos across all batch rows (persisted; fixes refresh blanks). */
  const [batchImageDataUrls, setBatchImageDataUrls] = useState([]);
  /** Firebase anonymous uid once signed in; enables cloud backup saves. */
  const [cloudUid, setCloudUid] = useState(null);
  const [cloudStatus, setCloudStatus] = useState("");
  const [cloudStatusDetail, setCloudStatusDetail] = useState("");
  const [reloadingSessionMedia, setReloadingSessionMedia] = useState(false);
  const reloadSessionMediaBusyRef = useRef(false);

  /** Apply persisted home session to React state (localStorage and/or Firebase payload). */
  const applySessionSnapshot = useCallback((raw) => {
    if (!raw || typeof raw !== "object") return defaultConfig;
    let merged = defaultConfig;
    if (raw.config && typeof raw.config === "object") {
      merged = mergePersistedConfig(defaultConfig, emptySlot, raw.config);
      setConfig(merged);
    }
    if (Array.isArray(raw.savedSlideshows)) {
      const cloned = raw.savedSlideshows.map((s) => ({
        ...s,
        slots: Array.isArray(s?.slots) ? s.slots.map((slot) => ({ ...slot })) : s?.slots,
      }));
      const { shows, activeShowIdx: prunedActive } = pruneBlankSavedSlideshows(
        cloned,
        raw.activeShowIdx,
      );
      setSavedSlideshows(shows);
      if (typeof prunedActive === "number" && prunedActive >= 0) {
        setActiveShowIdx(prunedActive);
      } else {
        setActiveShowIdx(null);
      }
    }
    const maxSlide = Math.max(0, getTotalSlides(merged) - 1);
    const cs = typeof raw.currentSlide === "number" ? raw.currentSlide : 0;
    setCurrentSlide(Math.min(Math.max(0, cs), maxSlide));
    if (!Array.isArray(raw.savedSlideshows)) {
      setActiveShowIdx(null);
    }
    if (typeof raw.numSlideshows === "number" && raw.numSlideshows >= 1 && raw.numSlideshows <= 120) {
      setNumSlideshows(raw.numSlideshows);
    }
    if (Array.isArray(raw.batchImageDataUrls)) {
      const aid = merged.appId ?? "thrifty";
      if (aid === "thrifty") {
        setBatchImageDataUrls(raw.batchImageDataUrls.map((x) => (typeof x === "string" && x.trim() ? x : null)));
      } else {
        setBatchImageDataUrls([]);
      }
    }
    return merged;
  }, []);

  /** Re-apply only gallery + batch image rows (used by “Reload media” — does not reset the editor workspace). */
  const applyGalleryAndBatchOnly = useCallback((raw) => {
    if (!raw || typeof raw !== "object") return;
    if (Array.isArray(raw.savedSlideshows)) {
      const cloned = raw.savedSlideshows.map((s) => ({
        ...s,
        slots: Array.isArray(s?.slots) ? s.slots.map((slot) => ({ ...slot })) : s?.slots,
      }));
      const { shows, activeShowIdx: prunedActive } = pruneBlankSavedSlideshows(
        cloned,
        raw.activeShowIdx,
      );
      setSavedSlideshows(shows);
      if (typeof prunedActive === "number" && prunedActive >= 0) {
        setActiveShowIdx(prunedActive);
      } else {
        setActiveShowIdx(null);
      }
    } else {
      setSavedSlideshows([]);
      setActiveShowIdx(null);
    }
    if (Array.isArray(raw.batchImageDataUrls)) {
      const aid = typeof raw.config?.appId === "string" ? raw.config.appId : "thrifty";
      if (aid === "thrifty") {
        setBatchImageDataUrls(raw.batchImageDataUrls.map((x) => (typeof x === "string" && x.trim() ? x : null)));
      } else {
        setBatchImageDataUrls([]);
      }
    }
  }, []);

  /** Write session immediately (food-list / batch edits must survive refresh before debounced save). */
  const persistHomeSessionNow = useCallback(
    (overrides = {}) => {
      if (skipSaveUntilHydrated.current) return;
      const payload = {
        v: 1,
        config: overrides.config ?? config,
        savedSlideshows: overrides.savedSlideshows ?? savedSlideshows,
        activeShowIdx: overrides.activeShowIdx ?? activeShowIdx,
        currentSlide: overrides.currentSlide ?? currentSlide,
        numSlideshows: overrides.numSlideshows ?? numSlideshows,
        batchImageDataUrls: overrides.batchImageDataUrls ?? batchImageDataUrls,
        savedAt: Date.now(),
      };
      writeHomeSession(payload);
      if (cloudUid && isFirebaseConfigured()) {
        firebaseRemoteSaveChainRef.current = firebaseRemoteSaveChainRef.current
          .catch(() => {})
          .then(async () => {
            const { saveHomeSessionRemote } = await import("@/lib/firebaseHomeSession");
            await saveHomeSessionRemote(cloudUid, payload);
          })
          .catch((e) => console.warn("[firebase] immediate save", e));
      }
    },
    [config, savedSlideshows, activeShowIdx, currentSlide, numSlideshows, batchImageDataUrls, cloudUid],
  );

  const reloadGalleryAndBatchMedia = useCallback(async () => {
    if (reloadSessionMediaBusyRef.current) return;
    reloadSessionMediaBusyRef.current = true;
    setReloadingSessionMedia(true);
    const prevSkip = skipSaveUntilHydrated.current;
    skipSaveUntilHydrated.current = true;
    try {
      setSavedSlideshows([]);
      setBatchImageDataUrls([]);
      setActiveShowIdx(null);
      await new Promise((r) => setTimeout(r, 50));

      const localRaw = readHomeSession();
      const localAt = typeof localRaw?.savedAt === "number" ? localRaw.savedAt : 0;
      let chosen = localRaw;

      if (isFirebaseConfigured() && cloudUid) {
        try {
          const { loadHomeSessionRemote } = await import("@/lib/firebaseHomeSession");
          const remote = await loadHomeSessionRemote(cloudUid);
          const remoteAt = typeof remote?.savedAt === "number" ? remote.savedAt : 0;
          if (remote && remoteAt > localAt) {
            chosen = {
              config: remote.config,
              savedSlideshows: remote.savedSlideshows,
              currentSlide: remote.currentSlide,
              activeShowIdx: remote.activeShowIdx,
              numSlideshows: remote.numSlideshows,
              batchImageDataUrls: remote.batchImageDataUrls,
              savedAt: remote.savedAt,
            };
          }
        } catch (e) {
          console.warn("[reload session media] firebase", e);
        }
      }

      if (chosen && typeof chosen === "object") {
        applyGalleryAndBatchOnly(chosen);
      }
    } finally {
      skipSaveUntilHydrated.current = prevSkip;
      reloadSessionMediaBusyRef.current = false;
      setReloadingSessionMedia(false);
    }
  }, [applyGalleryAndBatchOnly, cloudUid]);

  useEffect(() => {
    void initFirebaseWebAnalytics();
  }, []);

  useEffect(() => {
    let cancelled = false;

    (async () => {
      try {
        const raw = readHomeSession();
        const localSavedAt = typeof raw?.savedAt === "number" ? raw.savedAt : 0;
        if (raw) {
          applySessionSnapshot(raw);
        }

        if (!isFirebaseConfigured()) {
          return;
        }

        const { signInFirebaseAnonymously, loadHomeSessionRemote } = await import("@/lib/firebaseHomeSession");
        const uid = await signInFirebaseAnonymously();
        if (cancelled) return;
        if (!uid) {
          setCloudStatus("Firebase: sign-in failed (check Auth domain + Anonymous provider)");
          setCloudStatusDetail("signInFirebaseAnonymously returned null");
          return;
        }
        setCloudUid(uid);

        const remote = await loadHomeSessionRemote(uid);
        if (cancelled) return;
        if (!remote) {
          setCloudStatus("Firebase backup ready");
          setCloudStatusDetail("");
          return;
        }
        const remoteAt = typeof remote.savedAt === "number" ? remote.savedAt : 0;
        if (remoteAt > localSavedAt) {
          const snap = {
            config: remote.config,
            savedSlideshows: remote.savedSlideshows,
            currentSlide: remote.currentSlide,
            activeShowIdx: remote.activeShowIdx,
            numSlideshows: remote.numSlideshows,
            batchImageDataUrls: remote.batchImageDataUrls,
            savedAt: remote.savedAt,
          };
          const mergedRemote = applySessionSnapshot(snap);
          const galleryLen = Array.isArray(remote.savedSlideshows) ? remote.savedSlideshows.length : 0;
          const clampedActive =
            typeof remote.activeShowIdx === "number" && remote.activeShowIdx >= 0 && galleryLen > 0
              ? Math.min(remote.activeShowIdx, galleryLen - 1)
              : null;
          const maxSlideRemote = Math.max(0, getTotalSlides(mergedRemote) - 1);
          const clampedSlide = Math.min(
            Math.max(0, typeof remote.currentSlide === "number" ? remote.currentSlide : 0),
            maxSlideRemote,
          );
          writeHomeSession({
            v: 1,
            config: mergedRemote,
            savedSlideshows: remote.savedSlideshows,
            activeShowIdx: clampedActive,
            currentSlide: clampedSlide,
            numSlideshows: remote.numSlideshows,
            batchImageDataUrls: remote.batchImageDataUrls,
            savedAt: remote.savedAt,
          });
          setCloudStatus("Loaded newer session from Firebase");
          setCloudStatusDetail("");
        } else {
          setCloudStatus("Firebase backup ready");
          setCloudStatusDetail("");
        }
      } catch (e) {
        console.warn("[firebase]", e);
        if (!cancelled) {
          const h = firebaseFriendlyError(e);
          setCloudStatus(h.short);
          setCloudStatusDetail(h.detail);
        }
      } finally {
        if (!cancelled) skipSaveUntilHydrated.current = false;
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [applySessionSnapshot]);

  useEffect(() => {
    if (skipSaveUntilHydrated.current) return;
    const savedAt = Date.now();
    const t = window.setTimeout(() => {
      writeHomeSession({
        v: 1,
        config,
        savedSlideshows,
        activeShowIdx,
        currentSlide,
        numSlideshows,
        batchImageDataUrls,
        savedAt,
      });
    }, 400);
    return () => window.clearTimeout(t);
  }, [config, savedSlideshows, activeShowIdx, currentSlide, numSlideshows, batchImageDataUrls]);

  useEffect(() => {
    if (skipSaveUntilHydrated.current || !cloudUid || !isFirebaseConfigured()) return;
    if (isGenerating || isExporting) return;

    const t = window.setTimeout(() => {
      firebaseRemoteSaveChainRef.current = firebaseRemoteSaveChainRef.current
        .catch(() => {})
        .then(async () => {
          try {
            const { saveHomeSessionRemote } = await import("@/lib/firebaseHomeSession");
            await saveHomeSessionRemote(cloudUid, {
              config,
              savedSlideshows,
              activeShowIdx,
              currentSlide,
              numSlideshows,
              batchImageDataUrls,
              savedAt: Date.now(),
            });
            setCloudStatus("Backed up to Firebase");
            setCloudStatusDetail("");
          } catch (e) {
            console.warn("[firebase] save", e);
            const h = firebaseFriendlyError(e);
            setCloudStatus(h.short);
            setCloudStatusDetail(h.detail);
          }
        });
    }, 4500);
    return () => window.clearTimeout(t);
  }, [
    config,
    savedSlideshows,
    activeShowIdx,
    currentSlide,
    numSlideshows,
    batchImageDataUrls,
    cloudUid,
    isGenerating,
    isExporting,
  ]);

  const handleSlideshowSaved = useCallback((showData) => {
    setSavedSlideshows((prev) => {
      const next = [...prev, showData];
      setActiveShowIdx(next.length - 1);
      return next;
    });
  }, []);

  const prevAppIdForBatchRef = useRef(null);
  useEffect(() => {
    const aid = config.appId ?? "thrifty";
    const prev = prevAppIdForBatchRef.current;
    if (prev != null && prev !== aid) {
      setBatchImageDataUrls([]);
    }
    prevAppIdForBatchRef.current = aid;
  }, [config.appId]);

  const loadShow = useCallback((showData, idx) => {
    const isLabelyShow = showData.appId === "labely";
    const isValcoinShow = showData.appId === "valcoin";
    setConfig((prev) => ({
      ...prev,
      slots: showData.slots,
      captionText: "",
      ...(isLabelyShow
        ? { outputFormat: "labelyScan" }
        : isValcoinShow
          ? {
              outputFormat: normalizeValcoinOutputFormat(
                showData.outputFormat ?? prev.outputFormat,
              ),
            }
          : showData.outputFormat != null
            ? { outputFormat: showData.outputFormat }
            : {}),
      ...(showData.appId != null ? { appId: showData.appId } : {}),
      ...(showData.jitterSeed != null ? { jitterSeed: showData.jitterSeed } : {}),
      ...(showData.labelyOutroText != null ? { labelyOutroText: showData.labelyOutroText } : {}),
      ...(isLabelyShow
        ? { labelyScanSlotCount: showData.labelyScanSlotCount ?? LABELY_SCAN_TOUR_SLOTS }
        : showData.labelyScanSlotCount != null
          ? { labelyScanSlotCount: showData.labelyScanSlotCount }
          : {}),
    }));
    setActiveShowIdx(idx);
    setCurrentSlide(0);
    // Batch rows are a global queue for the next multi-show run; do not reuse another slideshow's queued URLs.
    setBatchImageDataUrls([]);
  }, []);

  const totalSlides = useMemo(() => getTotalSlides(config), [config]);
  const isVideoUniqueizer = (config.appId ?? "thrifty") === "videoUniqueizer";

  const galleryEntries = useMemo(() => {
    const aid = config.appId ?? "thrifty";
    return savedSlideshows
      .map((show, origIdx) => ({ show, origIdx }))
      .filter(({ show }) => savedShowMatchesApp(show, aid));
  }, [savedSlideshows, config.appId]);

  useEffect(() => {
    const aid = config.appId ?? "thrifty";
    setActiveShowIdx((idx) => {
      if (idx == null || idx < 0) return null;
      const show = savedSlideshows[idx];
      if (!show || !savedShowMatchesApp(show, aid)) return null;
      return idx;
    });
  }, [config.appId, savedSlideshows]);

  const updateConfig = useCallback((key, value) => {
    if (key === "appId") {
      setConfig((prev) => {
        if (value === prev.appId) return prev;
        const next = { ...prev, appId: value };
        next.slots = Array.from({ length: 6 }, (_, i) => emptySlot(i));
        next.captionText = "";
        next.jitterSeed = 0;
        if (value === "valcoin") {
          next.outputFormat = normalizeValcoinOutputFormat(next.outputFormat);
        }
        if (value !== "labely" && prev.appId === "labely") {
          if (["labelyOnly", "labelyScan"].includes(prev.outputFormat ?? "standard")) {
            next.outputFormat = "standard";
          }
        }
        if (value === "labely") {
          next.outputFormat = "labelyScan";
          next.labelyAiProducts = true;
          next.labelyUseBraveImages = true;
        }
        return next;
      });
      setBatchImageDataUrls([]);
      setActiveShowIdx(null);
      setCurrentSlide(0);
      return;
    }
    setConfig((prev) => {
      const next = { ...prev, [key]: value };
      if (key === "outputFormat" && next.appId === "valcoin") {
        next.outputFormat = normalizeValcoinOutputFormat(value);
      }
      if (key === "outputFormat") {
        const maxSlide = Math.max(0, getTotalSlides(next) - 1);
        Promise.resolve().then(() => {
          setCurrentSlide((s) => Math.min(s, maxSlide));
        });
      }
      return next;
    });
  }, []);

  const updateSlot = useCallback((index, updates) => {
    setConfig((prev) => ({
      ...prev,
      slots: prev.slots.map((s, i) => (i === index ? { ...s, ...updates } : s)),
    }));
  }, []);

  const updateMatchItem = useCallback((slotIndex, matchIndex, updates) => {
    setConfig((prev) => ({
      ...prev,
      slots: prev.slots.map((s, i) =>
        i === slotIndex
          ? {
              ...s,
              matchItems: s.matchItems.map((m, j) =>
                j === matchIndex ? { ...m, ...updates } : m
              ),
            }
          : s
      ),
    }));
  }, []);

  return (
    <div className="container max-w-6xl mx-auto px-4 pb-10">
        <AppNav
          appId={config.appId ?? "thrifty"}
          onAppIdChange={(nextAppId) => updateConfig("appId", nextAppId)}
          currentSlide={currentSlide}
          totalSlides={totalSlides}
          cloudStatus={isFirebaseConfigured() ? cloudStatus : ""}
          cloudStatusDetail={cloudStatusDetail}
          onReloadMedia={!isVideoUniqueizer ? () => void reloadGalleryAndBatchMedia() : undefined}
          reloadingMedia={reloadingSessionMedia}
          isExporting={isExporting}
          isGenerating={isGenerating}
          isVideoUniqueizer={isVideoUniqueizer}
        />

        <main className="relative py-8 md:py-10">
          <GlobalJobBar />
          {isVideoUniqueizer ? (
            <div className="dash-card p-4 md:p-6">
              <VideoUniqueizer />
            </div>
          ) : (
            <div className="grid items-start gap-5 md:gap-6 lg:grid-cols-5">
              <div className="dash-card p-4 md:p-5 lg:col-span-2 max-h-[calc(100vh-6rem)] overflow-y-auto">
                <ConfigPanel
                  config={config}
                  setConfig={setConfig}
                  updateConfig={updateConfig}
                  updateSlot={updateSlot}
                  updateMatchItem={updateMatchItem}
                  currentSlide={currentSlide}
                  setCurrentSlide={setCurrentSlide}
                  totalSlides={totalSlides}
                  isExporting={isExporting}
                  setIsExporting={setIsExporting}
                  exportProgress={exportProgress}
                  setExportProgress={setExportProgress}
                  exportStatus={exportStatus}
                  setExportStatus={setExportStatus}
                  onBusyChange={setIsGenerating}
                  registerRefreshSlide={(fn) => { refreshHandlerRef.current = fn; }}
                  onSlideshowSaved={handleSlideshowSaved}
                  onSavedSlideshowsChange={setSavedSlideshows}
                  activeShowIdx={activeShowIdx}
                  savedSlideshows={savedSlideshows}
                  numSlideshows={numSlideshows}
                  setNumSlideshows={setNumSlideshows}
                  batchImageDataUrls={batchImageDataUrls}
                  setBatchImageDataUrls={setBatchImageDataUrls}
                  persistHomeSessionNow={persistHomeSessionNow}
                />
              </div>

              <div className="flex min-w-0 flex-col gap-5 md:gap-6 lg:col-span-3">
                <div className="dash-card flex items-center justify-center p-4 md:p-5">
                  <PreviewFrame
                    subtitle={`${totalSlides} slides · ${config.slideDuration}s each`}
                    meta="1080 × 1920"
                  >
                    <div className="flex flex-col items-center gap-3">
                      <LabelyScanSequencePreview
                        config={config}
                        currentSlide={currentSlide}
                        setCurrentSlide={setCurrentSlide}
                        totalSlides={totalSlides}
                      />
                      <VideoPreview
                        config={config}
                        currentSlide={currentSlide}
                        setCurrentSlide={setCurrentSlide}
                        totalSlides={totalSlides}
                        isGenerating={isGenerating}
                        onRefreshSlide={(i) => refreshHandlerRef.current?.(i)}
                      />
                    </div>
                  </PreviewFrame>
                </div>

                {galleryEntries.length > 0 ? (
                  <GalleryRail
                    entries={galleryEntries}
                    activeShowIdx={activeShowIdx}
                    loadShow={loadShow}
                  />
                ) : null}
              </div>
            </div>
          )}
        </main>
    </div>
  );
}
