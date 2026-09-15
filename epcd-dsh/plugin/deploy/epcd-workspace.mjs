/**
 * EPCD 固定工作区：DSH 启动时自动把「项目根目录」登记为 epcd 的工作区。
 *
 * 背景：EPCD 是固定单工作区的专用 agent（UI 已隐藏工作区切换入口）。但 DSH
 * 的工作区是「随 session 启动时 bootstrap」动态建立的——全新部署时还没有任何
 * session，前端会提示「加载工作区」。本插件在启动时直接通过正规 workspaceRegistry
 * API 把项目根登记为工作区，消除空状态提示；后续新 session 的 cwd 即固定为该项目根。
 *
 * 路径来源：机器相关的绝对路径不能硬编码进 git，故由 deploy 脚本通过环境变量
 * `EPCD_WORKSPACE` 传入仓库根绝对路径；未设置时回落到 DSH 进程启动目录
 * `process.cwd()`。create 幂等（同路径复用），路径不存在时优雅降级（不阻断启动）。
 *
 * 与 epcd-brand.mjs / epcd-ui-lock.mjs 同一种「本地 host 插件 + cordis.patch insert」
 * 模式，仅对本 profile（epcd）生效，跟随 git 部署。
 */

export const name = 'epcd-workspace';
export const inject = ['workspaceRegistry'];

export function apply(ctx) {
  const path = process.env.EPCD_WORKSPACE?.trim() || process.cwd();

  // create 幂等注册（同路径复用）；路径不存在/非目录时 realpath 会 reject，
  // 捕获后仅记录警告，不阻断 profile 启动。
  ctx.workspaceRegistry
    .create(path)
    .then(() => {
      ctx.logger.info(`epcd-workspace: 工作区已就绪：${path}`);
    })
    .catch((error) => {
      ctx.logger.warn(`epcd-workspace: 无法登记工作区 "${path}"：${error instanceof Error ? error.message : String(error)}`);
    });
}