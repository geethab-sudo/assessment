import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { fetchEmployeeReport } from "../lib/employeeReportApi.js";

function formatDate(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function formatDuration(totalSeconds) {
  const s = Math.max(0, Number(totalSeconds) || 0);
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  if (h > 0) return `${h}h ${m}m`;
  if (m > 0) return `${m}m`;
  return `${s}s`;
}

function topicChipClass(percent) {
  if (percent >= 75) return "emp-report-chip emp-report-chip--good";
  if (percent >= 50) return "emp-report-chip emp-report-chip--mid";
  return "emp-report-chip emp-report-chip--low";
}

function trendGlyph(trend) {
  if (trend === "up") return "↑";
  if (trend === "down") return "↓";
  if (trend === "flat") return "→";
  return "";
}

const UNEXPLORED_TOPIC_MAX_LEN = 30;

function truncateTopicName(name, maxLen = UNEXPLORED_TOPIC_MAX_LEN) {
  const s = String(name || "");
  if (s.length <= maxLen) return s;
  return `${s.slice(0, maxLen - 1)}…`;
}

function groupTopicsByTier(topics) {
  const groups = new Map();
  for (const name of topics || []) {
    const m = /^Tier\s*(\d+)/i.exec(name);
    const label = m ? `Tier ${m[1]}` : "Other";
    if (!groups.has(label)) groups.set(label, []);
    groups.get(label).push(name);
  }
  return [...groups.entries()].sort((a, b) => {
    const tierNum = (label) => {
      const m = /^Tier\s*(\d+)/i.exec(label);
      return m ? Number.parseInt(m[1], 10) : 999;
    };
    return tierNum(a[0]) - tierNum(b[0]);
  });
}

function ScoreRing({ percent, label }) {
  const r = 42;
  const c = 2 * Math.PI * r;
  const clamped = Math.min(100, Math.max(0, percent));
  const offset = c - (clamped / 100) * c;
  return (
    <div className="emp-report-ring" aria-label={`${label}: ${Math.round(clamped)} percent`}>
      <svg viewBox="0 0 100 100" width="120" height="120" role="img">
        <circle cx="50" cy="50" r={r} fill="none" stroke="rgba(0,0,0,0.08)" strokeWidth="9" />
        <circle
          cx="50"
          cy="50"
          r={r}
          fill="none"
          stroke="var(--emp-report-accent, #2563eb)"
          strokeWidth="9"
          strokeLinecap="round"
          strokeDasharray={c}
          strokeDashoffset={offset}
          transform="rotate(-90 50 50)"
        />
        <text x="50" y="48" textAnchor="middle" className="emp-report-ring-value">
          {Math.round(clamped)}%
        </text>
        <text x="50" y="62" textAnchor="middle" className="emp-report-ring-label">
          {label}
        </text>
      </svg>
    </div>
  );
}

function topicRadarSymbol(index) {
  return String.fromCharCode(65 + index);
}

function chartTextSize(expanded, chartWidth, compactSize = 11) {
  if (!expanded) return compactSize;
  return Math.round(compactSize * (chartWidth / 400));
}

function AssessmentXAxis({ n, xAt, width, height, padLeft, padRight, dense, expanded = false }) {
  const axisTitleY = height - 2;
  const tickY = height - (dense ? 22 : 16);
  const tickFont = chartTextSize(expanded, width, dense ? 9 : 10);
  const titleFont = chartTextSize(expanded, width, 10);

  return (
    <>
      {Array.from({ length: n }, (_, i) => (
        <text
          key={i}
          x={xAt(i)}
          y={tickY}
          textAnchor={dense ? "end" : "middle"}
          fontSize={tickFont}
          className={`emp-report-line-chart-axis emp-report-line-chart-axis--x${
            dense ? " emp-report-line-chart-axis--tilted" : ""
          }`}
          transform={dense ? `rotate(-32, ${xAt(i)}, ${tickY})` : undefined}
        >
          {i + 1}
        </text>
      ))}
      <text
        x={(padLeft + width - padRight) / 2}
        y={axisTitleY}
        textAnchor="middle"
        fontSize={titleFont}
        className="emp-report-chart-axis-title"
      >
        Assessments
      </text>
    </>
  );
}

function lineChartLayout(expanded) {
  return expanded
    ? { width: 760, height: 400, padLeft: 56, padRight: 28, padTop: 22, padBottom: 68 }
    : { width: 400, height: 196, padLeft: 44, padRight: 16, padTop: 14, padBottom: 54 };
}

function ChartLightbox({ open, title, onClose, children }) {
  useEffect(() => {
    if (!open) return undefined;
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const onKey = (e) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => {
      document.body.style.overflow = prevOverflow;
      window.removeEventListener("keydown", onKey);
    };
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div
      className="emp-report-chart-lightbox no-print"
      role="dialog"
      aria-modal="true"
      aria-label={title}
    >
      <button
        type="button"
        className="emp-report-chart-lightbox-backdrop"
        onClick={onClose}
        aria-label="Close chart"
      />
      <div
        className="emp-report-chart-lightbox-panel"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="emp-report-chart-lightbox-header">
          <h3>{title}</h3>
          <button
            type="button"
            className="emp-report-chart-lightbox-close"
            onClick={onClose}
            aria-label="Close"
          >
            ×
          </button>
        </header>
        <div className="emp-report-chart-lightbox-body">{children}</div>
      </div>
    </div>
  );
}

function ExpandableChartBlock({
  id,
  title,
  lead,
  expandedId,
  onExpand,
  renderChart,
  footer,
  className = "",
  showTitle = true,
}) {
  const isOpen = expandedId === id;
  const open = () => onExpand(id);
  const close = () => onExpand(null);

  const body = (expanded) => (
    <>
      {lead}
      <div
        className={
          expanded
            ? "emp-report-chart-canvas emp-report-chart-canvas--expanded"
            : "emp-report-chart-canvas"
        }
      >
        {renderChart(expanded)}
      </div>
      {footer}
    </>
  );

  return (
    <>
      <div
        className={`emp-report-chart-block emp-report-chart-block--expandable ${className}`.trim()}
        role="button"
        tabIndex={0}
        onClick={open}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            open();
          }
        }}
        aria-label={`${title} — click to enlarge`}
      >
        {showTitle && <h3>{title}</h3>}
        {body(false)}
        <p className="emp-report-chart-expand-hint muted small-print">Click to enlarge</p>
      </div>
      <ChartLightbox open={isOpen} title={title} onClose={close}>
        {body(true)}
      </ChartLightbox>
    </>
  );
}

