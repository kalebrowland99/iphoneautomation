/** True when /automation was opened from the iMouse farm (jobId + farmUrl query params). */
export function isFarmUploadActive(farmUpload) {
  return Boolean(farmUpload?.jobId && farmUpload?.farmUrl);
}
