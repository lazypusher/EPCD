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
  return React.createElement('div', { style: { marginBottom: 10 } },
    React.createElement('div', { style: { display: 'flex', marginBottom: 6 } }, tabs),
    cur ? React.createElement('img', { src: cur.image, alt: names[current], style: { maxWidth: '100%', maxHeight: 320, borderRadius: 8, border: '1px solid #e5e7eb', display: 'block' } }) : null,
    cur ? React.createElement('div', { style: { fontSize: 12, marginTop: 4 } }, cur.label) : null
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
      if (v) views.push({ key: v, label: a.label || a.path, image: a.image })
      else images.push(a)
    } else others.push(a)
  }
  var kids = []
  if (views.length >= 2) kids.push(React.createElement(ViewSwitcher, { key: 'threeview', views: views }))
  else if (views.length === 1) images.unshift({ label: views[0].label, image: views[0].image, path: '' })
  for (var j = 0; j < images.length; j++) {
    var im = images[j]
    kids.push(React.createElement('div', { key: (im.path || im.label || ('img' + j)), style: { marginBottom: 10 } },
      React.createElement('img', { src: im.image, alt: im.label || '', style: { maxWidth: '100%', maxHeight: 320, borderRadius: 8, border: '1px solid #e5e7eb', display: 'block' } }),
      React.createElement('div', { style: { fontSize: 12, marginTop: 4 } }, im.label || '')
    ))
  }
  for (var k = 0; k < others.length; k++) {
    var o = others[k]
    var key = (o && o.path) ? o.path : ('o' + k)
    if (o && o.error) {
      kids.push(React.createElement('div', { key: key, style: { fontSize: 12, color: '#c0392b', padding: '4px 0' } }, (o.label || key) + ' · 读取失败: ' + o.error))
    } else if (o && typeof o.text === 'string') {
      kids.push(React.createElement('div', { key: key, style: { marginBottom: 10 } },
        React.createElement('div', { style: { fontSize: 12, fontWeight: 600, marginBottom: 4 } }, o.label || ''),
        React.createElement('pre', { style: { fontSize: 11, lineHeight: 1.5, whiteSpace: 'pre-wrap', wordBreak: 'break-word', maxHeight: 240, overflow: 'auto', background: '#0f151a', color: '#e6e8eb', padding: 10, borderRadius: 8 } }, o.text)
      ))
    } else {
      kids.push(React.createElement('div', { key: key, style: { fontSize: 12, padding: '6px 8px', border: '1px solid #e5e7eb', borderRadius: 8, marginBottom: 6 } }, (o ? ((o.label || key) + ' · ' + o.kind) : '…')))
    }
  }
  return React.createElement('div', { style: { padding: '10px 12px', borderRadius: 12, border: '1px solid #e5e7eb' } },
    React.createElement('div', { style: { fontSize: 13, fontWeight: 600, marginBottom: 8 } }, '设计产物'),
    kids
  )
}

return {
  inject: ['slots'],
  apply: function (ctx) {
    styles.insert('.pXSMma_headline{display:none!important}')
    ctx.slots.inject('tool.call.toolview', function () { return ctx.slots.register({ name: 'tool.call.toolview', key: 'epcd_status' }, ProgressBar) })
    ctx.slots.inject('tool.call.toolview', function () { return ctx.slots.register({ name: 'tool.call.toolview', key: 'epcd_artifacts' }, ArtifactsView) })
  }
}