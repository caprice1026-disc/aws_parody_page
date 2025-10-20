// 日本語コメント：API を叩いて JSON を受け取り、テンプレに差し込む

document.addEventListener("DOMContentLoaded", () => {
  const form = document.getElementById("gen-form");
  const term = document.getElementById("term");
  const lang = document.getElementById("lang");
  const tone = document.getElementById("tone");
  const statusEl = document.getElementById("status");
  const page = document.getElementById("page");
  const button = document.getElementById("gen-btn");

  // 日本語コメント：生成中のステータスメッセージを回すための配列
  const loadingMessages = [
    "生成中…（クラウドのはるか彼方でバズワードが攪拌されています）",
    "生成中…（エッジロケーション在住の妖精がキャッシュを温めています）",
    "生成中…（責任共有モデルの線引きを絶賛協議中…）",
  ];
  let loadingTimer = null;
  let loadingIndex = 0;

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const payload = {
      term: term.value.trim(),
      lang: lang.value,
      tone: tone.value,
    };

    term.classList.remove("input-error");

    if (!payload.term) {
      statusEl.textContent = "単語を入れてください。";
      term.classList.add("input-error");
      term.focus();
      return;
    }

    setLoadingState(true);
    startLoadingStatus();

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
      stopLoadingStatus("生成完了。");
      smoothScrollTo(page);
    } catch (err) {
      console.error(err);
      stopLoadingStatus("生成に失敗しました。コンソールを確認してください。");
      showErrorState("⚠️ 生成に失敗しました。もう一度お試しください。");
    } finally {
      setLoadingState(false);
    }
  });

  function startLoadingStatus() {
    statusEl.classList.add("is-loading");
    statusEl.textContent = loadingMessages[0];
    loadingIndex = 0;
    if (loadingTimer) clearInterval(loadingTimer);
    loadingTimer = setInterval(() => {
      loadingIndex = (loadingIndex + 1) % loadingMessages.length;
      statusEl.textContent = loadingMessages[loadingIndex];
    }, 2600);
  }

  function stopLoadingStatus(message) {
    statusEl.classList.remove("is-loading");
    if (loadingTimer) {
      clearInterval(loadingTimer);
      loadingTimer = null;
    }
    if (message) {
      statusEl.textContent = message;
    }
  }

  function setLoadingState(isLoading) {
    if (isLoading) {
      button.disabled = true;
      button.setAttribute("aria-busy", "true");
      showLoadingSkeleton();
    } else {
      button.disabled = false;
      button.removeAttribute("aria-busy");
    }
  }

  /** 日本語コメント：受け取った JSON をレイアウトに挿入する（innerHTML は使わず XSS を回避） */
  function render(spec) {
    page.classList.remove("loading");
    page.classList.remove("ready");
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
      const entry = el("div", { className: "faq-entry" },
        el("p", { className: "faq-question" }, txt(item.q || "")),
        el("p", { className: "faq-answer" }, txt(item.a || "")),
      );
      faqWrap.appendChild(entry);
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

    requestAnimationFrame(() => {
      page.classList.add("ready");
    });
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
  function showLoadingSkeleton() {
    page.classList.remove("ready");
    page.classList.add("loading");
    page.innerHTML = "";

    const heading = el("div", {},
      skeletonBlock("60%", 26),
      skeletonLine("40%", 16)
    );
    heading.style.marginBottom = "18px";
    heading.style.display = "grid";
    heading.style.gap = "12px";

    const tagline = el("div", {},
      skeletonLine("72%", 14),
      skeletonLine("52%", 14)
    );
    tagline.style.marginBottom = "24px";
    tagline.style.display = "grid";
    tagline.style.gap = "10px";

    const summary = skeletonCard();
    const highlight = skeletonCard();
    const grid = el("div", { className: "kv" }, summary, highlight);

    const sections = [
      skeletonSection(),
      skeletonSection(),
      skeletonSection(),
      skeletonSection(),
      skeletonSection(),
      skeletonFaq(),
    ];

    page.appendChild(heading);
    page.appendChild(tagline);
    page.appendChild(grid);
    sections.forEach(sec => page.appendChild(sec));
  }

  function showErrorState(message) {
    page.classList.remove("loading");
    page.classList.remove("ready");
    page.innerHTML = "";
    page.appendChild(el("div", { className: "placeholder error" }, txt(message)));
  }

  function skeletonLine(width, height = 12) {
    const line = el("div", { className: "skeleton-line skeleton-shimmer" });
    line.style.width = width;
    line.style.height = `${height}px`;
    return line;
  }

  function skeletonBlock(width, height = 18) {
    const block = el("div", { className: "skeleton-block skeleton-shimmer" });
    block.style.width = width;
    block.style.height = `${height}px`;
    return block;
  }

  function skeletonCard() {
    const card = el("div", { className: "card skeleton-card" });
    card.appendChild(skeletonBlock("55%", 18));
    card.appendChild(skeletonLine("82%"));
    card.appendChild(skeletonLine("68%"));
    card.appendChild(skeletonLine("72%"));
    return card;
  }

  function skeletonSection() {
    const wrap = el("div", { className: "section card skeleton-card" });
    wrap.appendChild(skeletonBlock("45%", 18));
    wrap.appendChild(skeletonLine("86%"));
    wrap.appendChild(skeletonLine("72%"));
    wrap.appendChild(skeletonLine("64%"));
    return wrap;
  }

  function skeletonFaq() {
    const wrap = el("div", { className: "section card skeleton-card" });
    wrap.appendChild(skeletonBlock("30%", 18));
    wrap.appendChild(skeletonLine("90%"));
    wrap.appendChild(skeletonLine("80%"));
    wrap.appendChild(skeletonLine("70%"));
    wrap.appendChild(skeletonLine("82%"));
    return wrap;
  }

  function smoothScrollTo(node) {
    if (!node) return;
    node.scrollIntoView({ behavior: "smooth", block: "start" });
  }
});
