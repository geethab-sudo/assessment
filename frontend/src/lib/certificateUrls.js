/**
 * Resolve a public verification URL for sharing.
 * Prefers API-provided URLs; rewrites localhost links when running on a deployed host;
 * falls back to the current browser origin + certificate id.
 */
export function resolveVerificationUrl(meta) {
  const cid = meta?.certificate_id;
  const candidates = [meta?.verification_url, meta?.share_url].filter(Boolean);

  for (const raw of candidates) {
    if (typeof raw !== "string" || !/^https?:\/\//i.test(raw)) {
      continue;
    }
    try {
      const parsed = new URL(raw);
      const isLocalHost =
        parsed.hostname === "localhost" || parsed.hostname === "127.0.0.1";
      const onLocalHost =
        typeof window !== "undefined" &&
        (window.location.hostname === "localhost" ||
          window.location.hostname === "127.0.0.1");
      if (isLocalHost && !onLocalHost && cid != null) {
        return `${window.location.origin}/verify/certificate/${cid}`;
      }
      return raw;
    } catch {
      /* try next candidate */
    }
  }

  if (cid != null && Number.isFinite(Number(cid))) {
    const origin =
      typeof window !== "undefined" ? window.location.origin : "";
    if (origin) {
      return `${origin}/verify/certificate/${cid}`;
    }
  }

  return "";
}
