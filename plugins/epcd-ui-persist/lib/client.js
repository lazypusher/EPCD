// EPCD UI persistent plugin — BROWSER half (client module).
//
// Loaded by the dsh client module system as a `dsh.client` dual-face package
// (served at /plugins/<entry-id>/client.js). Registers two keyed `tool.call.toolview`
// rows:
//   epcd_status     → TPE progress bar (+ per-round cost sparkline)
//   epcd_artifacts  → artifact gallery with 三视图 (俯视/轴测/侧视) tab switching
//
// The DeepSeek hero slogan is hidden HOST-side by epcd-brand.mjs (BRAND_CSS),
// so this module stays focused on the tool cards.

window.__ModuleLoader__.load({
  id: "epcd-ui-plugin",
  factory: (require) => {
    var module = { exports: {} };
    var exports = module.exports;
    Object.defineProperty(exports, Symbol.toStringTag, { value: "Module" });
    const React = require("react");
    var createRoot = null;
    try { createRoot = require("react-dom/client").createRoot; } catch (e) { createRoot = null; }

    function jsonFromBlock(block) {
      if (!block) return null;
      var content = Array.isArray(block.content) ? block.content : null;
      if (content) {
        for (var i = 0; i < content.length; i++) {
          var b = content[i];
          var txt = null;
          if (typeof b === "string") txt = b;
          else if (b && typeof b === "object") txt = (b.text !== undefined ? b.text : (b.output !== undefined ? b.output : b.content));
          if (typeof txt === "string") {
            try { var v2 = JSON.parse(txt); if (v2 && typeof v2 === "object") return v2; } catch (e) {}
          }
        }
      }
      var raw = null;
      if (typeof block.argsRaw === "string") raw = block.argsRaw;
      else if (block.call && typeof block.call.argsRaw === "string") raw = block.call.argsRaw;
      if (raw) { try { var v = JSON.parse(raw); if (v && typeof v === "object") return v; } catch (e) {} }
      return null;
    }

    function viewOf(img) {
      var s = (img && img.label ? img.label : "") + "|" + (img && img.path ? img.path : "");
      if (img && img.view) return img.view;
      if (/俯视|preview_top|_top/i.test(s)) return "top";
      if (/轴测|preview_iso|_iso/i.test(s)) return "iso";
      if (/侧视|preview_side|_side/i.test(s)) return "side";
      return null;
    }

    function ProgressBar(props) {
      var data = jsonFromBlock(props.block);
      var p = data && data.progress ? data.progress : data;
      if (!p || typeof p.total_rounds !== "number" || typeof p.done_rounds !== "number") {
        return React.createElement("div", { style: { padding: 12, fontSize: 13 } }, "等待 TPE 优化进度数据…");
      }
      var total = p.total_rounds;
      var done = p.done_rounds;
      var pct = total > 0 ? Math.round(Math.min(1, Math.max(0, done / total)) * 100) : 0;
      var statusText = p.status === "finished" ? "已完成" : (p.status === "paused" ? "已暂停" : (p.status === "canceled" ? "已取消" : "进行中"));
      var costText = typeof p.best_cost === "number" ? p.best_cost.toFixed(3) : "—";
      var rounds = Array.isArray(p.rounds) ? p.rounds : [];
      var spark = [];
      for (var i = 0; i < rounds.length; i++) {
        var r = rounds[i];
        if (r && typeof r.cost === "number") {
          var h = Math.max(3, Math.min(30, Math.abs(r.cost) * 30 + 3));
          spark.push(React.createElement("span", { key: i, title: "R" + (r.round_no != null ? r.round_no : (i + 1)) + " cost " + r.cost.toFixed(3), style: { flex: "1 1 auto", minWidth: 2, height: h + "px", backgroundColor: "#4c7ff0", borderRadius: 2 } }));
        }
      }
      var header = React.createElement("div", { style: { display: "flex", justifyContent: "space-between", marginBottom: 6, fontSize: 13 } },
        React.createElement("span", { style: { fontWeight: 600 } }, "TPE 优化进度 · " + statusText),
        React.createElement("span", null, done + " / " + total + " 轮")
      );
      var bar = React.createElement("div", { style: { height: 8, borderRadius: 4, background: "#eef0f3", overflow: "hidden" } },
        React.createElement("div", { style: { width: pct + "%", height: "100%", borderRadius: 4, background: "#4c7ff0", transition: "width .3s ease" } })
      );
      var meta = React.createElement("div", { style: { marginTop: 6, fontSize: 12 } }, "当前最优 cost " + costText);
      var children = [header, bar, meta];
      if (rounds.length) {
        children.push(React.createElement("div", { style: { display: "flex", gap: 2, alignItems: "flex-end", height: 32, marginTop: 8, padding: "0 4px" } }, spark));
      }
      return React.createElement("div", { style: { padding: "10px 12px", borderRadius: 12, border: "1px solid #e5e7eb" } }, children);
    }

    function ViewSwitcher(props) {
      var vws = props.views;
      var state = React.useState(null);
      var sel = state[0];
      var set = state[1];
      var order = ["top", "iso", "side"];
      var names = { top: "俯视", iso: "轴测", side: "侧视" };
      var found = {};
      for (var i = 0; i < vws.length; i++) { if (!found[vws[i].key]) found[vws[i].key] = vws[i]; }
      var keys = [];
      for (var j = 0; j < order.length; j++) { if (found[order[j]]) keys.push(order[j]); }
      var current = (sel && found[sel]) ? sel : (keys[0] || null);
      var cur = current ? found[current] : null;
      var tabs = keys.map(function (k) {
        var active = k === current;
        return React.createElement("button", { key: k, onClick: function () { set(k); }, style: {
          padding: "4px 10px", marginRight: 6, fontSize: 12, cursor: "pointer", borderRadius: 6,
          border: active ? "1px solid #4c7ff0" : "1px solid #e5e7eb", background: active ? "#4c7ff0" : "#f5f6f8",
          color: active ? "#ffffff" : "#333333", fontWeight: active ? 600 : 400
        } }, names[k]);
      });
      return React.createElement("div", { style: { marginBottom: 10 } },
        React.createElement("div", { style: { display: "flex", marginBottom: 6 } }, tabs),
        cur ? React.createElement("img", { src: cur.image, alt: names[current], style: { maxWidth: "100%", maxHeight: 320, borderRadius: 8, border: "1px solid #e5e7eb", display: "block" } }) : null,
        cur ? React.createElement("div", { style: { fontSize: 12, marginTop: 4 } }, cur.label) : null
      );
    }

    function ArtifactsView(props) {
      var data = jsonFromBlock(props.block);
      var arts = data && data.artifacts ? data.artifacts : [];
      if (!Array.isArray(arts) || arts.length === 0) {
        return React.createElement("div", { style: { padding: 12, fontSize: 13 } }, "暂无产物");
      }
      var views = [];
      var images = [];
      var others = [];
      for (var i = 0; i < arts.length; i++) {
        var a = arts[i];
        if (a && a.image) {
          var v = viewOf(a);
          if (v) views.push({ key: v, label: a.label || a.path, image: a.image });
          else images.push(a);
        } else others.push(a);
      }
      var kids = [];
      if (views.length >= 2) kids.push(React.createElement(ViewSwitcher, { key: "threeview", views: views }));
      else if (views.length === 1) images.unshift({ label: views[0].label, image: views[0].image, path: "" });
      for (var j = 0; j < images.length; j++) {
        var im = images[j];
        kids.push(React.createElement("div", { key: (im.path || im.label || ("img" + j)), style: { marginBottom: 10 } },
          React.createElement("img", { src: im.image, alt: im.label || "", style: { maxWidth: "100%", maxHeight: 320, borderRadius: 8, border: "1px solid #e5e7eb", display: "block" } }),
          React.createElement("div", { style: { fontSize: 12, marginTop: 4 } }, im.label || "")
        ));
      }
      for (var k = 0; k < others.length; k++) {
        var o = others[k];
        var key = (o && o.path) ? o.path : ("o" + k);
        if (o && o.error) {
          kids.push(React.createElement("div", { key: key, style: { fontSize: 12, color: "#c0392b", padding: "4px 0" } }, (o.label || key) + " · 读取失败: " + o.error));
        } else if (o && typeof o.text === "string") {
          kids.push(React.createElement("div", { key: key, style: { marginBottom: 10 } },
            React.createElement("div", { style: { fontSize: 12, fontWeight: 600, marginBottom: 4 } }, o.label || ""),
            React.createElement("pre", { style: { fontSize: 11, lineHeight: 1.5, whiteSpace: "pre-wrap", wordBreak: "break-word", maxHeight: 240, overflow: "auto", background: "#0f151a", color: "#e6e8eb", padding: 10, borderRadius: 8 } }, o.text)
          ));
        } else {
          kids.push(React.createElement("div", { key: key, style: { fontSize: 12, padding: "6px 8px", border: "1px solid #e5e7eb", borderRadius: 8, marginBottom: 6 } }, (o ? ((o.label || key) + " · " + o.kind) : "…")));
        }
      }
      return React.createElement("div", { style: { padding: "10px 12px", borderRadius: 12, border: "1px solid #e5e7eb" } },
        React.createElement("div", { style: { fontSize: 13, fontWeight: 600, marginBottom: 8 } }, "设计产物"),
        kids
      );
    }

    var VIEW_ORDER = ["top", "iso", "side"];
    var VIEW_NAMES = { top: "俯视", iso: "轴测", side: "侧视" };

    function classifyArtifacts(arts) {
      var views = [];
      var images = [];
      var texts = [];
      var files = [];
      for (var i = 0; i < arts.length; i++) {
        var a = arts[i];
        if (a && a.image) {
          var v = viewOf(a);
          if (v) views.push({ key: v, label: a.label || a.path, image: a.image, path: a.path });
          else images.push(a);
        } else if (a && typeof a.text === "string") {
          texts.push(a);
        } else {
          files.push(a);
        }
      }
      var byKey = {};
      for (var j = 0; j < views.length; j++) { if (!byKey[views[j].key]) byKey[views[j].key] = views[j]; }
      var ordered = [];
      for (var k = 0; k < VIEW_ORDER.length; k++) { if (byKey[VIEW_ORDER[k]]) ordered.push(byKey[VIEW_ORDER[k]]); }
      for (var m = 0; m < views.length; m++) {
        if (VIEW_ORDER.indexOf(views[m].key) < 0) ordered.push(views[m]);
      }
      return { views: ordered, images: images, texts: texts, files: files };
    }

    function Lightbox(props) {
      if (!props.item) return null;
      var im = React.createElement("div", {
        onClick: function (e) { e.stopPropagation(); props.onClose(); },
        style: { position: "fixed", inset: 0, zIndex: 1000, background: "rgba(10,13,18,0.86)", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", padding: 24, cursor: "zoom-out" }
      },
        React.createElement("img", { src: props.item.image, alt: props.item.label || "", style: { maxWidth: "96%", maxHeight: "88%", objectFit: "contain", borderRadius: 10, boxShadow: "0 10px 40px rgba(0,0,0,0.5)" } }),
        React.createElement("div", { style: { marginTop: 14, color: "#e6e8eb", fontSize: 13 } }, props.item.label || ""),
        React.createElement("div", { style: { marginTop: 6, color: "#9aa3ad", fontSize: 12 } }, "点击任意处关闭")
      );
      return im;
    }

    function GalleryPanel(props) {
      var sessionId = props.sessionId || null;
      var st = React.useState({ status: "loading", artifacts: [], error: null, ts: null });
      var state = st[0];
      var setState = st[1];
      var lb = React.useState(null);
      var lightbox = lb[0];
      var setLightbox = lb[1];
      var av = React.useState(null);
      var activeView = av[0];
      var setActiveView = av[1];

      React.useEffect(function () {
        var cancelled = false;
        function load() {
          if (!sessionId) return;
          fetch("/api/epcd-gallery?session=" + encodeURIComponent(sessionId))
            .then(function (r) { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); })
            .then(function (d) {
              if (cancelled) return;
              var arts = Array.isArray(d.artifacts) ? d.artifacts : [];
              setState({ status: arts.length ? "ready" : "empty", artifacts: arts, error: null, ts: d.ts || null });
            })
            .catch(function (e) {
              if (cancelled) return;
              setState({ status: "error", artifacts: [], error: String((e && e.message) || e), ts: null });
            });
        }
        load();
        var timer = window.setInterval(load, 3000);
        return function () { cancelled = true; window.clearInterval(timer); };
      }, [sessionId]);

      var rootStyle = {
        height: "100%", overflowY: "auto", padding: 16,
        boxSizing: "border-box", color: "#1f2329", background: "var(--dsw-alias-bg-layer-1, #ffffff)"
      };
      var head = React.createElement("div", { style: { display: "flex", alignItems: "baseline", justifyContent: "space-between", marginBottom: 14 } },
        React.createElement("div", { style: { fontSize: 15, fontWeight: 700 } }, "预览展示"),
        React.createElement("div", { style: { fontSize: 11, color: "#9aa3ad" } },
          state.ts ? ("更新于 " + new Date(state.ts).toLocaleTimeString()) : "")
      );

      if (state.status === "loading") {
        return React.createElement("div", { style: rootStyle }, head,
          React.createElement("div", { style: { fontSize: 13, color: "#68707a", padding: "24px 0" } }, "正在加载产物…"));
      }
      if (state.status === "error") {
        return React.createElement("div", { style: rootStyle }, head,
          React.createElement("div", { style: { fontSize: 13, color: "#c0392b", padding: "24px 0" } }, "加载失败：" + state.error));
      }
      if (state.status === "empty") {
        return React.createElement("div", { style: rootStyle }, head,
          React.createElement("div", { style: { fontSize: 13, color: "#68707a", padding: "24px 0", lineHeight: 1.7 } },
            "本任务暂无产物。", React.createElement("br"), "当一轮设计交付后（模型调用 epcd_artifacts），版图三视图 / S2P / GDS / 目标值会自动出现在这里。"));
      }

      var cls = classifyArtifacts(state.artifacts);
      var kids = [];

      // 三视图（top/iso/side）：tab 切换 + 大图，点击放大。
      if (cls.views.length) {
        var current = null;
        for (var vi = 0; vi < cls.views.length; vi++) {
          if (cls.views[vi].key === activeView) current = cls.views[vi];
        }
        if (!current) current = cls.views[0];
        var tabs = cls.views.map(function (vw) {
          var active = vw.key === current.key;
          return React.createElement("button", {
            key: vw.key,
            type: "button",
            onClick: function () { setActiveView(vw.key); },
            style: {
              padding: "5px 12px", marginRight: 6, fontSize: 12, cursor: "pointer", borderRadius: 6,
              border: active ? "1px solid #4c7ff0" : "1px solid #e5e7eb", background: active ? "#4c7ff0" : "var(--dsw-alias-bg-layer-2, #f5f6f8)",
              color: active ? "#ffffff" : "#333333", fontWeight: active ? 600 : 400
            }
          }, VIEW_NAMES[vw.key] || vw.label);
        });
        kids.push(React.createElement("div", { key: "threeview", style: { marginBottom: 16 } },
          React.createElement("div", { style: { display: "flex", marginBottom: 8 } }, tabs),
          React.createElement("img", {
            src: current.image,
            alt: current.label || "",
            onClick: function () { setLightbox(current); },
            style: { maxWidth: "100%", maxHeight: 460, borderRadius: 8, border: "1px solid #e5e7eb", display: "block", cursor: "zoom-in", boxShadow: "0 1px 4px rgba(0,0,0,0.08)" }
          }),
          React.createElement("div", { style: { fontSize: 12, color: "#68707a", marginTop: 6 } }, current.label || "")
        ));
      }

      // 其它单张图。
      for (var imi = 0; imi < cls.images.length; imi++) {
        var im = cls.images[imi];
        (function (img) {
          kids.push(React.createElement("div", { key: img.path || img.label || ("img" + imi), style: { marginBottom: 16 } },
            React.createElement("img", {
              src: img.image, alt: img.label || "",
              onClick: function () { setLightbox(img); },
              style: { maxWidth: "100%", maxHeight: 460, borderRadius: 8, border: "1px solid #e5e7eb", display: "block", cursor: "zoom-in" }
            }),
            React.createElement("div", { style: { fontSize: 12, color: "#68707a", marginTop: 6 } }, img.label || "")
          ));
        })(im);
      }

      // S2P / JSON / 文本。
      for (var ti = 0; ti < cls.texts.length; ti++) {
        var t = cls.texts[ti];
        kids.push(React.createElement("div", { key: (t.path || t.label || ("t" + ti)), style: { marginBottom: 16 } },
          React.createElement("div", { style: { fontSize: 12, fontWeight: 600, marginBottom: 6 } }, t.label || ""),
          React.createElement("pre", { style: { fontSize: 11, lineHeight: 1.5, whiteSpace: "pre-wrap", wordBreak: "break-word", maxHeight: 260, overflow: "auto", background: "#0f151a", color: "#e6e8eb", padding: 10, borderRadius: 8, margin: 0 } }, t.text)
        ));
      }

      // GDS / 其它文件 / 读取失败。
      for (var fi = 0; fi < cls.files.length; fi++) {
        var f = cls.files[fi];
        if (f && f.error) {
          kids.push(React.createElement("div", { key: f.path || ("f" + fi), style: { fontSize: 12, color: "#c0392b", padding: "6px 0" } }, (f.label || f.path) + " · 读取失败: " + f.error));
        } else if (f && f.kind === "gds") {
          kids.push(React.createElement("div", { key: f.path || ("f" + fi), style: { display: "flex", alignItems: "center", gap: 8, padding: "10px 12px", border: "1px solid #e5e7eb", borderRadius: 8, marginBottom: 8 } },
            React.createElement("span", { style: { fontWeight: 600, fontSize: 13 } }, f.label || "GDS"),
            React.createElement("span", { style: { fontSize: 12, color: "#68707a", wordBreak: "break-all" } }, f.path || "")
          ));
        } else {
          kids.push(React.createElement("div", { key: f.path || ("f" + fi), style: { fontSize: 12, padding: "8px 12px", border: "1px solid #e5e7eb", borderRadius: 8, marginBottom: 8 } }, (f.label || "文件") + " · " + (f.kind || "unknown")));
        }
      }

      return React.createElement("div", { style: rootStyle },
        head,
        React.createElement("div", null, kids),
        React.createElement(Lightbox, { item: lightbox, onClose: function () { setLightbox(null); } })
      );
    }

    var CFG_FIELDS = ["host", "port", "user", "identityFile", "pkg", "technology", "workDirRoot"];

    function ConfigPanel(props) {
      var sessionId = props.sessionId || null;
      var st = React.useState({ status: "loading", data: null, error: null });
      var state = st[0];
      var setState = st[1];
      var vst = React.useState({});
      var values = vst[0];
      var setValues = vst[1];
      var namest = React.useState("");
      var name = namest[0];
      var setName = namest[1];
      var sav = React.useState("none"); // none | saving | saved | error
      var saveState = sav[0];
      var setSaveState = sav[1];
      var smsg = React.useState("");
      var saveMsg = smsg[0];
      var setSaveMsg = smsg[1];

      React.useEffect(function () {
        var cancelled = false;
        function load() {
          if (!sessionId) return;
          fetch("/api/epcd-config?session=" + encodeURIComponent(sessionId))
            .then(function (r) { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); })
            .then(function (d) {
              if (cancelled) return;
              setState({ status: "ready", data: d, error: null });
              setName(d.active || "");
              var cfg = d.activeConfig || {};
              var next = {};
              for (var i = 0; i < CFG_FIELDS.length; i++) next[CFG_FIELDS[i]] = cfg[CFG_FIELDS[i]] || "";
              setValues(next);
            })
            .catch(function (e) {
              if (cancelled) return;
              setState({ status: "error", data: null, error: String((e && e.message) || e) });
            });
        }
        load();
        return function () { cancelled = true; };
      }, [sessionId]);

      function onField(field, val) {
        var next = {};
        for (var k in values) next[k] = values[k];
        next[field] = val;
        setValues(next);
      }

      function post(body) {
        setSaveState("saving");
        setSaveMsg("");
        return fetch("/api/epcd-config", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(Object.assign({ session: sessionId }, body))
        })
          .then(function (r) { return r.json(); })
          .then(function (d) {
            if (d.ok) {
              setSaveState("saved");
              setState({ status: "ready", data: d, error: null });
              setName(d.active || "");
              var cfg = d.activeConfig || {};
              var next = {};
              for (var i = 0; i < CFG_FIELDS.length; i++) next[CFG_FIELDS[i]] = cfg[CFG_FIELDS[i]] || "";
              setValues(next);
            } else {
              setSaveState("error");
            }
            setSaveMsg(d.ok ? "已完成" : (d.error || "操作失败"));
            return d;
          })
          .catch(function (e) {
            setSaveState("error");
            setSaveMsg(String((e && e.message) || e));
          });
      }

      function save() {
        post({ action: "save", name: name, config: values }).then(function (d) {
          if (d && d.ok) setSaveMsg("已保存配置 " + name);
        });
      }

      function activate(name2) {
        var next = {};
        var cfg = (state.data && state.data.configs && state.data.configs[name2]) || {};
        for (var i = 0; i < CFG_FIELDS.length; i++) next[CFG_FIELDS[i]] = cfg[CFG_FIELDS[i]] || "";
        setValues(next);
        setName(name2);
        post({ action: "activate", name: name2 });
      }

      function removeAt(target) {
        if (!target) return;
        if (!window.confirm("删除配置 \"" + target + "\"？此操作不可撤销。")) return;
        post({ action: "delete", name: target }).then(function (d) {
          if (d && d.ok) setSaveMsg("已删除配置 " + target + (d.active ? "，当前配置切到 " + d.active : ""));
          else if (d && d.error) setSaveMsg(d.error);
        });
      }

      function renameAt(target) {
        if (!target) return;
        var nn = window.prompt("重命名配置 \"" + target + "\" 为：", target);
        if (!nn) return;
        nn = nn.trim();
        if (!nn) return;
        if (nn === target) { setSaveMsg("新名与原名相同"); return; }
        post({ action: "rename", name: target, newName: nn }).then(function (d) {
          if (d && d.ok) setSaveMsg("已重命名为 " + nn);
          else if (d && d.error) setSaveMsg(d.error);
        });
      }

      function remove() {
        // 兼容旧的「删除」入口：删除当前编辑器选中的配置（与 chip 上删除一致）。
        removeAt(name);
      }

      function create() {
        var n = window.prompt("新建配置名（例如 zhubo-prod）：", "");
        if (!n) return;
        var cfg = {};
        for (var i = 0; i < CFG_FIELDS.length; i++) cfg[CFG_FIELDS[i]] = values[CFG_FIELDS[i]] || "";
        post({ action: "save", name: n, config: cfg }).then(function (d) {
          if (d && d.ok) setSaveMsg("已新建并切换配置 " + n);
        });
      }

      var rootStyle = { minWidth: 0, color: "#1f2329" };
      var cwdLine = !sessionId ? "未定位到项目" : (state.data && state.data.cwd ? ("项目目录：" + state.data.cwd) : "项目内 epcd-configs.json");
      var head = React.createElement("div", { style: { display: "flex", alignItems: "flex-start", marginBottom: 14 } },
        React.createElement("div", { style: { flex: 1, minWidth: 0 } },
          React.createElement("div", { style: { fontSize: 15, fontWeight: 700, marginBottom: 3 } }, "EPCD 项目配置"),
          React.createElement("div", { style: { fontSize: 11, color: "#9aa3ad", wordBreak: "break-all" } }, cwdLine)
        ),
        props.onClose ? React.createElement("button", {
          onClick: props.onClose,
          title: "关闭",
          "aria-label": "关闭",
          style: { flex: "none", marginLeft: 12, width: 28, height: 28, border: "1px solid #e5e7eb", borderRadius: 8, background: "transparent", color: "#68707a", cursor: "pointer", fontSize: 14, lineHeight: 1 }
        }, "✕") : null
      );

      if (!sessionId) {
        return React.createElement("div", { style: rootStyle }, head,
          React.createElement("div", { style: { fontSize: 13, color: "#68707a", padding: "12px 0" } },
            "当前没有打开的项目会话，无法定位项目配置（请先打开或新建一个项目会话）。"));
      }

      if (state.status === "loading") {
        return React.createElement("div", { style: rootStyle }, head,
          React.createElement("div", { style: { fontSize: 13, color: "#68707a", padding: "24px 0" } }, "正在加载配置…"));
      }
      if (state.status === "error") {
        return React.createElement("div", { style: rootStyle }, head,
          React.createElement("div", { style: { fontSize: 13, color: "#c0392b", padding: "24px 0" } }, "加载失败：" + state.error));
      }

      var d = state.data || {};
      var list = d.list || [];
      var cache = d.cache || {};
      var labels = d.labels || {};
      var fields = d.fields || CFG_FIELDS;

      // 配置条目：名称（点击切换/激活）+ 重命名 + 删除，三者各自独立、删的是该条目本身而非隐式选中态
      var itemBorder = "1px solid #e5e7eb";
      var selector = list.length
        ? list.map(function (k) {
            var isActive = k === (d.active || "");
            var nameBtn = React.createElement("button", {
              onClick: function () { activate(k); },
              title: "切换到此配置",
              style: {
                fontSize: 12, padding: "5px 10px", cursor: "pointer", border: "none", background: "transparent",
                color: isActive ? "#4c7ff0" : "#333", fontWeight: isActive ? 600 : 400
              }
            }, k);
            var ico = { fontSize: 12, padding: "5px 6px", cursor: "pointer", border: "none", background: "transparent", lineHeight: 1 };
            var renameBtn = React.createElement("button", {
              onClick: function () { renameAt(k); },
              title: "重命名此配置",
              style: Object.assign({}, ico, { color: "#4c7ff0" })
            }, "✎");
            var delBtn = React.createElement("button", {
              onClick: function () { removeAt(k); },
              title: "删除此配置",
              style: Object.assign({}, ico, { color: "#c0392b" })
            }, "✕");
            return React.createElement("span", {
              key: k,
              style: {
                display: "inline-flex", alignItems: "center", margin: "0 6px 6px 0",
                border: isActive ? "1px solid #4c7ff0" : itemBorder, borderRadius: 8, overflow: "hidden", background: "#f5f6f8"
              }
            }, nameBtn, renameBtn, delBtn);
          })
        : [React.createElement("span", { key: "none", style: { fontSize: 11, color: "#9aa3ad" } }, "暂无配置，请新建")];

      var toolbar = React.createElement("div", { style: { display: "flex", alignItems: "center", flexWrap: "wrap", marginBottom: 14 } },
        React.createElement("span", { style: { fontSize: 12, fontWeight: 600, marginRight: 8 } }, "当前配置：" + (d.active || "（无）")),
        selector,
        React.createElement("button", { onClick: create, style: btnStyle(false) }, "新建")
      );

      var fieldBlocks = fields.map(function (f) {
        var cur = values[f] || "";
        var chips = [];
        var seen = {};
        for (var ci = 0; ci < (cache[f] || []).length; ci++) {
          var cv = cache[f][ci];
          if (!cv || cv === cur || seen[cv]) continue;
          seen[cv] = true;
          (function (v) {
            chips.push(React.createElement("button", {
              key: v,
              onClick: function () { onField(f, v); },
              title: v,
              style: {
                maxWidth: 240, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
                fontSize: 11, padding: "3px 8px", margin: "0 6px 6px 0", cursor: "pointer",
                border: "1px solid #e5e7eb", borderRadius: 999, background: "#f5f6f8", color: "#333"
              }
            }, v));
          })(cv);
        }
        return React.createElement("div", { key: f, style: { marginBottom: 18, padding: "12px", border: "1px solid #ececf0", borderRadius: 10 } },
          React.createElement("div", { style: { display: "flex", alignItems: "baseline", marginBottom: 8 } },
            React.createElement("span", { style: { fontSize: 13, fontWeight: 600, marginRight: 8 } }, labels[f] || f),
            React.createElement("span", { style: { marginLeft: "auto", fontSize: 11, color: "#9aa3ad" } }, f)
          ),
          React.createElement("input", {
            value: cur,
            placeholder: "留空则缺省",
            onChange: function (e) { onField(f, e.target.value); },
            style: {
              width: "100%", boxSizing: "border-box", fontSize: 12, padding: "7px 10px",
              border: "1px solid #d5d9e0", borderRadius: 6, marginBottom: 8,
              background: "#fff", color: "#1f2329", fontFamily: "ui-monospace, SFMono-Regular, Consolas, monospace"
            }
          }),
          chips.length ? React.createElement("div", { style: { display: "flex", flexWrap: "wrap", alignItems: "center" } },
            React.createElement("span", { style: { fontSize: 11, color: "#9aa3ad", marginRight: 6 } }, "历史：" ),
            chips
          ) : null
        );
      });

      function btnStyle(danger) {
        var base = { fontSize: 12, padding: "5px 12px", marginLeft: 6, cursor: "pointer", borderRadius: 8 };
        if (danger) return Object.assign({}, base, { border: "1px solid #e5e7eb", background: "transparent", color: "#c0392b" });
        return Object.assign({}, base, { border: "1px solid #4c7ff0", background: "transparent", color: "#4c7ff0" });
      }

      var saveBtn = React.createElement("button", {
        onClick: save,
        disabled: saveState === "saving",
        style: {
          padding: "8px 16px", fontSize: 13, fontWeight: 600, cursor: saveState === "saving" ? "default" : "pointer",
          borderRadius: 8, border: "1px solid #4c7ff0", background: "#4c7ff0", color: "#fff", opacity: saveState === "saving" ? 0.6 : 1
        }
      }, saveState === "saving" ? "保存中…" : "保存修改");
      var statusNode = saveMsg ? React.createElement("span", { style: { marginLeft: 10, fontSize: 12, color: saveState === "error" ? "#c0392b" : "#1a7f37" } }, saveMsg) : null;

      return React.createElement("div", { style: rootStyle },
        head,
        toolbar,
        fieldBlocks,
        React.createElement("div", { style: { display: "flex", alignItems: "center", marginTop: 4 } }, saveBtn, statusNode),
        React.createElement("div", { style: { fontSize: 11, color: "#9aa3ad", marginTop: 10, lineHeight: 1.6 } },
          "说明：一套配置包含连接（主机/端口/用户/密钥）、EPCD 包根、工艺文件与工作目录。点击配置名切换生效；每套配置旁的 ✎ 重命名、✕ 删除（可删当前配置，删后自动切到剩余配置）；「保存修改」把字段写回当前选中配置，「新建」复制当前值另存一份。")
      );
    }

    // ── 侧边栏入口（DOM 注入，位于 SSH 之下）+ 配置弹窗 ─────────────────────────

    var epcdSessions = null;      // ISessions service（apply 里设置）
    var modalRoot = null;         // react-dom/client Root
    var modalContainer = null;    // backdrop 元素

    var EPCD_ENTRY_ICON = '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><line x1="4" y1="21" x2="4" y2="14"/><line x1="4" y1="10" x2="4" y2="3"/><line x1="12" y1="21" x2="12" y2="12"/><line x1="12" y1="8" x2="12" y2="3"/><line x1="20" y1="21" x2="20" y2="16"/><line x1="20" y1="12" x2="20" y2="3"/><line x1="1" y1="14" x2="7" y2="14"/><line x1="9" y1="8" x2="15" y2="8"/><line x1="17" y1="16" x2="23" y2="16"/></svg>';

    function currentSessionId() {
      try {
        if (epcdSessions && epcdSessions.list) {
          var snap = epcdSessions.list.getSnapshot();
          return snap && snap.current ? snap.current : null;
        }
      } catch (e) { /* ignore */ }
      return null;
    }

    function sidebarRootEl() {
      try {
        var column = document.querySelector('[data-pane="sidebar"], [class*="sidebarCol"]');
        if (!column) return null;
        var logoOwner = column.querySelector('[class*="logoRow"]');
        if (logoOwner && logoOwner.parentElement) return logoOwner.parentElement;
        return column.firstElementChild || null;
      } catch (e) { return null; }
    }

    function newSessionButtonEl(root) {
      if (!root) return null;
      try {
        var nested = root.querySelector('button[class*="newSession"]');
        if (nested) return nested;
        for (var i = 0; i < root.children.length; i++) {
          if (root.children[i].tagName === "BUTTON") return root.children[i];
        }
      } catch (e) { /* ignore */ }
      return null;
    }

    function mountSidebarEntry() {
      if (typeof document === "undefined") return function () {};
      if (document.querySelector('[data-dsh-epcd-config-entry]')) return function () {};

      var entry = document.createElement("button");
      entry.type = "button";
      entry.setAttribute("data-dsh-epcd-config-entry", "");
      entry.setAttribute("data-dsh-plugin", "epcd");
      entry.setAttribute("data-dsh-part", "sidebar-entry");
      entry.className = "dsh-epcd-entry";
      entry.setAttribute("aria-label", "EPCD 配置");
      entry.setAttribute("title", "EPCD 项目配置");
      var icon = document.createElement("span");
      icon.className = "dsh-epcd-entry-icon";
      icon.innerHTML = EPCD_ENTRY_ICON;
      var label = document.createElement("span");
      label.className = "dsh-epcd-entry-label";
      label.textContent = "EPCD 配置";
      entry.append(icon, label);
      entry.addEventListener("click", function () { toggleConfigModal(); });

      var root = null;
      var placed = false;
      var familySelectors = '[data-dsh-taskboard-entry], [data-dsh-ssh-entry], [data-dsh-epcd-config-entry]';

      function place() {
        if (root && !root.isConnected) { rootObserver.disconnect(); root = null; placed = false; }
        if (placed) {
          if (document.body.contains(entry)) return;
          rootObserver.disconnect();
          root = null;
          placed = false;
        }
        if (!root) root = sidebarRootEl();
        if (!root) return;
        var button = newSessionButtonEl(root);
        if (!button) return;
        if (entry.parentElement !== root) {
          var row = button.closest('[class*="logoRow"]');
          var base = (row && row.parentElement === root) ? row : button;
          var family = Array.prototype.filter.call(root.children, function (el) {
            return el instanceof HTMLElement && el.matches(familySelectors);
          });
          var anchor = family.length > 0 ? family[family.length - 1].nextElementSibling : base.nextElementSibling;
          root.insertBefore(entry, anchor);
        }
        placed = true;
        rootObserver.observe(root, { childList: true, subtree: true });
      }

      var waitObserver = new MutationObserver(function () { place(); });
      waitObserver.observe(document.body, { childList: true, subtree: true });
      var rootObserver = new MutationObserver(function () {
        if (!root || !root.isConnected) { placed = false; place(); return; }
        if (!root.contains(entry)) place();
      });
      place();

      return function () {
        waitObserver.disconnect();
        rootObserver.disconnect();
        entry.remove();
      };
    }

    function openConfigModal() {
      if (modalContainer || typeof document === "undefined" || !createRoot) return;
      var backdrop = document.createElement("div");
      backdrop.className = "dsh-epcd-modal-backdrop";
      var modal = document.createElement("div");
      modal.className = "dsh-epcd-modal";
      backdrop.appendChild(modal);
      backdrop.addEventListener("click", function (e) { if (e.target === backdrop) closeConfigModal(); });
      document.body.appendChild(backdrop);
      modalContainer = backdrop;
      modalRoot = createRoot(modal);
      var sessionId = currentSessionId();
      function close() { closeConfigModal(); }
      modalRoot.render(React.createElement(ConfigPanel, { sessionId: sessionId, onClose: close }));
      var e = document.querySelector('[data-dsh-epcd-config-entry]');
      if (e) e.dataset.active = "true";
    }

    function closeConfigModal() {
      try { if (modalRoot) modalRoot.unmount(); } catch (e) { /* ignore */ }
      modalRoot = null;
      try { if (modalContainer && modalContainer.parentElement) modalContainer.parentElement.removeChild(modalContainer); } catch (e) { /* ignore */ }
      modalContainer = null;
      var e = document.querySelector('[data-dsh-epcd-config-entry]');
      if (e) delete e.dataset.active;
    }

    function toggleConfigModal() {
      if (modalContainer) { closeConfigModal(); return; }
      openConfigModal();
    }

    function injectStyles() {
      if (typeof document === "undefined") return function () {};
      var style = document.createElement("style");
      style.id = "dsh-epcd-config-style";
      style.textContent = [
        ".dsh-epcd-entry{box-sizing:border-box;display:flex;align-items:center;gap:10px;width:100%;min-height:36px;padding:0 10px;background:transparent;border:none;border-radius:8px;color:var(--dsw-alias-label-secondary);cursor:pointer;font-size:13px;white-space:nowrap}",
        ".dsh-epcd-entry:hover{background:var(--dsw-alias-interactive-bg-hover);color:var(--dsw-alias-label-primary)}",
        ".dsh-epcd-entry[data-active]{background:var(--dsw-alias-interactive-bg-active);color:var(--dsw-alias-label-primary);font-weight:600}",
        ".dsh-epcd-entry-icon{display:inline-flex;align-items:center;justify-content:center;width:24px;height:24px;flex:none}",
        ".dsh-epcd-entry-icon svg{display:block;width:18px;height:18px}",
        ".dsh-epcd-entry-label{overflow:hidden;text-overflow:ellipsis}",
        ":is([data-dsh-frame][data-sidebar-collapsed],[data-sidebar-collapsed]) .dsh-epcd-entry{justify-content:center;padding:0;width:36px;min-height:36px;margin:0 auto 12px;border-radius:50%}",
        ":is([data-dsh-frame][data-sidebar-collapsed],[data-sidebar-collapsed]) .dsh-epcd-entry-label{display:none}",
        ".dsh-epcd-modal-backdrop{position:fixed;inset:0;z-index:9999;display:flex;align-items:center;justify-content:center;padding:24px;box-sizing:border-box;background:rgba(0,0,0,.4)}",
        ".dsh-epcd-modal{width:min(560px,100%);max-height:calc(100vh - 48px);overflow-y:auto;background:var(--dsw-alias-bg-base,#fff);border:1px solid var(--dsw-alias-border-l2,#e5e7eb);border-radius:14px;padding:18px 20px;box-shadow:0 12px 40px rgba(0,0,0,.25);color:var(--dsw-alias-label-primary,#1f2329)}"
      ].join("\n");
      document.head.appendChild(style);
      return function () { if (style.parentElement) style.parentElement.removeChild(style); };
    }

    function apply(ctx) {
      try { epcdSessions = ctx.sessions || ctx.get("sessions") || null; } catch (e) { epcdSessions = null; }

      ctx.slots.inject("tool.call.toolview", () => ctx.slots.register({ name: "tool.call.toolview", key: "epcd_status" }, ProgressBar));
      ctx.slots.inject("tool.call.toolview", () => ctx.slots.register({ name: "tool.call.toolview", key: "epcd_artifacts" }, ArtifactsView));
      ctx.slots.inject("conversation.view", () => ctx.slots.register({
        name: "conversation.view",
        id: "epcd-gallery",
        order: 20,
        label: "预览展示",
        inject: (sessionId) => ({ sessionId })
      }, GalleryPanel));

      var disposers = [];
      try {
        disposers.push(injectStyles());
        disposers.push(mountSidebarEntry());
      } catch (err) {
        console.warn("[epcd-ui] sidebar mount failed:", err);
      }
      ctx.effect(() => () => {
        closeConfigModal();
        for (var i = 0; i < disposers.length; i++) { try { disposers[i](); } catch (e) { /* ignore */ } }
      }, "epcd-ui: config sidebar entry + modal");
    }

    exports.name = "epcd-ui-client";
    exports.inject = ["slots", "sessions"];
    exports.apply = apply;
    return module.exports;
  }
});