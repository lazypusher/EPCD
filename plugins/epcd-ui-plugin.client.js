// EPCD UI dynamic plugin — CLIENT half (durable source).
//
// Registers two `tool.call.toolview` rows keyed by tool name, plus hides the hero branding:
//   epcd_status     → TPE progress bar (+ per-round cost sparkline)
//   epcd_artifacts  → artifact gallery with three-view (俯视/轴测/侧视) tab switching
//
// Usage: this file is the `code.client` function body for a dynamic Cordis package.
// Mount it with cordis_define + cordis_run, together with plugins/epcd-ui-plugin.host.js.

function jsonFromBlock(block) {
  if (!block) return null
  var content = Array.isArray(block.content) ? block.content : null
  if (content) {
    for (var i = 0; i < content.length; i++) {
      var b = content[i]
      var txt = null
      if (typeof b === 'string') txt = b
      else if (b && typeof b === 'object') txt = (b.text !== undefined ? b.text : (b.output !== undefined ? b.output : b.content))
      if (typeof txt === 'string') { try { var v2 = JSON.parse(txt); if (v2 && typeof v2 === 'object') return v2 } catch (e) {} }
    }
  }
  var raw = null
  if (typeof block.argsRaw === 'string') raw = block.argsRaw
  else if (block.call && typeof block.call.argsRaw === 'string') raw = block.call.argsRaw
  if (raw) { try { var v = JSON.parse(raw); if (v && typeof v === 'object') return v } catch (e) {} }
  return null
}

function viewOf(img) {
  var s = (img && img.label ? img.label : '') + '|' + (img && img.path ? img.path : '')
  if (img && img.view) return img.view
  if (/俯视|preview_top|_top/i.test(s)) return 'top'
  if (/轴测|preview_iso|_iso/i.test(s)) return 'iso'
  if (/侧视|preview_side|_side/i.test(s)) return 'side'
  return null
}

// 净化 Touchstone（S2P）文本：保留表格头（S 参数格式行 + 列头）与频率行，
// 去掉文件头部的 ewave 命令行 / 端口注释 / 路径等元信息。
function sanitizeS2P(text) {
  if (typeof text !== 'string') return text
  var lines = text.split(/\r?\n/)
  var out = []
  var seenData = false
  var hasHeader = false
  var keptColumnHeader = false
  for (var i = 0; i < lines.length; i++) {
    var ln = lines[i]
    var t = ln.trim()
    if (t.charAt(0) === '#') {
      if (!hasHeader) { out.push(ln); hasHeader = true }
      continue
    }
    if (t.charAt(0) === '!') {
      if (hasHeader && !keptColumnHeader && !seenData && /freq/i.test(t)) {
        out.push(ln); keptColumnHeader = true
      }
      continue
    }
    if (t === '') { if (seenData) out.push(ln); continue }
    if (/^[\d.+-eE]/.test(t)) {
      seenData = true
      out.push(ln)
    }
  }
  // 若未识别到格式/数据行，回退原文（可能不是标准 S2P）
  if (!hasHeader && !seenData) return text
  return out.join('\n')
}

function ProgressBar(props) {
  var data = jsonFromBlock(props.block)
  var p = data && data.progress ? data.progress : data
  if (!p || typeof p.total_rounds !== 'number' || typeof p.done_rounds !== 'number') {
    return React.createElement('div', { style: { padding: 12, fontSize: 13 } }, '等待 TPE 优化进度数据…')
  }
  var total = p.total_rounds
  var done = p.done_rounds
  var pct = total > 0 ? Math.round(Math.min(1, Math.max(0, done / total)) * 100) : 0
  var statusText = p.status === 'finished' ? '已完成' : (p.status === 'paused' ? '已暂停' : (p.status === 'canceled' ? '已取消' : '进行中'))
  var costText = typeof p.best_cost === 'number' ? p.best_cost.toFixed(3) : '—'
  var rounds = Array.isArray(p.rounds) ? p.rounds : []
  var spark = []
  for (var i = 0; i < rounds.length; i++) {
    var r = rounds[i]
    if (r && typeof r.cost === 'number') {
      var h = Math.max(3, Math.min(30, Math.abs(r.cost) * 30 + 3))
      spark.push(React.createElement('span', { key: i, title: 'R' + (r.round_no != null ? r.round_no : (i + 1)) + ' cost ' + r.cost.toFixed(3), style: { flex: '1 1 auto', minWidth: 2, height: h + 'px', backgroundColor: '#4c7ff0', borderRadius: 2 } }))
    }
  }
  var header = React.createElement('div', { style: { display: 'flex', justifyContent: 'space-between', marginBottom: 6, fontSize: 13 } },
    React.createElement('span', { style: { fontWeight: 600 } }, 'TPE 优化进度 · ' + statusText),
    React.createElement('span', null, done + ' / ' + total + ' 轮')
  )
  var bar = React.createElement('div', { style: { height: 8, borderRadius: 4, background: '#eef0f3', overflow: 'hidden' } },
    React.createElement('div', { style: { width: pct + '%', height: '100%', borderRadius: 4, background: '#4c7ff0', transition: 'width .3s ease' } })
  )
  var meta = React.createElement('div', { style: { marginTop: 6, fontSize: 12 } }, '当前最优 cost ' + costText)
  var children = [header, bar, meta]
  if (rounds.length) {
    children.push(React.createElement('div', { style: { display: 'flex', gap: 2, alignItems: 'flex-end', height: 32, marginTop: 8, padding: '0 4px' } }, spark))
  }
  return React.createElement('div', { style: { padding: '10px 12px', borderRadius: 12, border: '1px solid #e5e7eb' } }, children)
}

