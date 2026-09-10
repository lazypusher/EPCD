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
const manifest = JSON.stringify({
  id: '/',
  name: 'EPCD 器件设计平台',
  short_name: 'EPCD',
  start_url: '/',
  scope: '/',
  display: 'fullscreen',
  icons: [{ src: '/favicon.svg', sizes: 'any', type: 'image/svg+xml', purpose: 'any' }]
});

// UI 内的 DeepSeek 品牌元素 → EPCD / 隐藏。
// class hash 来自 dsh-web-frontend / dsh-client-ui-conversation 编译产物
// （dsh 版本 0.1.0-rc.6 锁定后稳定）。
const BRAND_CSS = [
  /* sidebar 顶部：DeepSeek 文字字标 → EPCD 文字 */
  '.hHd-Xa_brand svg{display:none!important}',
  '.hHd-Xa_brand::after{content:"EPCD 器件设计";font-size:15px;font-weight:600;color:var(--dsw-alias-label-primary);white-space:nowrap}',
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
    .replace(/<title>[^<]*<\/title>/, '<title>EPCD 器件设计平台</title>')
    .replace('</head>', `<style>${BRAND_CSS}</style></head>`));
  // favicon（精确路由优先于 dist 的 fallback）
  ctx.webServer.register({ kind: 'exact', path: '/favicon.svg', handler: respond(favicon, 'image/svg+xml') });
  // PWA manifest
  ctx.webServer.register({ kind: 'exact', path: '/manifest.webmanifest', handler: respond(manifest, 'application/manifest+json') });
}