import { useMemo } from "react";

import type { Cn2, ForecastPoint } from "../api";
import { CN2_COLORS, CN2_LOG_MAX, CN2_LOG_MIN, CN2_LOW_MAX_HEIGHT_M } from "../config";
import { cn2Cells } from "../lib/cn2";
import { formatDay, formatDayHour, formatHour, hourIn, type TimeZone } from "../lib/time";
import { chartTheme as T } from "./chartTheme";
import EChart from "./EChart";

interface Props {
  cn2: Cn2;
  points: ForecastPoint[];
  full: boolean;
  now: number;
  tz: TimeZone;
  compact: boolean;
}

const SUPERSCRIPT: Record<string, string> = { "-": "⁻", "0": "⁰", "1": "¹", "2": "²", "3": "³", "4": "⁴", "5": "⁵", "6": "⁶", "7": "⁷", "8": "⁸", "9": "⁹" };
const pow10 = (e: number) => `10${String(Math.round(e)).replace(/./g, (c) => SUPERSCRIPT[c] ?? c)}`;

export default function Cn2Heatmap({ cn2, points, full, now, tz, compact }: Props) {
  const option = useMemo(() => {
    const maxH = full ? Infinity : CN2_LOW_MAX_HEIGHT_M;
    const { times, heights, cells } = cn2Cells(cn2, maxH);
    const step = compact ? 12 : 3;
    const nowIdx = times.findIndex((t) => t > now) - 1;

    // Boundary-layer height overlaid as a line, mapped onto the (category) height axis.
    const blByTime = new Map(points.map((p) => [Date.parse(p.valid_time), p.h_coulim_m]));
    const dh = heights.length > 1 ? heights[1]! - heights[0]! : 100;
    const bl = times.map((t, i) => {
      const h = blByTime.get(t);
      if (h == null || h > heights[heights.length - 1]!) return [i, null];
      return [i, (h - heights[0]!) / dh];
    });

    return {
      backgroundColor: "transparent",
      animation: false,
      textStyle: { color: T.text, fontFamily: T.font },
      grid: { left: 54, right: 16, top: 40, bottom: 30 },
      tooltip: {
        backgroundColor: T.tooltipBg,
        borderColor: T.grid,
        textStyle: { color: T.textStrong },
        formatter: (p: { seriesType: string; value: [number, number, number] }) => {
          if (p.seriesType !== "heatmap") return "";
          const [xi, yi, lv] = p.value;
          return `<b>${formatDayHour(times[xi]!, tz)}</b><br/>${heights[yi]} m AGL<br/>Cn² = ${Math.pow(10, lv).toExponential(1)} m⁻²ᐟ³`;
        },
      },
      xAxis: {
        type: "category",
        data: times.map(String),
        axisLine: { lineStyle: { color: T.axis } },
        axisTick: { alignWithLabel: true, interval: (i: number) => hourIn(times[i]!, tz) % step === 0 },
        axisLabel: {
          color: T.text,
          interval: (i: number) => hourIn(times[i]!, tz) % step === 0,
          formatter: (v: string) => {
            const t = Number(v);
            return hourIn(t, tz) === 0 ? `{day|${formatDay(t, tz)}}` : formatHour(t, tz);
          },
          rich: { day: { color: T.textStrong, fontWeight: "bold" } },
        },
      },
      yAxis: {
        type: "category",
        data: heights.map(String),
        name: "m AGL",
        nameTextStyle: { color: T.text, align: "right" },
        axisLine: { lineStyle: { color: T.axis } },
        axisLabel: {
          color: T.text,
          interval: (i: number) => heights[i]! % (full ? 2000 : 500) === 0,
          formatter: (v: string) => (Number(v) >= 1000 ? `${Number(v) / 1000} km` : `${v} m`),
        },
        axisTick: { show: false },
      },
      visualMap: {
        type: "continuous",
        min: CN2_LOG_MIN,
        max: CN2_LOG_MAX,
        seriesIndex: 0,
        dimension: 2,
        calculable: false,
        orient: "horizontal",
        right: 16,
        top: 0,
        itemHeight: compact ? 120 : 180,
        itemWidth: 10,
        text: [pow10(CN2_LOG_MAX), pow10(CN2_LOG_MIN)],
        textStyle: { color: T.text, fontSize: 11 },
        inRange: { color: CN2_COLORS },
      },
      series: [
        {
          type: "heatmap",
          data: cells,
          progressive: 0,
          emphasis: { disabled: true },
          markLine:
            nowIdx >= 0
              ? {
                  silent: true,
                  symbol: "none",
                  label: { show: false },
                  lineStyle: { color: T.now, type: "dashed", width: 1.5 },
                  data: [{ xAxis: nowIdx }],
                }
              : undefined,
        },
        {
          type: "line",
          name: "Boundary layer",
          data: bl,
          showSymbol: false,
          connectNulls: false,
          lineStyle: { color: "rgba(255,255,255,0.75)", width: 1.5, type: "dashed" },
          z: 10,
          silent: true,
          tooltip: { show: false },
        },
      ],
    };
  }, [cn2, points, full, now, tz, compact]);

  return (
    <EChart
      option={option}
      height={compact ? 300 : 360}
      ariaLabel="Cn2 turbulence profile heatmap over time and height; brighter means more turbulence"
    />
  );
}
