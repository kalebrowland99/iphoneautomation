/**
 * Thrifty `SHARED_RULES_INTRO` — iPhone retail snapshot look (color, WB, subtle lens smear, deep focus).
 *
 * @param {"thrift" | "product"} [variant="product"] — last sentence of the focus paragraph (cart vs pack shot).
 */
export function iphoneRetailPhotoImperfectionPrompt(variant = "product") {
  const focusTail =
    variant === "thrift"
      ? "Store floor, distant racks, cart, and clothes must all read clearly in focus, like a casual phone snapshot with everything sharp."
      : "The product, nearby shelf or bin surfaces, and visible background must all read clearly in focus, like a casual phone snapshot with everything sharp.";

  return [
    "Aspect ratio requirement: Generate the image in 9:16 vertical portrait orientation only. This is mandatory. The image must be tall (portrait), optimized for smartphone viewing similar to TikTok or Instagram Reels. Do not generate square or landscape images. The composition must fill a 9:16 portrait frame from top to bottom.",
    "",
    "The photo should look like it was taken with an iPhone main rear camera using the default Camera app (Photo mode, no Portrait mode, no filter). Color should match iPhone\u2019s natural output: restrained saturation \u2014 noticeably less saturated than typical AI images or \u201cvivid\u201d social posts; true-to-life fabric and environment colors; no neon punch, no oversaturated primaries, no cinematic teal-orange grading. Aim for the calm, accurate look of an unedited shot in the iOS Photos app: moderate contrast, natural shadow roll-off, no HDR halos or glowing edges.",
    "",
    "Color temperature and white balance: overhead fluorescent retail lighting, neutral-to-slightly-cool white balance around 4500\u20135500K with a very slight green-neutral cast. Whites clean and neutral \u2014 not warm orange or amber. Zero golden-hour warmth, zero vintage filter, zero beauty-mode skin smoothing on any distant figures.",
    "",
    "Lens character (subtle): Include a very faint authentic smartphone-lens imperfection \u2014 a small soft smeared glare or streak near the brightest specular highlights (overhead tubes reflecting on lens glass), mild greenish or neutral flare typical of iPhone optics. Keep it minimal and realistic, not a dramatic sun-star or cinematic lens-flare overlay.",
    "",
    `Focus and depth (critical): Sharp focus from foreground through background across the entire 9:16 frame \u2014 deep focus only. No shallow depth of field, no background blur, no bokeh, no portrait-mode separation, no artificial Gaussian blur on the environment. ${focusTail}`,
  ].join("\n");
}
