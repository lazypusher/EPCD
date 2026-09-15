/**
 * EPCD 专用 UI 锁定：只在 epcd profile（固定单工作区）内生效，不影响默认 web profile。
 *
 * 与 epcd-brand.mjs 同一种注入机制（webServer.tapIndex 注入 <style> + <script>）。
 * class hash / data-* 属性来自 dsh-web-frontend 与各 client-ui 编译产物
 * （dsh 版本 0.1.5-rc.1 锁定后稳定，升级后需对照前端 dist 重新核对）。四组行为：
 *
 *   1) 固定工作区 —— 隐藏「添加/切换工作区」入口：
 *        - 输入栏上方 hero 的「选择工作区」chip
 *        - 左侧边栏工作区 section 头的「+ 添加工作区」按钮
 *      会话列表保留（仍可浏览/切换历史会话，只是不能再增/切工作区）。
 *
 *   2) 隐藏对话栏上方 hero 的「预设模式」选择器（标准/PTC/极简/创造等 Agent preset，
 *      即「即将开始的这个会话所用的 Agent 预设」）。默认只用 epcd 预设，隐去切换入口。
 *
 *   3) 默认隐藏 LLM 思考块（含流式输出中的「思考」），回合过程摘要行保留。
 *      工具调用节点维持现状（仍显示）；执行细节仍可在「轨迹」视图查看。
 *
 *   4) 右侧边栏文件树隐藏所有 `.` 开头（dotfile）目录（用 MutationObserver 按条目名
 *      basename 判断，覆盖任意 .xxx，不限固定清单）。
 *
 * 其中 (4) 无法用纯 CSS 表达（条目名以 . 开头是运行时数据），故注入一段极小的
 * document 观察脚本；其余用 CSS 的 data-* 稳定属性选择器。
 */

export const name = 'epcd-ui-lock';
export const inject = ['webServer'];

// ── CSS 规则（data-* 属性为主，比 hash 类名更稳定） ──────────────────────────
const UI_LOCK_CSS = [
  /* 1) 固定工作区 */
  '.pXSMma_workspace{display:none!important}',   /* hero「选择工作区」chip */
  '.bhn1Oq_iconButton{display:none!important}',  /* 侧栏「+ 添加工作区」按钮 */

  /* 2) 对话栏上方「预设模式」选择器（标准/PTC/极简/创造等 Agent preset） */
  '.cubgiG_seat{display:none!important}',

  /* 3) 隐藏思考块（工具调用节点与回合过程摘要保留）。
        ReasoningRow 根节点：class=lcKema_root + data-variant="think"，
        双保险同时命中，避免单一选择器因版本/渲染路径失效。 */
  '.lcKema_root,[data-variant="think"]{display:none!important}',
  '.lcKema_thinkBody{display:none!important}'
].join('\n');

// ── 极小的 document 观察脚本：隐藏所有 dotfile 目录 ──────────────────────────
// 文件树条目为 <li data-files-entry="directory" data-files-path="...">，
// 路径末段即目录名；以 . 开头的目录整行隐藏。文件树按需懒加载，需监听新增节点。
const UI_LOCK_SCRIPT = `(function () {
  function apply(node) {
    if (!node || node.nodeType !== 1) return;
    if (node.matches && node.matches('li[data-files-entry="directory"]')) {
      var name = null;
      var path = node.getAttribute('data-files-path');
      if (path !== null) {
        var n = String(path).replace(/\\\\/g, '/');
        var i = n.lastIndexOf('/');
        var seg = i >= 0 ? n.slice(i + 1) : n;
        if (seg.length > 1 && seg.charAt(0) === '.') name = seg;
      }
      if (name === null) {
        var s = node.querySelector('.k-1LKG_name');
        if (s) {
          var txt = (s.textContent || '').trim();
          if (txt.length > 1 && txt.charAt(0) === '.') name = txt;
        }
      }
      if (name !== null) { node.style.setProperty('display', 'none', 'important'); return; }
    }
    if (node.querySelectorAll) {
      var items = node.querySelectorAll('li[data-files-entry="directory"]');
      for (var k = 0; k < items.length; k++) apply(items[k]);
    }
  }
  function sweep() {
    var all = document.querySelectorAll('li[data-files-entry="directory"]');
    for (var j = 0; j < all.length; j++) apply(all[j]);
  }
  function start() {
    sweep();
    var mo = new MutationObserver(function (muts) {
      for (var i = 0; i < muts.length; i++) {
        var added = muts[i].addedNodes;
        for (var j = 0; j < added.length; j++) apply(added[j]);
      }
    });
    mo.observe(document.documentElement, { childList: true, subtree: true });
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', start);
  } else {
    start();
  }
})();`;

export function apply(ctx) {
  ctx.webServer.tapIndex((html) => {
    if (!html.includes('</head>')) return html;
    const style = `<style data-epcd-ui-lock>${UI_LOCK_CSS}</style>`;
    const script = `<script data-epcd-ui-lock>${UI_LOCK_SCRIPT}</script>`;
    return html.replace('</head>', `${style}${script}</head>`);
  });
}