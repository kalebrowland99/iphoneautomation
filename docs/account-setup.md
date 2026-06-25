# Account setup checklist

Complete this **once per phone / TikTok account** before running `tiktok_prep` → `tiktok_post` → `tiktok_end`. The automation assumes a fixed UI layout on a ~406×720 mirrored screen (TikTok **45.6.0**).

---

## 1. TikTok app version

| Item | Requirement |
|------|-------------|
| TikTok version | **45.6.0** (recommended; do not auto-update without retesting) |

Pin the app version if your MDM or App Store settings allow it. Button positions and the editor toolbar layout are calibrated for this release.

---

## 2. Music — Favorites

The post workflow opens the music picker → **Favorites** → taps **Hvitserk's choice**.

- [ ] Open TikTok → create or edit a draft → music picker → **Favorites**
- [ ] **Only one song** should be saved there: **Hvitserk's choice**
- [ ] Remove any other tracks from Favorites (extra rows can cause OCR to tap the wrong song)

**Verify:** Dashboard → Debug → **Post: Wait + tap Favorites**, then **Post: Wait + tap "Hvitserk's choice"**.

---

## 3. VPN must be off before file upload

Gallery clear/upload uses the iMouse **Photos shortcut**. VPN (Shadowrocket) blocks or breaks that transfer.

- [ ] Before the first run of the day, open Shadowrocket and confirm **Not Connected** is visible (toggle gray / off)
- [ ] Prep turns VPN **on** only **after** album upload succeeds (`tiktok_prep` order: clear → upload → VPN → TikTok)
- [ ] End workflow turns VPN **off** again after posting

**Verify:** Dashboard → Debug → **Detect VPN not connected** before prep.

---

## 4. iMouse shortcut (album upload)

The phone must reach the Windows iMouse server for `shortcut_album_upload` / `shortcut_album_clear`.

**On the PC**

- [ ] iMouseXP server is running
- [ ] `config/config.yaml` → `imouse.host` / `imouse.port` match the server (default `localhost:9911` on the PC itself)

**On the iPhone (iMouse app / shortcut setup)**

- [ ] Album / Photos shortcut is installed and enabled per iMouseXP docs
- [ ] Shortcut server IP = **this PC's LAN IP** (not `127.0.0.1` — that only works on the PC)
- [ ] Phone and PC are on the same network; firewall allows the iMouse port
- [ ] Test upload: Dashboard → Debug → **Upload gallery** (uses absolute paths from `gallery/<slot>/`)

If upload fails or times out, fix the shortcut IP before running prep.

---

## 5. TikTok gallery → Recents

When posting, the flow opens the gallery picker and waits for **Recents** at the top before picking media.

- [ ] In TikTok's media picker, set the album dropdown to **Recents** (not Favorites, not a custom album)
- [ ] Leave it on Recents — prep uploads 3 files in slot order; post picks right → middle → left in Recents

Gallery tap coordinates (post 1 → 3): `(321, 194)`, `(191, 190)`, `(82, 201)`.

**Verify:** Dashboard → Debug → **Post: Wait for Recents (OCR)** with the picker open.

---

## 6. Home screen — dock layout

Automation taps app icons by template match on the **home screen**. Icons must be visible without swiping to another page.

| App | Position |
|-----|----------|
| **TikTok** | **Lower-right** slot of the pinned dock (4-icon bar) |
| **Shadowrocket** | **Same home screen page** as TikTok (workflow opens VPN from home between prep/post/end) |

- [ ] TikTok icon is in the dock, bottom-right
- [ ] Shadowrocket icon is on the **same** home screen (not buried in App Library or another page)
- [ ] Do not rearrange these icons after templates were captured; re-capture `config/templates/tiktok.jpg` and `shadowrocket.jpg` if you move them

**Verify:** Dashboard → Debug → template taps for **TikTok** and **End: Tap Shadowrocket**.

---

## 7. TikTok editor icon (third from top)

After text overlay (aa → Done), the workflow taps the **editor** at fixed coordinate **(374, 163)** — the **third icon from the top** on the right-side toolbar in TikTok 45.6.0.

- [ ] Open a draft on the post editor screen
- [ ] Count the vertical toolbar on the right: editor/scissors icon should be **3rd from the top**
- [ ] If TikTok updates and moves the toolbar, update the coord in `config/workflows/tiktok_post.yaml` (`tap_editor`) and debug test **Post: Tap editor (374, 163)**

**Verify:** Dashboard → Debug → **Post: Tap editor (374, 163)** on the editor screen.

---

## 8. Gallery media (PC)

- [ ] Assign the phone a slot folder: `gallery/<slot>/` (e.g. `gallery/12/`)
- [ ] Exactly **3** video/image files for the 3 posts, in upload order (post 1 = first file uploaded → rightmost in Recents)

---

## 9. Pre-flight (dashboard)

Run these debug tests on the device before a full pipeline start:

| Order | Debug test |
|-------|----------------|
| 1 | Upload gallery |
| 2 | Detect VPN not connected |
| 3 | Tap TikTok |
| 4 | Post: Wait for Recents (OCR) |
| 5 | Post: Wait + tap Favorites |
| 6 | Post: Wait + tap "Hvitserk's choice" |
| 7 | Post: Tap editor (374, 163) |

Then start **Full pipeline** or **Posts 2→3 + End** if resuming mid-run.

---

## Quick reference

| Topic | Value |
|-------|--------|
| TikTok version | 45.6.0 |
| Music | Single favorite: **Hvitserk's choice** |
| VPN during upload | **Off** (prep enables after upload) |
| iMouse shortcut IP | PC LAN IP, same network as phone |
| Gallery album | **Recents** |
| TikTok dock | Lower-right |
| Shadowrocket | Same home screen as TikTok |
| Editor icon | 3rd from top → tap **(374, 163)** |
| Post-upload wait | 5 minutes after post 3 before kill/VPN off |