function LineChart({ points, expanded = false }) {
  if (!points?.length) {
    return <p className="muted small-print">No score history yet.</p>;
  }

  const { width, height, padLeft, padRight, padTop, padBottom } = lineChartLayout(expanded);
  const chartW = width - padLeft - padRight;
  const chartH = height - padTop - padBottom;
  const yTicks = [0, 25, 50, 75, 100];
  const n = points.length;

  const coords = points.map((p, i) => {
    const x =
      padLeft + (n === 1 ? chartW / 2 : (i / Math.max(n - 1, 1)) * chartW);
    const percent = Math.min(100, Math.max(0, Number(p.percent) || 0));
    const y = padTop + chartH - (percent / 100) * chartH;
    return { x, y, percent, index: i + 1, assessment_id: p.assessment_id };
  });

  const poly =
    n > 1 ? coords.map((c) => `${c.x},${c.y}`).join(" ") : null;
  const denseXLabels = n > (expanded ? 14 : 8);
  const xAt = (i) =>
    padLeft + (n === 1 ? chartW / 2 : (i / Math.max(n - 1, 1)) * chartW);
  const axisFont = chartTextSize(expanded, width, 11);

  return (
    <div
      className={`emp-report-line-chart-wrap${
        expanded ? " emp-report-line-chart-wrap--expanded" : ""
      }`}
    >
      <svg
        viewBox={`0 0 ${width} ${height}`}
        className="emp-report-line-chart"
        role="img"
        aria-label="Score trend across assessments"
      >
        {yTicks.map((tick) => {
          const y = padTop + chartH - (tick / 100) * chartH;
          return (
            <g key={tick}>
              <line
                x1={padLeft}
                y1={y}
                x2={width - padRight}
                y2={y}
                className="emp-report-line-chart-grid"
              />
              <text
                x={padLeft - 8}
                y={y + 4}
                textAnchor="end"
                fontSize={axisFont}
                className="emp-report-line-chart-axis"
              >
                {tick}
              </text>
            </g>
          );
        })}

        <line
          x1={padLeft}
          y1={padTop}
          x2={padLeft}
          y2={padTop + chartH}
          className="emp-report-line-chart-axis-line"
        />
        <line
          x1={padLeft}
          y1={padTop + chartH}
          x2={width - padRight}
          y2={padTop + chartH}
          className="emp-report-line-chart-axis-line"
        />

        {poly && (
          <polyline
            fill="none"
            stroke="var(--emp-report-accent, #2563eb)"
            strokeWidth="2.5"
            points={poly}
          />
        )}

        {coords.map((c) => (
          <circle
            key={c.assessment_id || c.index}
            cx={c.x}
            cy={c.y}
            r="4.5"
            fill="var(--emp-report-accent, #2563eb)"
          >
            <title>{`Assessment ${c.index}: ${Math.round(c.percent)}%`}</title>
          </circle>
        ))}

        <AssessmentXAxis
          n={n}
          xAt={xAt}
          width={width}
          height={height}
          padLeft={padLeft}
          padRight={padRight}
          dense={denseXLabels}
          expanded={expanded}
        />
      </svg>
      {n === 1 && (
        <p className="muted small-print emp-report-line-chart-hint">
          One assessment so far — complete more to see a trend line.
        </p>
      )}
    </div>
  );
}

