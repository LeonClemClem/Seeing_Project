import { useMemo } from "react";

import type { ForecastPoint } from "../api";
import { SEEING_BANDS } from "../config";
import { r0cm, seeingBand, type BestWindow, type Interval } from "../lib/seeing";
import { formatDayHour, type TimeZone } from "../lib/time";
import { chartTheme as T, timeAxis, toAxis } from "./chartTheme";
import EChart from "./EChart";

interface Props {
  points: ForecastPoint[];
  nights: Interval[];
  now: number;
  tz: TimeZone;
  best: BestWindow | null;
  compact: boolean;
}

export default function SeeingChart({ points, nights, now, tz, best, compact }: Props) {
  const option = useMemo(() => {
    const x = (t: number) => toAxis(t, tz);
    const byX = new Map(points.map((p) => [x(Date.parse(p.valid_time)), p]));
    const data = [...byX.entries()].map(([xv, p]) => [xv, p.seeing_arcsec]);
    const values = points.map((p) => p.seeing_arcsec).filter((v): v is number => v != null);
    const yMax = Math.max(3, Math.ceil((Math.max(0, ...values) + 0.25) * 2) / 2);
    const x0 = (data[0]?.[0] as number | undefined) ?? x(now);
    const x1 = (data[data.length - 1]?.[0] as number | undefined) ?? x(now);
    const xNow = x(now);

    let lo = 0;
    const bands = SEEING_BANDS.filter((_b, i) => (i === 0 ? 0 : SEEING_BANDS[i - 1]!.max) < yMax).map((b) => {
      const area = [{ yAxis: lo, itemStyle: { color: b.color, opacity: 0.045 } }, { yAxis: Math.min(b.max, yMax) }];
      lo = b.max;
      return area;
    });

    return {
      backgroundColor: "transparent",
      animation: false,
      grid: { left: 44, right: 16, top: 26, bottom: 30 },
      textStyle: { color: T.text, fontFamily: T.font },
      tooltip: {
        trigger: "axis",
        backgroundColor: T.tooltipBg,
        borderColor: T.grid,
        textStyle: { color: T.textStrong },
        axisPointer: { type: "line", lineStyle: { color: T.axis } },
        formatter: (params: { value: [number, number | null] }[]) => {
          const xv = params[0]?.value[0];
          const p = xv != null ? byX.get(xv) : undefined;
          if (!p) return "";
          const v = p.seeing_arcsec;
          const band = seeingBand(v);
          const r0 = r0cm(p.r0_m);
          return [
            `<b>${formatDayHour(p.valid_time, tz)}</b>`,
            `Seeing: <b>${v != null ? v.toFixed(2) + "″" : "no data"}</b> ${band ? `<span style="color:${band.color}">●</span> ${band.label}` : ""}`,
            `r0: ${r0 != null ? r0.toFixed(1) + " cm" : "–"}`,
            `Boundary layer: ${p.h_coulim_m != null ? Math.round(p.h_coulim_m) + " m" : "–"}`,
          ].join("<br/>");
        },
      },
      xAxis: timeAxis(x0, x1, compact ? 12 : 3),
      yAxis: {
        type: "value",
        min: 0,
        max: yMax,
        interval: 0.5,
        axisLabel: { color: T.text, formatter: (v: number) => `${v}″` },
        splitLine: { lineStyle: { color: T.grid } },
      },
      visualMap: {
        show: false,
        seriesIndex: 0,
        dimension: 1,
        pieces: SEEING_BANDS.map((b, i) => ({
          gte: i === 0 ? 0 : SEEING_BANDS[i - 1]!.max,
          lt: Number.isFinite(b.max) ? b.max : 1e9,
          color: b.color,
        })),
      },
      series: [
        {
          name: "Seeing",
          type: "line",
          data,
          showSymbol: false,
          symbolSize: 8,
          connectNulls: false,
          lineStyle: { width: 2.5 },
          z: 5,
          markLine: {
            silent: true,
            symbol: "none",
            label: { formatter: "now", color: T.now, position: "end" },
            lineStyle: { color: T.now, type: "dashed", width: 1.5 },
            data: xNow >= x0 && xNow <= x1 ? [{ xAxis: xNow }] : [],
          },
          markArea: best
            ? {
                silent: true,
                label: { show: true, position: "insideTop", color: T.textStrong, formatter: "best", fontSize: 11 },
                itemStyle: {
                  color: "rgba(255,255,255,0.05)",
                  borderColor: "rgba(255,255,255,0.5)",
                  borderWidth: 1,
                  borderType: "dashed",
                },
                data: [[{ xAxis: x(best.start) }, { xAxis: Math.min(x(best.end), x1) }]],
              }
            : undefined,
        },
        {
          name: "night",
          type: "line",
          data: [],
          markArea: {
            silent: true,
            itemStyle: { color: T.night },
            label: { show: !compact, position: "insideBottom", color: T.text, fontSize: 10, formatter: "night" },
            data: nights.map((n) => [{ xAxis: Math.max(x(n.start), x0) }, { xAxis: Math.min(x(n.end), x1) }]),
          },
        },
        { name: "bands", type: "line", data: [], markArea: { silent: true, data: bands } },
      ],
    };
  }, [points, nights, now, tz, best, compact]);

  return (
    <EChart
      option={option}
      height={compact ? 260 : 320}
      ariaLabel="Seeing forecast line chart; the hourly values are also listed in the table below"
    />
  );
}
