/**
 * EPCD 专用 branding：覆盖 title / favicon / manifest，去掉 DeepSeek 标识。
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

function respond(body, contentType) {
  return (_req, res) => {
    res.writeHead(200, { 'content-type': contentType });
    res.end(body);
  };
}

export function apply(ctx) {
  // 浏览器标签标题
  ctx.webServer.tapIndex((html) => html.replace(/<title>[^<]*<\/title>/, '<title>EPCD 器件设计平台</title>'));
  // favicon（精确路由优先于 dist 的 fallback）
  ctx.webServer.register({ kind: 'exact', path: '/favicon.svg', handler: respond(favicon, 'image/svg+xml') });
  // PWA manifest
  ctx.webServer.register({ kind: 'exact', path: '/manifest.webmanifest', handler: respond(manifest, 'application/manifest+json') });
}