function heatmapCellStyle(percent) {
  if (percent == null || Number.isNaN(percent)) {
    return { background: "rgba(0,0,0,0.04)", color: "var(--muted, #94a3b8)" };
  }
  if (percent >= 75) return { background: "rgba(34, 197, 94, 0.35)", color: "#166534" };
  if (percent >= 50) return { background: "rgba(234, 179, 8, 0.35)", color: "#854d0e" };
  return { background: "rgba(239, 68, 68, 0.3)", color: "#991b1b" };
}

function buildHeatmapModel(languages) {
  const langList = languages || [];
  const topicSet = new Set();
  const matrix = new Map();

  for (const lang of langList) {
    for (const topic of lang.topics || []) {
      topicSet.add(topic.topic_name);
      if (!matrix.has(topic.topic_name)) matrix.set(topic.topic_name, {});
      matrix.get(topic.topic_name)[lang.language_code] = topic.percent_correct;
    }
  }

  const topics = [...topicSet].sort((a, b) => a.localeCompare(b));
  return {
    columns: langList.map((lang) => ({
      code: lang.language_code,
      label: lang.language_label,
    })),
    topics,
    matrix,
  };
}

function TopicHeatmap({ languages, languageColors, expanded = false }) {
  const model = useMemo(() => buildHeatmapModel(languages), [languages]);

  if (!model.topics.length) {
    return <p className="muted small-print">No topic attempts yet.</p>;
  }

  const topicMaxLen = expanded ? 64 : 36;

  return (
    <div
      className={`emp-report-heatmap-wrap${
        expanded ? " emp-report-heatmap-wrap--expanded" : ""
      }`}
    >
      <table className="emp-report-heatmap" role="grid" aria-label="Topic performance by language">
        <thead>
          <tr>
            <th scope="col" className="emp-report-heatmap-corner">
              Topic
            </th>
            {model.columns.map((col) => (
              <th key={col.code} scope="col" className="emp-report-heatmap-col-head">
                <span
                  className="emp-report-heatmap-lang-dot"
                  style={{ background: languageColors[col.code] || "#2563eb" }}
                  aria-hidden
                />
                {col.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {model.topics.map((topic) => (
            <tr key={topic}>
              <th scope="row" className="emp-report-heatmap-row-head" title={topic}>
                {truncateTopicName(topic, topicMaxLen)}
              </th>
              {model.columns.map((col) => {
                const percent = model.matrix.get(topic)?.[col.code];
                const hasValue = percent != null && !Number.isNaN(percent);
                const label = hasValue
                  ? `${topic} · ${col.label}: ${Math.round(percent)}%`
                  : `${topic} · ${col.label}: not attempted`;
                return (
                  <td
                    key={col.code}
                    className="emp-report-heatmap-cell"
                    style={heatmapCellStyle(hasValue ? percent : null)}
                    title={label}
                  >
                    {hasValue ? `${Math.round(percent)}%` : "—"}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
      <p className="muted small-print emp-report-heatmap-legend">
        Green ≥75% · Amber 50–74% · Red &lt;50% · Gray = not attempted
      </p>
    </div>
  );
}

function CumulativeStackedChart({ points, expanded = false }) {
  if (!points?.length) {
    return <p className="muted small-print">No cumulative progress yet.</p>;
  }

  const { width, height, padLeft, padRight, padTop, padBottom } = lineChartLayout(expanded);
  const chartW = width - padLeft - padRight;
  const chartH = height - padTop - padBottom;
  const n = points.length;

  const totals = points.map(
    (p) =>
      Math.max(0, Number(p.cumulative_correct) || 0) +
      Math.max(0, Number(p.cumulative_wrong) || 0)
  );
  const maxTotal = Math.max(...totals, 1);
  const yMax = Math.ceil(maxTotal / 5) * 5 || 5;
  const yTicks = Array.from({ length: 5 }, (_, i) => Math.round((yMax / 4) * i));

  const xAt = (i) =>
    padLeft + (n === 1 ? chartW / 2 : (i / Math.max(n - 1, 1)) * chartW);
  const yAt = (value) => padTop + chartH - (value / yMax) * chartH;

  const correctCoords = points.map((p, i) => ({
    x: xAt(i),
    y: yAt(Math.max(0, Number(p.cumulative_correct) || 0)),
    total: totals[i],
  }));
  const totalCoords = points.map((p, i) => ({
    x: xAt(i),
    y: yAt(totals[i]),
  }));

  function areaPath(topCoords, bottomY) {
    if (!topCoords.length) return "";
    const top = topCoords.map((c) => `${c.x},${c.y}`).join(" L ");
    const last = topCoords[topCoords.length - 1];
    const first = topCoords[0];
    return `M ${first.x},${bottomY} L ${top} L ${last.x},${bottomY} Z`;
  }

  const baseline = padTop + chartH;
  const wrongPath = areaPath(totalCoords, baseline);
  const correctPath = areaPath(correctCoords, baseline);
  const denseXLabels = n > (expanded ? 14 : 8);
  const axisFont = chartTextSize(expanded, width, 11);
  const yTitleFont = chartTextSize(expanded, width, 9);

  return (
    <div
      className={`emp-report-line-chart-wrap${
        expanded ? " emp-report-line-chart-wrap--expanded" : ""
      }`}
    >
      <p className="muted small-print emp-report-chart-lead">
        How many questions you have answered correctly vs incorrectly over your full history.
      </p>
      <svg
        viewBox={`0 0 ${width} ${height}`}
        className="emp-report-line-chart"
        role="img"
        aria-label="Cumulative correct and wrong answers over assessments"
      >
        <text
          x={10}
          y={padTop + chartH / 2}
          textAnchor="middle"
          fontSize={yTitleFont}
          className="emp-report-chart-axis-title emp-report-chart-axis-title--y"
          transform={`rotate(-90, 10, ${padTop + chartH / 2})`}
        >
          Questions
        </text>

        {yTicks.map((tick) => {
          const y = yAt(tick);
          return (
            <g key={tick}>
              <line
                x1={padLeft}
                y1={y}
                x2={width - padRight}
                y2={y}
                className="emp-report-line-chart-grid"
              />
              <text
                x={padLeft - 8}
                y={y + 4}
                textAnchor="end"
                fontSize={axisFont}
                className="emp-report-line-chart-axis"
              >
                {tick}
              </text>
            </g>
          );
        })}

        <line
          x1={padLeft}
          y1={padTop}
          x2={padLeft}
          y2={baseline}
          className="emp-report-line-chart-axis-line"
        />
        <line
          x1={padLeft}
          y1={baseline}
          x2={width - padRight}
          y2={baseline}
          className="emp-report-line-chart-axis-line"
        />

        <path d={wrongPath} fill="rgba(239, 68, 68, 0.45)" />
        <path d={correctPath} fill="rgba(34, 197, 94, 0.55)" />

        <AssessmentXAxis
          n={n}
          xAt={xAt}
          width={width}
          height={height}
          padLeft={padLeft}
          padRight={padRight}
          dense={denseXLabels}
          expanded={expanded}
        />
      </svg>
      <p className="muted small-print emp-report-chart-caption">
        Running total of individual questions marked correct (green) or incorrect (red)
        after each completed assessment — not a score percentage.
      </p>
      <p className="emp-report-chart-insight">
        So the chart answers: &ldquo;Across my whole history, how much knowledge have I demonstrated
        correctly vs where I&apos;m still getting things wrong?&rdquo;
      </p>
      <ul className="emp-report-stacked-legend">
        <li>
          <span className="emp-report-legend-swatch" style={{ background: "rgba(34, 197, 94, 0.75)" }} />
          Cumulative correct
        </li>
        <li>
          <span className="emp-report-legend-swatch" style={{ background: "rgba(239, 68, 68, 0.65)" }} />
          Cumulative wrong
        </li>
      </ul>
    </div>
  );
}

function RadarChart({ topics, expanded = false }) {
  if (!topics?.length) {
    return <p className="muted small-print">Not enough topic data for radar chart.</p>;
  }

  const items = topics.slice(0, 8).map((t, i) => ({
    ...t,
    symbol: topicRadarSymbol(i),
  }));
  const n = items.length;
  const cx = expanded ? 200 : 120;
  const cy = expanded ? 188 : 112;
  const maxR = expanded ? 128 : 72;
  const viewW = expanded ? 400 : 240;
  const viewH = expanded ? 360 : 220;
  const levels = [25, 50, 75, 100];

  function polar(i, value) {
    const angle = (Math.PI * 2 * i) / n - Math.PI / 2;
    const r = (Math.min(100, Math.max(0, value)) / 100) * maxR;
    return { x: cx + r * Math.cos(angle), y: cy + r * Math.sin(angle) };
  }

  function polygon(values) {
    return values.map((v, i) => {
      const p = polar(i, v);
      return `${i === 0 ? "M" : "L"} ${p.x},${p.y}`;
    }).join(" ") + " Z";
  }

  const latestValues = items.map((t) => Number(t.latest_percent) || 0);
  const rollingValues = items.map((t) => Number(t.rolling_avg_percent) || 0);

  return (
    <div className={`emp-report-radar-wrap${expanded ? " emp-report-radar-wrap--expanded" : ""}`}>
      <svg
        viewBox={`0 0 ${viewW} ${viewH}`}
        className="emp-report-radar"
        role="img"
        aria-label="Topic radar chart"
      >
        {levels.map((level) => (
          <polygon
            key={level}
            points={items
              .map((_, i) => {
                const p = polar(i, level);
                return `${p.x},${p.y}`;
              })
              .join(" ")}
            fill="none"
            stroke="rgba(0,0,0,0.08)"
            strokeWidth="1"
          />
        ))}

        {items.map((t, i) => {
          const outer = polar(i, 100);
          const label = polar(i, 92);
          return (
            <g key={t.topic_name}>
              <line
                x1={cx}
                y1={cy}
                x2={outer.x}
                y2={outer.y}
                stroke="rgba(0,0,0,0.1)"
                strokeWidth="1"
              />
              <circle
                cx={label.x}
                cy={label.y}
                r="9"
                className="emp-report-radar-symbol-bg"
              />
              <text
                x={label.x}
                y={label.y + 3.5}
                textAnchor="middle"
                className="emp-report-radar-symbol"
              >
                {t.symbol}
              </text>
            </g>
          );
        })}

        <path
          d={polygon(rollingValues)}
          fill="rgba(124, 58, 237, 0.15)"
          stroke="#7c3aed"
          strokeWidth="2"
        />
        <path
          d={polygon(latestValues)}
          fill="rgba(37, 99, 235, 0.18)"
          stroke="var(--emp-report-accent, #2563eb)"
          strokeWidth="2"
        />

        <text x={cx} y={8} textAnchor="middle" className="emp-report-radar-scale-label">
          100%
        </text>
      </svg>

      <div className="emp-report-radar-aside">
        <p className="emp-report-radar-key-heading">Topic key</p>
        <ul className="emp-report-radar-key">
          {items.map((t) => (
            <li key={t.topic_name} className="emp-report-radar-key-row">
              <span className="emp-report-radar-key-letter" aria-hidden>
                {t.symbol}
              </span>
              <div className="emp-report-radar-key-body">
                <span className="emp-report-radar-key-topic">{t.topic_name}</span>
                <span className="muted small-print emp-report-radar-key-stats">
                  Latest {Math.round(t.latest_percent)}% · 3-assessment avg{" "}
                  {Math.round(t.rolling_avg_percent)}%
                </span>
              </div>
            </li>
          ))}
        </ul>
        <ul className="emp-report-stacked-legend emp-report-radar-series-legend">
          <li>
            <span className="emp-report-legend-swatch" style={{ background: "#2563eb" }} />
            Latest assessment
          </li>
          <li>
            <span className="emp-report-legend-swatch" style={{ background: "#7c3aed" }} />
            Last 3 assessments avg
          </li>
        </ul>
      </div>
    </div>
  );
}

function TypeDonut({ breakdown, expanded = false }) {
  const entries = Object.entries(breakdown || {});
  if (!entries.length) {
    return <p className="muted small-print">No question-type data.</p>;
  }
  const total = entries.reduce((n, [, v]) => n + (v.count || 0), 0) || 1;
  const colors = { mcq: "#2563eb", coding: "#7c3aed", subjective: "#059669" };
  let angle = 0;
  const slices = entries.map(([type, data]) => {
    const frac = (data.count || 0) / total;
    const start = angle;
    angle += frac * 360;
    return { type, data, start, end: angle, color: colors[type] || "#64748b" };
  });
  const r = 40;
  const cx = 50;
  const cy = 50;
  const innerR = 22;
  const svgSize = expanded ? 168 : 140;
  const centerFont = expanded ? 12 : 11;
  function arc(startDeg, endDeg) {
    const s = (startDeg - 90) * (Math.PI / 180);
    const e = (endDeg - 90) * (Math.PI / 180);
    const x1 = cx + r * Math.cos(s);
    const y1 = cy + r * Math.sin(s);
    const x2 = cx + r * Math.cos(e);
    const y2 = cy + r * Math.sin(e);
    const large = endDeg - startDeg > 180 ? 1 : 0;
    return `M ${cx} ${cy} L ${x1} ${y1} A ${r} ${r} 0 ${large} 1 ${x2} ${y2} Z`;
  }
  return (
    <div className={`emp-report-donut-wrap${expanded ? " emp-report-donut-wrap--expanded" : ""}`}>
      <svg
        viewBox="0 0 100 100"
        width={svgSize}
        height={svgSize}
        className="emp-report-donut-chart"
        role="img"
      >
        {slices.map((sl) => (
          <path key={sl.type} d={arc(sl.start, sl.end)} fill={sl.color} opacity="0.9">
            <title>{`${sl.type}: ${sl.data.count} questions`}</title>
          </path>
        ))}
        <circle cx={cx} cy={cy} r={innerR} fill="var(--card-bg, #fff)" />
        <text
          x={cx}
          y={cy + 4}
          textAnchor="middle"
          fontSize={centerFont}
          fontWeight="600"
        >
          {total}
        </text>
      </svg>
      <ul className="emp-report-donut-legend">
        {slices.map((sl) => (
          <li key={sl.type}>
            <span className="emp-report-legend-swatch" style={{ background: sl.color }} />
            {sl.type.toUpperCase()} — {sl.data.count} ({Math.round(sl.data.percent_correct)}%)
          </li>
        ))}
      </ul>
    </div>
  );
}

export default function EmployeeReportPage({ mode = "client" }) {
  const { employeeId: routeEmployeeId } = useParams();
  const [searchParams, setSearchParams] = useSearchParams();
  const initialEmployee =
    routeEmployeeId?.trim() ||
    searchParams.get("employee_id")?.trim() ||
    "";
  const initialPeriod = searchParams.get("period") || "all_time";

  const [employeeIdInput, setEmployeeIdInput] = useState(initialEmployee);
  const [period, setPeriod] = useState(initialPeriod);
  const [report, setReport] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [expandedChartId, setExpandedChartId] = useState(null);

  useEffect(() => {
    if (routeEmployeeId?.trim()) {
      setEmployeeIdInput(routeEmployeeId.trim());
    }
  }, [routeEmployeeId]);

  const authRole = mode === "admin" ? "admin" : undefined;

  const loadReport = useCallback(async () => {
    const eid = employeeIdInput.trim();
    if (!eid) {
      setError("Employee ID is required.");
      setReport(null);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const data = await fetchEmployeeReport({
        employeeId: eid,
        period,
        authRole,
      });
      setReport(data);
      if (mode === "client") {
        setSearchParams({ employee_id: eid, period }, { replace: true });
      }
    } catch (e) {
      setReport(null);
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [employeeIdInput, period, authRole, mode, setSearchParams]);

  useEffect(() => {
    if (initialEmployee) {
      loadReport();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const hasData = (report?.summary?.assessments_completed ?? 0) > 0;

  const languageColors = useMemo(() => {
    const palette = ["#2563eb", "#7c3aed", "#059669", "#d97706", "#dc2626"];
    const map = {};
    (report?.languages || []).forEach((lang, i) => {
      map[lang.language_code] = palette[i % palette.length];
    });
    return map;
  }, [report?.languages]);

  function handlePrint() {
    window.print();
  }

  return (
    <div className={`page emp-report-page emp-report-page--${mode}`}>
      <header className="emp-report-header no-print">
        <div>
          <p className="page-eyebrow">Stage 4 — Skills analytics</p>
          <h1>{report?.title || "Skills Progress Report"}</h1>
          {mode === "admin" ? (
            <p className="muted">
              <Link to="/admin/submissions">← Submissions</Link>
            </p>
          ) : (
            <p className="muted">
              <Link to="/client">← Take test</Link>
              {employeeIdInput.trim() && (
                <>
                  {" · "}
                  <Link
                    to={`/client/improve?employee_id=${encodeURIComponent(employeeIdInput.trim())}`}
                  >
                    Help me improve →
                  </Link>
                </>
              )}
            </p>
          )}
        </div>
        <div className="emp-report-controls">
          <label>
            Employee ID
            <input
              value={employeeIdInput}
              onChange={(e) => setEmployeeIdInput(e.target.value)}
              placeholder="e.g. E1001"
            />
          </label>
          <label>
            Period
            <select value={period} onChange={(e) => setPeriod(e.target.value)}>
              <option value="all_time">All time</option>
              <option value="last_90_days">Last 90 days</option>
            </select>
          </label>
          <button type="button" className="primary" onClick={loadReport} disabled={loading}>
            {loading ? "Loading…" : "Load report"}
          </button>
          {hasData && (
            <button type="button" className="secondary" onClick={handlePrint}>
              Download PDF / Print
            </button>
          )}
        </div>
      </header>

      {error && (
        <div className="error no-print" role="alert">
          {error}
        </div>
      )}

      {report && !hasData && (
        <div className="card emp-report-empty">
          <h2>No submissions yet</h2>
          <p className="muted">
            Complete your first assessment to see progress, topic breakdowns, and charts here.
          </p>
        </div>
      )}

      {report && hasData && (
        <article className="emp-report-document">
          <section className="emp-report-hero card">
            <div className="emp-report-hero-main">
              <h2 className="emp-report-hero-title">
                {report.display_name || report.employee_id}
              </h2>
              <p className="muted emp-report-meta">
                <span>ID: {report.employee_id}</span>
                <span>Generated {formatDate(report.report_generated_at)}</span>
                <span>Period: {period === "last_90_days" ? "Last 90 days" : "All time"}</span>
              </p>
              <div className="emp-report-hero-stats">
                <div>
                  <strong>{report.summary.assessments_completed}</strong>
                  <span className="muted">Assessments</span>
                </div>
                <div>
                  <strong>{report.summary.questions_answered}</strong>
                  <span className="muted">Questions</span>
                </div>
                <div>
                  <strong>{formatDuration(report.summary.total_time_seconds)}</strong>
                  <span className="muted">Time on platform*</span>
                </div>
                <div>
                  <strong>{formatDuration(report.summary.avg_assessment_time_seconds)}</strong>
                  <span className="muted">Avg / assessment*</span>
                </div>
              </div>
              <p className="muted small-print emp-report-time-note">
                * Time on platform reflects timed assessments only.
              </p>
              <p className="emp-report-proficiency">
                Progress at <strong>{report.summary.assessed_level_label || "Beginner"}</strong>{" "}
                level: <strong>{report.summary.proficiency_label}</strong>
              </p>
            </div>
            <ScoreRing
              percent={report.summary.overall_percent_correct}
              label="Score"
            />
          </section>

          <section className="emp-report-grid card">
            <div className="emp-report-grid-col">
              <h3>Languages evaluated</h3>
              <div className="emp-report-lang-cards">
                {(report.languages || []).map((lang) => (
                  <div
                    key={lang.language_code}
                    className="emp-report-lang-card"
                    style={{
                      borderLeftColor: languageColors[lang.language_code] || "#2563eb",
                    }}
                  >
                    <strong>{lang.language_label}</strong>
                    <span>
                      {lang.topics_covered}/{lang.topics_in_catalog || "—"} topics
                    </span>
                    <span>{lang.questions_count} questions</span>
                    <span>
                      {Math.round(lang.percent_correct)}% · {lang.assessed_level_label || "Beginner"} ·{" "}
                      {lang.proficiency_label}
                    </span>
                  </div>
                ))}
              </div>
              <div className="emp-report-mastery-inline">
                <h3>Mastery</h3>
                <p>
                  <strong>{report.mastery.mastered_count}</strong> questions mastered
                </p>
                <p>
                  <strong>{report.mastery.needs_practice_count}</strong> need more practice
                  (wrong 2+ times)
                </p>
              </div>
            </div>
            <div className="emp-report-grid-heatmap-col">
              <ExpandableChartBlock
                id="topic-heatmap"
                title="Topic heatmap"
                expandedId={expandedChartId}
                onExpand={setExpandedChartId}
                className="emp-report-chart-block--in-grid"
                renderChart={(expanded) => (
                  <TopicHeatmap
                    languages={report.languages}
                    languageColors={languageColors}
                    expanded={expanded}
                  />
                )}
              />
            </div>
          </section>

          <section className="emp-report-charts card">
            <ExpandableChartBlock
              id="score-trend"
              title="Score trend"
              expandedId={expandedChartId}
              onExpand={setExpandedChartId}
              renderChart={(expanded) => (
                <LineChart points={report.score_timeline} expanded={expanded} />
              )}
            />
            <ExpandableChartBlock
              id="question-types"
              title="Question types"
              expandedId={expandedChartId}
              onExpand={setExpandedChartId}
              renderChart={(expanded) => (
                <TypeDonut breakdown={report.question_type_breakdown} expanded={expanded} />
              )}
            />
            <ExpandableChartBlock
              id="cumulative-progress"
              title="Cumulative progress"
              expandedId={expandedChartId}
              onExpand={setExpandedChartId}
              renderChart={(expanded) => (
                <CumulativeStackedChart points={report.cumulative_progress} expanded={expanded} />
              )}
            />
            <ExpandableChartBlock
              id="topic-radar"
              title="Topic radar"
              expandedId={expandedChartId}
              onExpand={setExpandedChartId}
              renderChart={(expanded) => (
                <RadarChart topics={report.radar_topics} expanded={expanded} />
              )}
            />
          </section>

          {(report.languages || []).map((lang) => (
            <section key={lang.language_code} className="card emp-report-topics">
              <h3>
                {lang.language_label} — topics covered
              </h3>
              <div className="table-wrap">
                <table className="data-table emp-report-topic-table">
                  <thead>
                    <tr>
                      <th>Topic</th>
                      <th>Questions</th>
                      <th>Mastered</th>
                      <th>% correct</th>
                      <th>Level</th>
                      <th>Trend</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(lang.topics || []).map((topic) => (
                      <tr key={topic.topic_name}>
                        <td>
                          <span className={topicChipClass(topic.percent_correct)}>
                            {topic.topic_name}
                          </span>
                        </td>
                        <td>{topic.questions_count}</td>
                        <td>{topic.mastered_count}</td>
                        <td>{Math.round(topic.percent_correct)}%</td>
                        <td>{topic.last_difficulty || "—"}</td>
                        <td aria-label={`Trend ${topic.trend || "none"}`}>
                          {trendGlyph(topic.trend)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          ))}

          <section className="card emp-report-insights">
            <h3>Strengths & focus areas</h3>
            <div className="emp-report-insights-grid">
              <div>
                <h4>Strengths</h4>
                {(report.insights.strengths || []).length ? (
                  <ul>
                    {report.insights.strengths.map((t) => (
                      <li key={t}>{t}</li>
                    ))}
                  </ul>
                ) : (
                  <p className="muted small-print">No standout strengths yet (need ≥80% on 5+ questions).</p>
                )}
              </div>
              <div>
                <h4>Focus areas (last 3 assessments)</h4>
                {(report.insights.focus_areas || []).length ? (
                  <ul>
                    {report.insights.focus_areas.map((t) => (
                      <li key={t}>{t}</li>
                    ))}
                  </ul>
                ) : (
                  <p className="muted small-print">No weak topics below 70% in recent assessments.</p>
                )}
              </div>
            </div>
            <div className="emp-report-unexplored">
              <h4>Unexplored topics (your languages)</h4>
              {(report.insights.unexplored_topics || []).length ? (
                groupTopicsByTier(report.insights.unexplored_topics).map(([tier, names]) => (
                  <div key={tier} className="emp-report-unexplored-tier">
                    <h5 className="emp-report-unexplored-tier-label">{tier}</h5>
                    <ul className="emp-report-unexplored-list">
                      {names.map((t) => (
                        <li key={t}>
                          <span className="emp-report-unexplored-chip" title={t}>
                            {truncateTopicName(t)}
                          </span>
                        </li>
                      ))}
                    </ul>
                  </div>
                ))
              ) : (
                <p className="muted small-print">
                  All catalog topics covered for languages you have been assessed in.
                </p>
              )}
            </div>
            {(report.insights.recommendations || []).length > 0 && (
              <div className="emp-report-recommendations">
                <h4>Recommendations</h4>
                <ul>
                  {report.insights.recommendations.map((r) => (
                    <li key={r}>{r}</li>
                  ))}
                </ul>
              </div>
            )}
          </section>

          <footer className="emp-report-footer muted small-print">
            <p>
              Scores reflect platform assessments only. Use Help me improve for targeted practice.
            </p>
            <p>Report version {report.report_version}</p>
          </footer>
        </article>
      )}
    </div>
  );
}