// 统一卡片样式：加粗标题置顶 + 内容，图片细边框圆角阴影。
var CARD_STYLE = { marginBottom: 12, padding: 12, border: '1px solid #e5e7eb', borderRadius: 12, background: '#ffffff' }
var CARD_TITLE_STYLE = { fontSize: 13, fontWeight: 600, margin: '0 0 8px', color: '#1f2329' }
var IMG_STYLE = { width: '100%', maxHeight: 320, objectFit: 'contain', borderRadius: 8, border: '1px solid #eef0f3', boxShadow: '0 1px 4px rgba(0,0,0,0.08)', background: '#fafafa', display: 'block' }
var PRE_STYLE = { fontSize: 11, lineHeight: 1.5, whiteSpace: 'pre-wrap', wordBreak: 'break-word', maxHeight: 240, overflow: 'auto', background: '#0f151a', color: '#e6e8eb', padding: 10, borderRadius: 8, margin: 0 }

// 为 target-chart 类型的图提供默认标题：性能指标图
function defaultLabel(a) {
  if (a && a.label) return a.label
  if (a && a.path) {
    var bn = String(a.path).split(/[\\/]/).pop() || ''
    if (/target-chart/i.test(bn)) return '性能指标图'
    return bn
  }
  if (a && /target-chart/i.test(String(a.kind || ''))) return '性能指标图'
  return '图像'
}

function ViewSwitcher(props) {
  var vws = props.views
  var state = React.useState(null)
  var sel = state[0]
  var set = state[1]
  var order = ['top', 'iso', 'side']
  var names = { top: '俯视', iso: '轴测', side: '侧视' }
  var found = {}
  for (var i = 0; i < vws.length; i++) { if (!found[vws[i].key]) found[vws[i].key] = vws[i] }
  var keys = []
  for (var j = 0; j < order.length; j++) { if (found[order[j]]) keys.push(order[j]) }
  var current = (sel && found[sel]) ? sel : (keys[0] || null)
  var cur = current ? found[current] : null
  var tabs = keys.map(function (k) {
    var active = k === current
    return React.createElement('button', { key: k, onClick: function () { set(k) }, style: {
      padding: '4px 10px', marginRight: 6, fontSize: 12, cursor: 'pointer', borderRadius: 6,
      border: active ? '1px solid #4c7ff0' : '1px solid #e5e7eb', background: active ? '#4c7ff0' : '#f5f6f8',
      color: active ? '#ffffff' : '#333333', fontWeight: active ? 600 : 400
    } }, names[k])
  })
  return React.createElement('div', { style: CARD_STYLE },
    React.createElement('div', { style: CARD_TITLE_STYLE }, '版图三视图'),
    React.createElement('div', { style: { display: 'flex', marginBottom: 8 } }, tabs),
    cur ? React.createElement('img', { src: cur.image, alt: names[current], style: IMG_STYLE }) : null,
    cur ? React.createElement('div', { style: { fontSize: 12, color: '#68707a', marginTop: 6 } }, names[current] || cur.label) : null
  )
}

function ArtifactsView(props) {
  var data = jsonFromBlock(props.block)
  var arts = data && data.artifacts ? data.artifacts : []
  if (!Array.isArray(arts) || arts.length === 0) {
    return React.createElement('div', { style: { padding: 12, fontSize: 13 } }, '暂无产物')
  }
  var views = []
  var images = []
  var others = []
  for (var i = 0; i < arts.length; i++) {
    var a = arts[i]
    if (a && a.image) {
      var v = viewOf(a)
      if (v) views.push({ key: v, label: defaultLabel(a), image: a.image })
      else images.push(a)
    } else others.push(a)
  }
  var kids = []
  if (views.length >= 2) kids.push(React.createElement(ViewSwitcher, { key: 'threeview', views: views }))
  else if (views.length === 1) images.unshift({ label: defaultLabel(views[0]), image: views[0].image, path: '' })
  for (var j = 0; j < images.length; j++) {
    var im = images[j]
    kids.push(React.createElement('div', { key: (im.path || im.label || ('img' + j)), style: CARD_STYLE },
      React.createElement('div', { style: CARD_TITLE_STYLE }, defaultLabel(im)),
      React.createElement('img', { src: im.image, alt: defaultLabel(im), style: IMG_STYLE })
    ))
  }
  for (var k = 0; k < others.length; k++) {
    var o = others[k]
    var key = (o && o.path) ? o.path : ('o' + k)
    if (o && o.error) {
      kids.push(React.createElement('div', { key: key, style: Object.assign({}, CARD_STYLE, { color: '#c0392b', fontSize: 12 }) }, (o.label || key) + ' · 读取失败: ' + o.error))
    } else if (o && typeof o.text === 'string') {
      var textContent = (o.kind === 's2p') ? sanitizeS2P(o.text) : o.text
      kids.push(React.createElement('div', { key: key, style: CARD_STYLE },
        React.createElement('div', { style: CARD_TITLE_STYLE }, o.label || ''),
        React.createElement('pre', { style: PRE_STYLE }, textContent)
      ))
    } else {
      kids.push(React.createElement('div', { key: key, style: Object.assign({}, CARD_STYLE, { fontSize: 12 }) }, (o ? ((o.label || key) + ' · ' + o.kind) : '…')))
    }
  }
  return React.createElement('div', { style: { padding: '4px 2px' } }, kids)
}

return {
  inject: ['slots'],
  apply: function (ctx) {
    styles.insert('.pXSMma_headline{display:none!important}')
    ctx.slots.inject('tool.call.toolview', function () { return ctx.slots.register({ name: 'tool.call.toolview', key: 'epcd_status' }, ProgressBar) })
    ctx.slots.inject('tool.call.toolview', function () { return ctx.slots.register({ name: 'tool.call.toolview', key: 'epcd_artifacts' }, ArtifactsView) })
  }
}