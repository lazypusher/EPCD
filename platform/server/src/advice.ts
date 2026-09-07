import type { EpcdConfig } from "./epcd/bridge.js";

export interface TargetMetric {
  metric: string;
  frequency?: { value: number; unit: string; valueHz?: number };
  comparison: string;
  targetValue: number;
  actualValue: number;
  unit: string;
  satisfied: boolean;
  relativeDeviation?: number;
}

function comparisonName(c: string): string {
  if (c === "greater-than") return "≥";
  if (c === "less-than") return "≤";
  return "≈";
}

function metricHint(metric: string): string {
  const m = metric.toLowerCase();
  if (m === "l" || m.includes("induct")) {
    return "增大匝数或缩小内径通常可提升电感 L；减小线宽可进一步增大 L。";
  }
  if (m.includes("q")) {
    return "增大导体截面积（加宽线宽 / 加厚金属 / 多金属层并联）可降低有效串联电阻，从而提升 Q。";
  }
  if (m.includes("size") || m.includes("area") || m.includes("dim")) {
    return "缩小外径或减少匝数以满足尺寸约束。";
  }
  return "调整相关几何参数（匝数/线宽/内径/间距）并重新优化。";
}

export function unmetTargets(metrics: TargetMetric[] | undefined): TargetMetric[] {
  return (metrics ?? []).filter((m) => !m.satisfied);
}

export function ruleBasedAdvice(metrics: TargetMetric[] | undefined): string[] {
  const out: string[] = [];
  for (const m of unmetTargets(metrics)) {
    const dev =
      typeof m.relativeDeviation === "number"
        ? (m.relativeDeviation * 100).toFixed(2)
        : "?";
    const head =
      `${m.metric} 未达标：需 ${comparisonName(m.comparison)} ${m.targetValue}${m.unit}` +
      `，实际 ${Number(m.actualValue).toFixed(4)}${m.unit}（${dev}% 偏差）`;
    out.push(`${head}。${metricHint(m.metric)}`);
  }
  return out;
}

export interface AdviceResult {
  source: "llm" | "rule";
  advice: string[];
  unmet: TargetMetric[];
}

export async function generateAdvice(
  metrics: TargetMetric[] | undefined,
  config: EpcdConfig
): Promise<AdviceResult> {
  const unmet = unmetTargets(metrics);
  if (unmet.length === 0) return { source: "rule", advice: [], unmet };

  const rule = ruleBasedAdvice(metrics);
  if (!config.llmBaseUrl || !config.llmKey) {
    return { source: "rule", advice: rule, unmet };
  }

  try {
    const resp = await fetch(`${config.llmBaseUrl.replace(/\/$/, "")}/chat/completions`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${config.llmKey}`,
      },
      body: JSON.stringify({
        model: config.llmModel ?? "deepseek-chat",
        temperature: 0.3,
        messages: [
          {
            role: "system",
            content:
              "你是电子元器件（片上电感）设计专家。根据给定的未达标目标，用中文给出简短、可操作的设计调整建议，每条一行，不解释无关内容。",
          },
          {
            role: "user",
            content: JSON.stringify(unmet),
          },
        ],
      }),
    });
    if (!resp.ok) throw new Error(`llm http ${resp.status}`);
    const json = (await resp.json()) as {
      choices?: { message?: { content?: string } }[];
    };
    const text = json.choices?.[0]?.message?.content?.trim();
    if (!text) throw new Error("llm empty");
    const lines = text
      .split(/\r?\n/)
      .map((s) => s.replace(/^[-*\d.\s]+/, "").trim())
      .filter(Boolean);
    return { source: "llm", advice: [...lines, ...rule], unmet };
  } catch {
    return { source: "rule", advice: rule, unmet };
  }
}