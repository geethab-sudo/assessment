import { useCallback, useEffect, useMemo, useState } from "react";

function parseMs(iso) {
  if (!iso) return null;
  const t = Date.parse(iso);
  return Number.isFinite(t) ? t : null;
}

function formatRemaining(ms) {
  const total = Math.max(0, Math.floor(ms / 1000));
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  if (h > 0) {
    return `${h}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
  }
  return `${m}:${String(s).padStart(2, "0")}`;
}

/**
 * @param {object|null} assessment
 * @param {{ onMainExpire?: () => void, onNotebookGraceEnd?: () => void }} callbacks
 */
export function useAssessmentTimer(assessment, { onMainExpire, onNotebookGraceEnd } = {}) {
  const [nowMs, setNowMs] = useState(() => Date.now());
  const [mainExpiredFired, setMainExpiredFired] = useState(false);
  const [graceEndFired, setGraceEndFired] = useState(false);

  const timer = assessment?.timer;
  const isTimed = Boolean(assessment?.is_timed && timer);

  const clockOffsetMs = useMemo(() => {
    const server = parseMs(timer?.server_now);
    if (server == null) return 0;
    return Date.now() - server;
  }, [timer?.server_now]);

  const expiresMs = parseMs(timer?.expires_at);
  const notebookExpiresMs = parseMs(timer?.notebook_expires_at);

  const serverNowMs = nowMs - clockOffsetMs;
  const mainRemainingMs =
    expiresMs != null ? Math.max(0, expiresMs - serverNowMs) : null;
  const notebookRemainingMs =
    notebookExpiresMs != null ? Math.max(0, notebookExpiresMs - serverNowMs) : null;

  const inMainWindow = isTimed && mainRemainingMs != null && mainRemainingMs > 0;
  const inNotebookGrace =
    isTimed &&
    mainRemainingMs === 0 &&
    notebookRemainingMs != null &&
    notebookRemainingMs > 0;

  const mainTone = useMemo(() => {
    if (!isTimed || mainRemainingMs == null) return "normal";
    if (mainRemainingMs <= 0) return "ended";
    if (mainRemainingMs < 60_000) return "critical";
    if (mainRemainingMs < 5 * 60_000) return "warning";
    return "normal";
  }, [isTimed, mainRemainingMs]);

  useEffect(() => {
    if (!isTimed) return undefined;
    const id = setInterval(() => setNowMs(Date.now()), 1000);
    return () => clearInterval(id);
  }, [isTimed]);

  useEffect(() => {
    if (!isTimed || mainExpiredFired) return;
    if (mainRemainingMs === 0) {
      setMainExpiredFired(true);
      onMainExpire?.();
    }
  }, [isTimed, mainRemainingMs, mainExpiredFired, onMainExpire]);

  useEffect(() => {
    if (!isTimed || graceEndFired) return;
    if (mainRemainingMs === 0 && notebookRemainingMs === 0) {
      setGraceEndFired(true);
      onNotebookGraceEnd?.();
    }
  }, [isTimed, mainRemainingMs, notebookRemainingMs, graceEndFired, onNotebookGraceEnd]);

  useEffect(() => {
    setMainExpiredFired(false);
    setGraceEndFired(false);
  }, [assessment?.assessment_id, timer?.started_at]);

  return {
    isTimed,
    inMainWindow,
    inNotebookGrace,
    mainLabel: mainRemainingMs != null ? formatRemaining(mainRemainingMs) : null,
    notebookLabel:
      notebookRemainingMs != null ? formatRemaining(notebookRemainingMs) : null,
    mainTone,
    mainRemainingMs,
    notebookRemainingMs,
  };
}
