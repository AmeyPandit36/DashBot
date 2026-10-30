import type { WidgetData } from "./types";

const BRAND = ["#4F6BFF", "#8B5CF6", "#06B6D4", "#14B8A6", "#D946EF", "#F59E0B", "#F43F5E", "#6366F1"];
const SEQUENTIAL = ["#EEF1FF", "#C7D0FF", "#95A5FF", "#6B80FF", "#4F6BFF", "#3D57E8", "#2F45C7"];
const DIVERGING = ["#F43F5E", "#FB923C", "#FDE68A", "#A7F3D0", "#34D399", "#10B981"];

function paletteFor(name?: string) {
  if (name === "sequential") return SEQUENTIAL;
  if (name === "diverging") return DIVERGING;
  return BRAND;
}

const isNumeric = (value: unknown) => typeof value === "number" || (typeof value === "string" && value.trim() !== "" && !Number.isNaN(Number(value)));

function fmtAxisLabel(value: unknown, column: string) {
  if (typeof value === "number") {
    return new Intl.NumberFormat("en-US", { notation: Math.abs(value) >= 10000 ? "compact" : "standard", maximumFractionDigits: 1 }).format(value);
  }
  const text = String(value ?? "");
  if (/^\d{4}-\d{2}-\d{2}/.test(text)) {
    const date = new Date(text);
    if (!Number.isNaN(date.getTime())) {
      return new Intl.DateTimeFormat("en-US", { month: "short", year: "2-digit" }).format(date);
    }
  }
  return text.length > 18 ? `${text.slice(0, 17)}…` : text;
}

