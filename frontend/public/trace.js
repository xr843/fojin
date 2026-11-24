// fojin.ai 首页「这段话，出自佛经吗？」——把一段文字切成句子，分批送
// POST https://fojin.app/api/verify/trace（一次最多 8 句），边查边显示。直接跨域请求
// fojin.app（CORS 允许 fojin.ai），限流按每位访客自己的 IP 计；经 fojin.ai 边缘脚本
// 代转时所有访客共用边缘脚本的出口 IP（2026-11-22 实测）。
// 每句的判定与 /verify 页同一套（app/services/claim_check.py）：
//   sutra 出自佛经 · not_sutra 出自论/注疏/祖师著作… · variant 用字略异
//   partial 部分见于藏经 · absent 藏经中未见
// 外部文件而非内联脚本：fojin.ai 的 CSP 不允许内联脚本。
(function () {
  "use strict";

  var API = "https://fojin.app/api/verify/trace";
  var BATCH = 8;            // 与后端 TRACE_MAX_SENTENCES 一致
  var MAX_SENTENCES = 40;
  var MAX_SENTENCE_CHARS = 200;
  var SHARE_MAX_CHARS = 600; // 更长的文字放进链接会超出常见的网址长度

  var CLASS_LABEL = {
    sutra: "佛经", vinaya: "律典", treatise: "论典", commentary: "注疏",
    school: "宗派与祖师著作", history: "史传", apocrypha: "疑伪经",
    later: "后世注疏、语录", unknown: "其他典籍"
  };

  var EXAMPLES = {
    fake: "佛说：一切有为法，如梦幻泡影，看开便是福。一切都是最好的安排。前世五百次的回眸，才换来今生的一次擦肩而过。",
    ai: "《金刚经》说：“应无所住而生其心。”意思是心不执着于任何境界。经中又说：“凡所有相，皆是虚妄，若见诸相非相，则见如来。”佛陀还说过：“放下执念，便得自在。”",
    sutra: "观自在菩萨，行深般若波罗蜜多时，照见五蕴皆空，度一切苦厄。舍利子，色不异空，空不异色，色即是空，空即是色，受想行识，亦复如是。"
  };

  var form = document.getElementById("trace-form");
  var input = document.getElementById("trace-text");
  var go = document.getElementById("trace-go");
  var count = document.getElementById("trace-count");
  var status = document.getElementById("status");
  var summary = document.getElementById("summary");
  var list = document.getElementById("result");
  var share = document.getElementById("share");
  var shareBtn = document.getElementById("share-btn");
  if (!form || !input) return;

  function track(name, data) {
    try { if (window.umami && window.umami.track) window.umami.track(name, data); } catch (e) {}
  }

  function hanCount(s) { return (s.match(/[㐀-鿿]/g) || []).length; }

  // 去掉 Markdown 记号与 AI 回答里的【《经名》第N卷】引注，只留要核对的文字。
  function clean(line) {
    return line
      .replace(/【[^】]{0,80}】/g, "")
      // 从电子书、论文里复制来的脚注编号：「元明1，」「六师异辙（1）」——
      // 夹在汉字和标点之间的数字会让整句对不上原文。「第3卷」这种后面接汉字的不动。
      .replace(/[（(]\d{1,3}[）)]/g, "")
      // CBETA 网页版的标记符号（◥ 段首、※ 校注）不是正文
      .replace(/[◥◤◣◢◆◇■□▲△▼▽○●◎※]/g, "")
      .replace(/([㐀-鿿])\d{1,3}(?=[，。；：、！？,.;:!?」』”’]|$)/g, "$1")
      .replace(/^\s*(#{1,6}|>|[-*+]|\d+[.、)])\s*/, "")
      .replace(/[*_`]+/g, "")
      .trim();
  }

  // 按换行与句末标点切句；过长的句子再按逗号切开，保证每句 ≤ 200 字。
  // 从 PDF、电子书复制来的文字常在句中硬换行（「宗謂異部所崇之理，輪謂顯\n能摧之用」），
  // 按行切会把一句切成两半、两半都对不上原文。前一行没以句末标点收尾、下一行
  // 也不是 Markdown 标题或列表项时，把两行接回一句。
  var LIST_MARK = /^\s*(#{1,6}\s|>|[-*+]\s|\d+[.、)]\s?)/;
  var ENDS_SENTENCE = /[。！？；：!?;:」』”’）)]\s*$/;
  function joinWrappedLines(text) {
    var lines = text.split(/\r?\n/), out = [];
    lines.forEach(function (line) {
      var prev = out.length ? out[out.length - 1] : null;
      if (prev && prev.trim() && line.trim() && !ENDS_SENTENCE.test(prev) &&
          !LIST_MARK.test(prev) && !LIST_MARK.test(line)) {
        out[out.length - 1] = prev.replace(/\s+$/, "") + line.trim();
      } else {
        out.push(line);
      }
    });
    return out.join("\n");
  }

  function splitSentences(text) {
    var out = [];
    joinWrappedLines(text).split(/\n+/).forEach(function (raw) {
      var line = clean(raw);
      if (!line) return;
      var parts = line.match(/[^。！？；!?;]+[。！？；!?;]?[”」』’"]?/g) || [line];
      parts.forEach(function (p) {
        p = p.trim();
        while (p.length > MAX_SENTENCE_CHARS) {
          var cut = p.lastIndexOf("，", MAX_SENTENCE_CHARS);
          if (cut < 20) cut = MAX_SENTENCE_CHARS - 1;
          out.push(p.slice(0, cut + 1));
          p = p.slice(cut + 1).trim();
        }
        if (p) out.push(p);
      });
    });
    return out;
  }

  // 引语前缀（「佛说：」「经云：」）由后端判断：先整句核对（「論曰：」常是原文的一部分），
  // 整句找不到才去掉前缀重查，并在 item.prefix 里告诉页面——这里只负责把它灰显。
  function bodyOf(item) {
    var p = item.prefix || "";
    return p && item.text.indexOf(p) === 0 ? item.text.slice(p.length) : item.text;
  }

  function el(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text != null) n.textContent = text;
    return n;
  }

  function sourceLink(src, close) {
    var title = src.title_zh || src.cbeta_id || "原典";
    var label = "《" + title + "》" + (src.juan_num ? "卷" + src.juan_num : "");
    if (!src.reader_url) return el("span", null, label);
    var a = el("a", null, label);
    a.href = src.reader_url + (src.reader_url.indexOf("?") < 0 ? "?" : "&") + "utm_source=fojin.ai&utm_medium=trace";
    a.target = "_blank";
    a.rel = "noopener";
    if (close) a.title = "藏经原文与这句用字略有不同";
    return a;
  }

  function firstSource(result) {
    var segs = result.segments || [];
    for (var i = 0; i < segs.length; i++) {
      if (segs[i].found && segs[i].sources && segs[i].sources.length) return { src: segs[i].sources[0] };
      if (segs[i].close) return { src: segs[i].close, close: true };
    }
    return null;
  }

  function tagText(result) {
    switch (result.verdict) {
      case "sutra": return "出自佛经";
      case "not_sutra": return "出自" + (CLASS_LABEL[result.source_class] || "其他典籍");
      case "variant": return "经中有此句，用字略异";
      case "partial": return "部分见于藏经";
      default: return "藏经中未见";
    }
  }

  function renderItem(li, item) {
    var prefix = item.prefix || "";
    li.className = "";
    li.textContent = "";
    if (!item.result) {
      li.className = "k-skip";
      li.appendChild(el("div", "s", item.text));
      return "skip";
    }
    var r = item.result;
    li.className = "k-" + r.verdict;
    var s = el("div", "s");
    if (prefix) s.appendChild(el("span", "pre", prefix));
    if (r.verdict === "partial") {
      // 分句着色：找到的照常显示，藏经中找不到的加虚线、变灰。在原句里按顺序
      // 定位每个分句，保留原来的标点；定位不到（分句是并接过的碎片）就逐段拼出。
      var text = bodyOf(item), cursor = 0, ok = true, pieces = [];
      (r.segments || []).forEach(function (seg) {
        var at = text.indexOf(seg.text, cursor);
        if (at < 0) { ok = false; return; }
        if (at > cursor) pieces.push([text.slice(cursor, at), true]);
        pieces.push([seg.text, seg.found]);
        cursor = at + seg.text.length;
      });
      if (ok) {
        if (cursor < text.length) pieces.push([text.slice(cursor), true]);
      } else {
        pieces = [];
        (r.segments || []).forEach(function (seg, i) {
          if (i > 0) pieces.push(["，", true]);
          pieces.push([seg.text, seg.found]);
        });
      }
      pieces.forEach(function (p) { s.appendChild(el("span", p[1] ? null : "miss", p[0])); });
    } else {
      s.appendChild(document.createTextNode(bodyOf(item)));
    }
    li.appendChild(s);
    var meta = el("div", "meta");
    meta.appendChild(el("span", "tag", tagText(r)));
    var first = firstSource(r);
    if (first && r.verdict !== "absent") meta.appendChild(sourceLink(first.src, first.close));
    if (r.verdict !== "absent") {
      var ask = el("a", "ask", "问小津这句什么意思");
      ask.href = "https://fojin.app/chat?send=1&utm_source=fojin.ai&utm_medium=trace&q=" +
        encodeURIComponent("请解释这句话的意思与出处：" + item.text);
      ask.target = "_blank";
      ask.rel = "noopener";
      ask.addEventListener("click", function () { track("trace_ask", { verdict: r.verdict }); });
      meta.appendChild(ask);
    }
    li.appendChild(meta);
    return r.verdict;
  }

  // 非佛经出处按类别分开写，与卡片标签同一套叫法（「出自论典」「出自注疏」…）。
  // 早先汇总把它们并成「论疏或祖师著作」，卡片却写「出自论典」（2026-11-24 用户截图）。
  var CLASS_ORDER = ["vinaya", "treatise", "commentary", "school", "history", "apocrypha", "later", "unknown"];

  function renderSummary(tally, total, byClass) {
    var found = (tally.sutra || 0) + (tally.not_sutra || 0);
    var parts = [];
    parts.push("共 " + total + " 句");
    if (tally.sutra) parts.push("<b>" + tally.sutra + "</b> 句出自佛经");
    CLASS_ORDER.forEach(function (c) {
      if (byClass[c]) parts.push("<b>" + byClass[c] + "</b> 句出自" + CLASS_LABEL[c]);
    });
    if (tally.variant) parts.push("<b>" + tally.variant + "</b> 句经中有、用字略异");
    if (tally.partial) parts.push("<b>" + tally.partial + "</b> 句只有部分见于藏经");
    // 「未见」最容易被读成「伪造」：只在结果里真有「未见」时，就地提醒一句
    // （原先是页面底部一段常驻说明，全部找到时多余、有未见时又常没人看到；2026-11-24）。
    if (tally.absent) parts.push("<b>" + tally.absent + "</b> 句藏经中未见（未见不等于伪造，可能是改写或出自未收录的典籍）");
    summary.innerHTML = parts.join("，") + "。";
    summary.hidden = false;
    return found;
  }

  function sleep(ms) { return new Promise(function (r) { setTimeout(r, ms); }); }

  // prefer：上一批的主出处（上一次响应的 dominant）。一段原文跨批时，夹在中间的
  // 常见短句（「所以者何？」）仍按这段原文认出处，而不是认到最早用这几个字的经。
  function post(sentences, attempt, prefer) {
    var payload = { sentences: sentences };
    if (prefer) payload.prefer = prefer;
    return fetch(API, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(payload)
    }).then(function (res) {
      if (res.status === 429 && attempt < 4) {
        var wait = parseInt(res.headers.get("retry-after") || "15", 10);
        if (!(wait > 0 && wait < 120)) wait = 15;
        status.textContent = "查询较多，" + wait + " 秒后继续……";
        return sleep(wait * 1000).then(function () { return post(sentences, attempt + 1, prefer); });
      }
      if (!res.ok) throw new Error("http " + res.status);
      return res.json();
    });
  }

  // ── 原文里连成一段的句子，合成一张卡片 ────────────────────────────────
  // 每句出处链接带着它在原文里的起止（hl=起-止）。相邻几句出自同一卷、位置首尾
  // 相接（中间至多隔几个标点），就是原文里连着的一段：合成一张卡片，链接高亮整段。
  var RUN_GAP = 4;

  function locOf(item) {
    var r = item && item.result;
    if (!r || (r.verdict !== "sutra" && r.verdict !== "not_sutra") || !r.segments || r.segments.length !== 1) return null;
    var seg = r.segments[0];
    if (!seg.found || !seg.sources || !seg.sources.length || !seg.sources[0].reader_url) return null;
    var u;
    try { u = new URL(seg.sources[0].reader_url); } catch (e) { return null; }
    var m = /^(\d+)-(\d+)$/.exec(u.searchParams.get("hl") || "");
    if (!m) return null;
    return { key: u.pathname + "|" + u.searchParams.get("juan"), first: +m[1], last: +m[2], url: u, src: seg.sources[0] };
  }

  function renderRun(lis, results, locs, i, j) {
    var head = locs[i];
    var li = lis[i];
    li.className = "k-" + results[i].result.verdict + " run";
    li.textContent = "";
    var s = el("div", "s");
    var whole = "";
    for (var k = i; k <= j; k++) {
      var piece = results[k].text;
      whole += piece;
      s.appendChild(document.createTextNode(piece));
    }
    li.appendChild(s);
    var meta = el("div", "meta");
    meta.appendChild(el("span", "tag", tagText(results[i].result)));
    var url = new URL(head.url.href);
    url.searchParams.set("hl", head.first + "-" + locs[j].last);
    meta.appendChild(sourceLink(Object.assign({}, head.src, { reader_url: url.href })));
    meta.appendChild(el("span", "runinfo", "第 " + (i + 1) + "–" + (j + 1) + " 句，原文连成一段"));
    var ask = el("a", "ask", "问小津这段什么意思");
    ask.href = "https://fojin.app/chat?send=1&utm_source=fojin.ai&utm_medium=trace&q=" +
      encodeURIComponent("请解释这段话的意思与出处：" + whole.slice(0, 300));
    ask.target = "_blank";
    ask.rel = "noopener";
    ask.addEventListener("click", function () { track("trace_ask", { verdict: "run" }); });
    meta.appendChild(ask);
    li.appendChild(meta);
    var det = el("details", "each");
    det.appendChild(el("summary", null, "逐句查看"));
    var ol = el("ol");
    for (var n = i; n <= j; n++) ol.appendChild(el("li", null, results[n].text));
    det.appendChild(ol);
    li.appendChild(det);
    for (var r = i + 1; r <= j; r++) lis[r].remove();
  }

  function mergeRuns(lis, results) {
    var locs = results.map(locOf);
    var merged = 0;
    var i = 0;
    while (i < locs.length) {
      if (!locs[i]) { i++; continue; }
      var j = i;
      while (j + 1 < locs.length && locs[j + 1] && locs[j + 1].key === locs[i].key &&
             locs[j + 1].first > locs[j].last && locs[j + 1].first - locs[j].last - 1 <= RUN_GAP) j++;
      if (j > i) {
        renderRun(lis, results, locs, i, j);
        merged += j - i + 1;
      }
      i = j + 1;
    }
    return merged;
  }

  var running = false;

  function run(text, fromLink) {
    if (running) return;
    var sentences = splitSentences(text);
    var dropped = 0;
    if (sentences.length > MAX_SENTENCES) {
      dropped = sentences.length - MAX_SENTENCES;
      sentences = sentences.slice(0, MAX_SENTENCES);
    }
    list.textContent = "";
    summary.hidden = true;
    share.hidden = true;
    if (!sentences.length || hanCount(text) < 4) {
      status.textContent = "太短了，请至少输入四个汉字。";
      return;
    }
    running = true;
    go.disabled = true;
    track("trace_submit", { n: sentences.length, link: fromLink ? 1 : 0 });

    var items = sentences.map(function (t) {
      var li = el("li", "pending");
      li.appendChild(el("div", "s", t));
      list.appendChild(li);
      return li;
    });
    var tally = {};
    var byClass = {};
    var done = 0;
    var prefer = null;
    var results = new Array(sentences.length);
    status.textContent = "正在核对 0 / " + sentences.length + " 句……";

    var chain = Promise.resolve();
    for (var b = 0; b < sentences.length; b += BATCH) {
      (function (start) {
        chain = chain.then(function () {
          return post(sentences.slice(start, start + BATCH), 0, prefer).then(function (data) {
            prefer = data.dominant || prefer;
            (data.items || []).forEach(function (item, j) {
              results[start + j] = item;
              var kind = renderItem(items[start + j], item);
              if (kind !== "skip") tally[kind] = (tally[kind] || 0) + 1;
              if (kind === "not_sutra") {
                var c = CLASS_LABEL[item.result.source_class] ? item.result.source_class : "unknown";
                byClass[c] = (byClass[c] || 0) + 1;
              }
            });
            done = Math.min(start + BATCH, sentences.length);
            status.textContent = "正在核对 " + done + " / " + sentences.length + " 句……";
          });
        });
      })(b);
    }
    chain.then(function () {
      var checked = Object.keys(tally).reduce(function (n, k) { return n + tally[k]; }, 0);
      var found = renderSummary(tally, checked, byClass);
      var merged = mergeRuns(items, results);
      if (merged) track("trace_merge", { n: merged });
      status.textContent = dropped ? "只核对了前 " + MAX_SENTENCES + " 句，其余 " + dropped + " 句请分开再贴。" : "";
      if (text.length <= SHARE_MAX_CHARS) share.hidden = false;
      track("trace_done", { n: checked, found: found, absent: tally.absent || 0, partial: tally.partial || 0 });
    }).catch(function () {
      status.textContent = "核对中断了，请稍后再试。已核对的句子保留在下面。";
      items.forEach(function (li) { if (li.className === "pending") li.className = "k-skip"; });
      track("trace_error", {});
    }).then(function () {
      running = false;
      go.disabled = false;
    });
  }

  function updateCount() {
    var n = input.value.trim() ? splitSentences(input.value).length : 0;
    count.textContent = n ? "约 " + n + " 句" + (n > MAX_SENTENCES ? "（只核对前 " + MAX_SENTENCES + " 句）" : "") : "";
  }

  input.addEventListener("input", updateCount);
  form.addEventListener("submit", function (e) {
    e.preventDefault();
    var text = input.value.trim();
    // 不把文字写进地址栏：页面装着访问统计，网址变化会被记成一次访问，贴进来的文字
    // （可能是私人的）就进了统计库（2026-11-22 查实 151 条）。分享链接只在点「复制
    // 这次核对的链接」时生成，复制到剪贴板。
    run(text, false);
  });

  document.querySelectorAll("[data-example]").forEach(function (b) {
    b.addEventListener("click", function () {
      var key = b.getAttribute("data-example");
      input.value = EXAMPLES[key] || "";
      updateCount();
      track("trace_example", { which: key });
      form.requestSubmit ? form.requestSubmit() : form.dispatchEvent(new Event("submit", { cancelable: true }));
    });
  });

  if (shareBtn) {
    shareBtn.addEventListener("click", function () {
      var url = location.origin + location.pathname + "?q=" + encodeURIComponent(input.value.trim());
      var done = function () {
        shareBtn.textContent = "链接已复制";
        setTimeout(function () { shareBtn.textContent = "复制这次核对的链接"; }, 1600);
      };
      if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(url).then(done, function () {});
      track("trace_share", {});
    });
  }

  // 分享链接：?q= 带进来的文字直接核对。
  // 分享链接：?q= 带进来的文字直接核对，并立刻把网址清干净——本脚本先于统计脚本
  // 执行（同为 defer，排在前面），统计记下的就是不带文字的 fojin.ai/。
  var q = new URLSearchParams(location.search).get("q");
  if (q) {
    try { history.replaceState(null, "", location.pathname); } catch (err) {}
    input.value = q.slice(0, 3000);
    updateCount();
    run(input.value.trim(), true);
  }
})();
