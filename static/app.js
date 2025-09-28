// 日本語コメント：API を叩いて JSON を受け取り、テンプレに差し込む

document.addEventListener("DOMContentLoaded", () => {
  const form = document.getElementById("gen-form");
  const term = document.getElementById("term");
  const lang = document.getElementById("lang");
  const tone = document.getElementById("tone");
  const statusEl = document.getElementById("status");
  const page = document.getElementById("page");

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const payload = {
      term: term.value.trim(),
      lang: lang.value,
      tone: tone.value,
    };
    if (!payload.term) {
      statusEl.textContent = "単語を入れてください。";
      return;
    }
    statusEl.textContent = "生成中…（クラウドのはるか彼方でバズワードが攪拌されています）";

    try {
      const res = await fetch("/api/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.error || `HTTP ${res.status}`);
      }
      const spec = await res.json();
      render(spec);
      statusEl.textContent = "生成完了。";
    } catch (err) {
      console.error(err);
      statusEl.textContent = "生成に失敗しました。コンソールを確認してください。";
    }
  });

  /** 日本語コメント：受け取った JSON をレイアウトに挿入する（innerHTML は使わず XSS を回避） */
  function render(spec) {
    page.innerHTML = "";

    // タイトル
    const h1 = el("div", { className: "h1" },
      el("h2", {}, txt(spec.service_name || "Unnamed Service")),
      el("span", { className: "pill" }, txt("Fictional / Parody"))
    );
    const tagline = el("p", { className: "tagline" }, txt(spec.tagline || ""));

    // サマリ & ハイライト
    const summaryCard = el("div", { className: "card" },
      el("h3", {}, txt(getLang() === "ja" ? "概要" : "Overview")),
      el("p", {}, txt(spec.summary || "")));

    const highlightsCard = el("div", { className: "card" },
      el("h3", {}, txt(getLang() === "ja" ? "ハイライト" : "Highlights")),
      list(spec.highlights || [])
    );

    const kv = el("div", { className: "kv" }, summaryCard, highlightsCard);

    // 機能
    const features = section(getLang() === "ja" ? "主な機能" : "Key Features", list(spec.features || []));

    // 連携
    const integrations = section(getLang() === "ja" ? "統合" : "Integrations", list(spec.integrations || []));

    // 導入手順
    const steps = section(getLang() === "ja" ? "はじめる" : "Getting Started", list(spec.getting_started || []));

    // 料金
    const pricing = section(getLang() === "ja" ? "料金" : "Pricing", list(spec.pricing || []));

    // CLI
    const cli = el("div", { className: "section" },
      el("h3", {}, txt(getLang() === "ja" ? "CLI 例" : "CLI Example")),
      code(spec.sample_cli || "")
    );

    // FAQ
    const faqWrap = el("div", { className: "section card" },
      el("h3", {}, txt("FAQ")));
    (spec.faqs || []).forEach(item => {
      const q = el("p", { style: "font-weight:700;margin-bottom:4px" }, txt((item.q || "")));
      const a = el("p", { style: "margin-top:0" }, txt((item.a || "")));
      faqWrap.appendChild(q); faqWrap.appendChild(a);
    });

    page.appendChild(h1);
    page.appendChild(tagline);
    page.appendChild(kv);
    page.appendChild(features);
    page.appendChild(integrations);
    page.appendChild(steps);
    page.appendChild(pricing);
    page.appendChild(cli);
    page.appendChild(faqWrap);
  }

  // --------- ユーティリティ（innerHTML を使わない） ---------

  function el(tag, props = {}, ...children) {
    const node = document.createElement(tag);
    Object.assign(node, props);
    children.forEach(c => node.appendChild(c));
    return node;
  }
  function txt(s) { return document.createTextNode(String(s)); }
  function list(items) {
    const ul = el("ul");
    (items || []).forEach(s => {
      const li = el("li");
      li.appendChild(txt(String(s)));
      ul.appendChild(li);
    });
    return ul;
  }
  function code(s) {
    const pre = el("pre", { className: "code" });
    pre.textContent = String(s || "");
    return pre;
  }
  function section(title, contentNode) {
    const wrap = el("div", { className: "section card" });
    wrap.appendChild(el("h3", {}, txt(title)));
    wrap.appendChild(contentNode);
    return wrap;
  }
  function getLang() {
    return document.getElementById("lang").value;
  }
});