export function buildChartOption(
  data: WidgetData,
  theme: "light" | "dark",
): Record<string, unknown> {
  const { columns, rows } = data;
  const encoding = data.encoding as Record<string, string | string[]>;
  const dark = theme === "dark";
  const axisText = dark ? "#9AA3C2" : "#545C7A";
  const splitLine = dark ? "rgba(255,255,255,0.07)" : "rgba(21,27,50,0.07)";
  const palette = paletteFor(data.options?.palette);

  const base: Record<string, unknown> = {
    animationDuration: 600,
    animationEasing: "cubicOut",
    color: palette,
    textStyle: { fontFamily: "InterVariable, Inter, system-ui, sans-serif", color: axisText },
    grid: { left: 8, right: 14, top: 26, bottom: 4, containLabel: true },
    tooltip: {
      trigger: "axis",
      backgroundColor: dark ? "rgba(17,23,43,0.96)" : "rgba(255,255,255,0.97)",
      borderColor: dark ? "rgba(255,255,255,0.12)" : "rgba(21,27,50,0.08)",
      borderWidth: 1,
      padding: [8, 12],
      textStyle: { color: dark ? "#ECF0FF" : "#151B32", fontSize: 12 },
      axisPointer: { type: "line", lineStyle: { color: dark ? "rgba(255,255,255,0.2)" : "rgba(21,27,50,0.2)" } },
    },
  };

  const axisCommon = {
    axisLine: { lineStyle: { color: splitLine } },
    axisTick: { show: false },
    axisLabel: { color: axisText, fontSize: 11 },
    splitLine: { lineStyle: { color: splitLine, type: "dashed" as const } },
  };

  switch (data.type) {
    case "line_chart":
    case "area_chart": {
      const xField = String(encoding.x);
      const yFields = (Array.isArray(encoding.y) ? encoding.y : [encoding.y]).map(String).filter((c) => columns.includes(c));
      const xIndex = columns.indexOf(xField);
      const categories = rows.map((row) => fmtAxisLabel(row[xIndex], xField));
      const series = yFields.map((field, idx) => ({
        name: field.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase()),
        type: "line",
        smooth: 0.35,
        showSymbol: rows.length <= 16,
        symbolSize: 6,
        lineStyle: { width: 2.4, color: palette[idx % palette.length] },
        itemStyle: { color: palette[idx % palette.length] },
        areaStyle:
          data.type === "area_chart"
            ? {
                opacity: 0.9,
                color: {
                  type: "linear",
                  x: 0, y: 0, x2: 0, y2: 1,
                  colorStops: [
                    { offset: 0, color: `${palette[idx % palette.length]}55` },
                    { offset: 1, color: `${palette[idx % palette.length]}05` },
                  ],
                },
              }
            : undefined,
        emphasis: { focus: "series" },
        data: rows.map((row) => {
          const value = row[columns.indexOf(field)];
          return typeof value === "number" ? value : Number(value);
        }),
      }));
      return {
        ...base,
        xAxis: { type: "category", data: categories, boundaryGap: false, ...axisCommon, splitLine: { show: false } },
        yAxis: { type: "value", ...axisCommon, axisLine: { show: false } },
        series,
      };
    }

    case "bar_chart": {
      const xField = String(encoding.x);
      const yFields = (Array.isArray(encoding.y) ? encoding.y : [encoding.y]).map(String).filter((c) => columns.includes(c));
      const xIdx = columns.indexOf(xField);
      const xValues = rows.map((row) => row[xIdx]);
      const horizontal = xValues.every((value) => isNumeric(value)) && yFields.length === 1 && rows.every((row) => typeof row[columns.indexOf(yFields[0])] === "string");
      const categoryField = horizontal ? yFields[0] : xField;
      const valueFields = horizontal ? [xField] : yFields;
      const catIdx = columns.indexOf(categoryField);
      const categories = rows.map((row) => fmtAxisLabel(row[catIdx], categoryField));
      const series = valueFields.map((field, idx) => ({
        name: field.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase()),
        type: "bar",
        barMaxWidth: 34,
        itemStyle: {
          borderRadius: horizontal ? [0, 6, 6, 0] : [6, 6, 0, 0],
          color: {
            type: "linear",
            x: 0, y: 0, x2: horizontal ? 1 : 0, y2: horizontal ? 0 : 1,
            colorStops: [
              { offset: 0, color: palette[idx % palette.length] },
              { offset: 1, color: `${palette[idx % palette.length]}A8` },
            ],
          },
        },
        emphasis: { itemStyle: { color: palette[idx % palette.length] } },
        data: rows.map((row) => {
          const value = row[columns.indexOf(field)];
          return typeof value === "number" ? value : Number(value);
        }),
      }));
      return {
        ...base,
        xAxis: horizontal
          ? { type: "value", ...axisCommon, axisLine: { show: false } }
          : { type: "category", data: categories, ...axisCommon, splitLine: { show: false } },
        yAxis: horizontal
          ? { type: "category", data: categories, inverse: true, ...axisCommon, splitLine: { show: false }, axisLabel: { color: axisText, fontSize: 11, width: 130, overflow: "truncate" } }
          : { type: "value", ...axisCommon, axisLine: { show: false } },
        series,
        tooltip: { ...base.tooltip as object, trigger: "axis", axisPointer: { type: "shadow" } },
      };
    }

    case "pie_chart":
    case "donut_chart": {
      const labelField = String(encoding.label);
      const valueField = String(encoding.value);
      const labelIdx = columns.indexOf(labelField);
      const valueIdx = columns.indexOf(valueField);
      return {
        ...base,
        tooltip: { ...(base.tooltip as object), trigger: "item", formatter: "{b}: {c} ({d}%)" },
        legend: {
          bottom: 0,
          type: "scroll",
          textStyle: { color: axisText, fontSize: 11 },
          icon: "roundRect",
          itemWidth: 8,
          itemHeight: 8,
        },
        series: [
          {
            type: "pie",
            radius: data.type === "donut_chart" ? ["46%", "72%"] : ["0%", "70%"],
            center: ["50%", "44%"],
            avoidLabelOverlap: true,
            padAngle: 2,
            itemStyle: { borderRadius: 6, borderColor: dark ? "#11172B" : "#FFFFFF", borderWidth: 2 },
            label: { show: false },
            labelLine: { show: false },
            emphasis: { scale: true, scaleSize: 6 },
            data: rows.map((row) => ({
              name: String(row[labelIdx] ?? "—"),
              value: Number(row[valueIdx] ?? 0),
            })),
          },
        ],
      };
    }

    case "scatter_chart": {
      const xField = String(encoding.x);
      const yField = String(encoding.y);
      const seriesField = encoding.series ? String(encoding.series) : null;
      const groups = new Map<string, number[][]>();
      const xIdx = columns.indexOf(xField);
      const yIdx = columns.indexOf(yField);
      const sIdx = seriesField ? columns.indexOf(seriesField) : -1;
      rows.forEach((row) => {
        const key = sIdx >= 0 ? String(row[sIdx] ?? "—") : "All";
        const point = [Number(row[xIdx] ?? 0), Number(row[yIdx] ?? 0)];
        groups.set(key, [...(groups.get(key) ?? []), point]);
      });
      return {
        ...base,
        xAxis: { type: "value", ...axisCommon, name: xField, nameTextStyle: { color: axisText, fontSize: 10 } },
        yAxis: { type: "value", ...axisCommon, name: yField, nameTextStyle: { color: axisText, fontSize: 10 } },
        series: [...groups.entries()].map(([name, dataPoints], idx) => ({
          name,
          type: "scatter",
          symbolSize: 9,
          itemStyle: { color: `${palette[idx % palette.length]}CC`, borderColor: palette[idx % palette.length] },
          data: dataPoints,
        })),
        legend: { bottom: 0, textStyle: { color: axisText, fontSize: 11 }, icon: "circle", itemWidth: 8, itemHeight: 8 },
      };
    }

    case "heatmap": {
      const xField = String(encoding.x);
      const yField = String(encoding.y);
      const valueField = String(encoding.value);
      const xIdx = columns.indexOf(xField);
      const yIdx = columns.indexOf(yField);
      const vIdx = columns.indexOf(valueField);
      const xValues = [...new Set(rows.map((row) => String(row[xIdx])))];
      const yValues = [...new Set(rows.map((row) => String(row[yIdx])))];
      const points = rows.map((row) => [xValues.indexOf(String(row[xIdx])), yValues.indexOf(String(row[yIdx])), Number(row[vIdx] ?? 0)]);
      const max = Math.max(...points.map((p) => p[2]), 1);
      return {
        ...base,
        grid: { left: 8, right: 16, top: 12, bottom: 48, containLabel: true },
        tooltip: { ...(base.tooltip as object), trigger: "item", formatter: (p: any) => `${yValues[p.value[1]]} · ${xValues[p.value[0]]}<br/><b>${new Intl.NumberFormat("en-US").format(p.value[2])}</b>` },
        xAxis: { type: "category", data: xValues, ...axisCommon, splitLine: { show: false } },
        yAxis: { type: "category", data: yValues, ...axisCommon, splitLine: { show: false } },
        visualMap: {
          min: 0,
          max,
          calculable: false,
          orient: "horizontal",
          left: "center",
          bottom: 0,
          inRange: { color: SEQUENTIAL.slice(1) },
          textStyle: { color: axisText, fontSize: 10 },
          itemWidth: 10,
          itemHeight: 90,
        },
        series: [{
          type: "heatmap",
          data: points,
          label: { show: false },
          itemStyle: { borderRadius: 4, borderColor: dark ? "#11172B" : "#FFFFFF", borderWidth: 2 },
          emphasis: { itemStyle: { shadowBlur: 8, shadowColor: "rgba(79,107,255,0.4)" } },
        }],
      };
    }

    default:
      return base;
  }
}
