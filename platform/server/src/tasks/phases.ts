// 8 阶段状态机 + 4 里程碑（对应 epcd-agent-flow skill 的端到端流程）

export type Phase =
  | "health"      // 1 健康检查
  | "project"     // 2 建工程
  | "template"    // 3 选模板 + M1
  | "objectives"  // 4 配置目标 + M2
  | "optimization"// 5 迭代优化
  | "apply"       // 6 写回最优 + M3
  | "final"       // 7 最终仿真 + M4
  | "deliver";    // 8 产物交付

export const PHASES: Phase[] = [
  "health",
  "project",
  "template",
  "objectives",
  "optimization",
  "apply",
  "final",
  "deliver",
];

export interface MilestoneDef {
  code: "M1" | "M2" | "M3" | "M4";
  phase: Phase;   // 该阶段完成后暂停，等待确认
  title: string;
  description: string;
}

export const MILESTONES: MilestoneDef[] = [
  { code: "M1", phase: "template", title: "模板与实例选定", description: "确认选用的电感触模板与实例名" },
  { code: "M2", phase: "objectives", title: "目标与仿真配置", description: "确认坐指标/频点/比较/权重与扫频预算" },
  { code: "M3", phase: "apply", title: "最优参数写回", description: "确认将优化出的最优几何参数写回实例" },
  { code: "M4", phase: "final", title: "最终仿真结果", description: "确认最终 run 达标，进入产物交付" },
];

export const MILESTONE_BY_CODE = Object.fromEntries(
  MILESTONES.map((m) => [m.code, m])
) as Record<MilestoneDef["code"], MilestoneDef>;

export const PHASE_AFTER: Record<Phase, Phase | null> = {
  health: "project",
  project: "template",
  template: "objectives",
  objectives: "optimization",
  optimization: "apply",
  apply: "final",
  final: "deliver",
  deliver: null,
};

// 里程碑决策
export type MilestoneDecision = "approve" | "modify" | "abort";