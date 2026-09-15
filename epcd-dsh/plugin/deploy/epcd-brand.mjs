/**
 * EPCD 专用 branding：覆盖 title / favicon / manifest + UI 内 DeepSeek logo / slogan。
 * 仅在本 profile（epcd）生效，不影响默认 web profile。
 */
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

export const name = 'epcd-brand';
export const inject = ['webServer'];

const here = dirname(fileURLToPath(import.meta.url));
const favicon = readFileSync(join(here, 'epcd-favicon.svg'), 'utf8');
// 左上角文字前的 logo（九同方微电子），base64 内联进 CSS。
// 缺失时优雅降级（不阻断 profile 启动），logo 规则不生效即可。
let logoDataUri = null;
try {
  logoDataUri = `data:image/png;base64,${readFileSync(join(here, 'epcd-logo.png')).toString('base64')}`;
} catch {
  logoDataUri = null;
}
const manifest = JSON.stringify({
  id: '/',
  name: 'Epcd Agent',
  short_name: 'Epcd Agent',
  start_url: '/',
  scope: '/',
  display: 'fullscreen',
  icons: [{ src: '/favicon.svg', sizes: 'any', type: 'image/svg+xml', purpose: 'any' }]
});

// UI 内的 DeepSeek 品牌元素 → EPCD / 隐藏。
// class hash 来自 dsh-web-frontend / dsh-client-ui-conversation 编译产物
// （dsh 版本 0.1.0-rc.6 锁定后稳定）。
const BRAND_CSS = [
  /* sidebar 顶部：DeepSeek 文字字标 → EPCD logo + 文字（对齐标准模式 brandName 18px / brandMark 24px 高） */
  '.hHd-Xa_brand svg{display:none!important}',
  '.hHd-Xa_brand{display:inline-flex;align-items:center;gap:8px}',
  // logo 缺失时不注入 ::before 图，仅保留文字（优雅降级，避免 url("null") 坏规则）。
  ...(logoDataUri
    ? [`.hHd-Xa_brand::before{content:"";width:100px;height:36px;flex:none;background:url("${logoDataUri}") center/contain no-repeat;overflow:hidden}`]
    : []),
  '.hHd-Xa_brand::after{content:"Epcd Agent";font-size:18px;font-weight:600;line-height:24px;letter-spacing:.04em;color:var(--dsw-alias-label-primary);white-space:nowrap}',
  /* 折叠态侧栏的鲸鱼图标（0.1.5 起类名 railFish → railMark） */
  '.hHd-Xa_railMark{display:none!important}',
  /* 空对话欢迎页 Hero 整行：slogan「探索未至之境」+「预览版」badge + 鲸鱼，一并隐藏 */
  '.pXSMma_headline{display:none!important}',
  /* 空对话欢迎页的鲸鱼图标（单独兜底） */
  '.pXSMma_fish{display:none!important}'
].join('\n');

function respond(body, contentType) {
  return (_req, res) => {
    res.writeHead(200, { 'content-type': contentType });
    res.end(body);
  };
}

export function apply(ctx) {
  // 浏览器标签标题 + 注入 EPCD logo 覆盖 CSS
  ctx.webServer.tapIndex((html) => html
    .replace(/<title>[^<]*<\/title>/, '<title>Epcd Agent</title>')
    .replace('</head>', `<style>${BRAND_CSS}</style></head>`));
  // favicon（精确路由优先于 dist 的 fallback）
  ctx.webServer.register({ kind: 'exact', path: '/favicon.svg', handler: respond(favicon, 'image/svg+xml') });
  // PWA manifest
  ctx.webServer.register({ kind: 'exact', path: '/manifest.webmanifest', handler: respond(manifest, 'application/manifest+json') });
}