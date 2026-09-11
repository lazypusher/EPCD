// EPCD UI dynamic plugin — HOST half (durable source).
//
// Registers two first-class tools that feed the client toolviews:
//   epcd_status     — echo the TPE optimization summary (rendered as a progress bar on the client)
//   epcd_artifacts  — read local artifact files (PNG→base64, S2P/JSON/txt→text, GDS→entry)
//
// Usage: this file is the `code.host` function body for a dynamic Cordis package.
// Mount it with cordis_define (kind:"new", idPrefix:"epcdui") + cordis_run, together
// with plugins/epcd-ui-plugin.client.js as `code.client`.

function bytesToBase64(bytes) {
  var chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/'
  var out = ''
  var i = 0
  for (; i + 2 < bytes.length; i += 3) {
    var n = (bytes[i] << 16) | (bytes[i + 1] << 8) | bytes[i + 2]
    out += chars.charAt((n >> 18) & 63) + chars.charAt((n >> 12) & 63) + chars.charAt((n >> 6) & 63) + chars.charAt(n & 63)
  }
  var rest = bytes.length - i
  if (rest === 1) {
    var n1 = bytes[i] << 16
    out += chars.charAt((n1 >> 18) & 63) + chars.charAt((n1 >> 12) & 63) + '=='
  } else if (rest === 2) {
    var n2 = (bytes[i] << 16) | (bytes[i + 1] << 8)
    out += chars.charAt((n2 >> 18) & 63) + chars.charAt((n2 >> 12) & 63) + chars.charAt((n2 >> 6) & 63) + '='
  }
  return out
}

function jsonBlock(value) {
  return [{ type: 'text', text: JSON.stringify(value) }]
}

// 净化 Touchstone（S2P）文本：保留表格头（S 参数格式行 + 列头）与频率行，
// 去掉文件头部的 ewave 命令行 / 端口注释 / 路径等元信息。
function sanitizeS2P(text) {
  if (typeof text !== 'string') return text
  var lines = text.split(/\r?\n/)
  var out = []
  var hasHeader = false // 已保留 "# HZ S RI R 50" 格式行
  var keptColumnHeader = false // 已保留紧跟格式行的那条 "! freq reS11 ..." 列头
  var seenData = false
  for (var i = 0; i < lines.length; i++) {
    var t = lines[i].trim()
    if (t.charAt(0) === '#') {
      if (!hasHeader) { out.push(lines[i]); hasHeader = true }
      continue
    }
    if (t.charAt(0) === '!') {
      // 仅保留紧跟 "# HZ..." 格式行之后的第一条注释（即列头），其余 ewave 命令/端口/路径注释丢弃
      if (hasHeader && !keptColumnHeader && !seenData && /freq/i.test(t)) {
        out.push(lines[i]); keptColumnHeader = true
      }
      continue
    }
    if (t === '') { if (seenData) out.push(lines[i]); continue }
    if (/^[\d.+-eE]/.test(t)) { seenData = true; out.push(lines[i]) }
  }
  if (!hasHeader && !seenData) return text // 非标准 S2P，回退原文
  return out.join('\n')
}

return {
  apply(ctx) {
    var fs = ctx.get('fs')
    var disposers = []

    function reg(def) {
      disposers.push(harness.registerTool(ctx, harness.defineTool(def)))
    }

    reg({
      name: 'epcd_status',
      description: '把 TPE 优化进度渲染成进度条。传你刚从优化状态里读到的汇总字段。',
      parameters: {
        type: 'object',
        properties: {
          task_id: { type: 'string', description: '优化任务 id，如 opt-17' },
          status: { type: 'string', description: 'running | finished | paused | canceled' },
          total_rounds: { type: 'number', description: '预算 max_rounds' },
          done_rounds: { type: 'number', description: '已完成轮数' },
          best_cost: { type: 'number', description: '当前最优 cost（越小越好）' },
          rounds: { type: 'array', description: '每轮 cost 序列（可选）', items: { type: 'object', properties: { round_no: { type: 'number' }, cost: { type: 'number' }, status: { type: 'string' } } } }
        },
        required: ['total_rounds', 'done_rounds']
      },
      execute: async function (args) {
        return { progress: {
          task_id: args.task_id || null,
          status: args.status || 'running',
          total_rounds: args.total_rounds,
          done_rounds: args.done_rounds,
          best_cost: typeof args.best_cost === 'number' ? args.best_cost : null,
          rounds: Array.isArray(args.rounds) ? args.rounds : []
        } }
      },
      output: {
        schema: { type: 'object', additionalProperties: true },
        render: function (args, value) { return jsonBlock(value) }
      }
    })

    reg({
      name: 'epcd_artifacts',
      description: '把已交付的器件产物（版图预览 PNG、S 参数 S2P、GDS、目标值 JSON/文本）渲染成图库；多张版图预览（top/iso/side）会合并成三视图切换。传本机绝对路径 + kind。',
      parameters: {
        type: 'object',
        properties: {
          files: { type: 'array', items: { type: 'object', properties: { path: { type: 'string', description: '本机绝对路径' }, kind: { type: 'string', description: 'image | text | s2p | json | gds' }, label: { type: 'string' } }, required: ['path', 'kind'] } }
        },
        required: ['files']
      },
      execute: async function (args) {
        if (!fs) return { artifacts: [], error: 'fs unavailable' }
        var out = []
        var files = Array.isArray(args.files) ? args.files : []
        for (var i = 0; i < files.length; i++) {
          var f = files[i] || {}
          var label = f.label || String(f.path || '').split(/[\\/]/).pop() || (f.kind || 'file')
          var entry = { path: f.path || '', kind: f.kind || 'text', label: label }
          try {
            if (f.kind === 'image') {
              var target = await fs.resolve(f.path)
              var bytes = await fs.readBytes(target, undefined, 8 * 1024 * 1024)
              entry.image = 'data:image/png;base64,' + bytesToBase64(bytes)
            } else if (f.kind === 'gds') {
              entry.kind = 'gds'
            } else {
              var t2 = await fs.resolve(f.path)
              var text = await fs.readText(t2)
              var capped = text.length > 20000 ? text.slice(0, 20000) + '\n...(截断)' : text
              // S2P 只展示表格数据，去掉 ewave 命令/路径等文件头注释
              entry.text = (f.kind === 's2p') ? sanitizeS2P(capped) : capped
            }
          } catch (e) {
            entry.error = String((e && e.message) || e)
          }
          out.push(entry)
        }
        return { artifacts: out }
      },
      output: {
        schema: { type: 'object', additionalProperties: true },
        render: function (args, value) { return jsonBlock(value) }
      }
    })

    return function () { disposers.forEach(function (d) { if (typeof d === 'function') d() }) }
  }
}