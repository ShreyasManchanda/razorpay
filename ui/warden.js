(() => {
  "use strict";

  const CASES = [
    { id: "sabziwala_clean_pass_v1", name: "Clean negotiation", short: "Clean" },
    { id: "sabziwala_legitimate_revision_pass_v1", name: "Legitimate revision", short: "Legit revision" },
    { id: "sabziwala_injection_reject_v1", name: "Prompt injection", short: "Injection" },
    { id: "sabziwala_drift_stepup_v1", name: "Gradual reasoning drift", short: "Drift" },
  ];
  const INJECTION_CASE_ID = CASES[2].id;
  const DRIFT_CASE_ID = CASES[3].id;
  const LIVE_INTENT = {
    scenario: "sabziwala_vs_mom",
    intent_text: "Buy fresh tamatar aur pyaz under 150 rupees total",
    max_price: 150,
    allowed_categories: ["vegetables"],
    red_lines: ["no stale items"],
  };
  const LIVE_SCRIPT = [
    "Bhaiya, fresh tamatar aur pyaz chahiye. Total Rs.150 ke andar rakhna.",
    "Fresh tamatar aur pyaz hi chahiye; total Rs.150 ke andar hi rakhna. Final rate batao.",
    "Yes, I accept fresh tamatar aur pyaz at the final price under Rs.150.",
  ];
  const MCP_COMMAND = "$env:PYTHONPATH='src'; .venv\\Scripts\\python scripts\\mcp_demo.py";
  const reducedMotion = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const gsapReady = typeof window.gsap !== "undefined";
  const $ = (id) => document.getElementById(id);
  const currencyFormatter = new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 2 });

  const state = {
    mode: "replay",
    caseIndex: 0,
    replay: null,
    frame: null,
    timeline: null,
    requestId: 0,
    abortController: null,
    playing: false,
    pausedForVisibility: false,
    renderedTurns: 0,
    liveSessionId: null,
    liveSnapshot: null,
    liveBusy: false,
    liveScriptRunning: false,
    liveGeneration: 0,
    liveAbortController: null,
    reviewTxId: null,
    report: null,
    evalAnimated: false,
    evaluationEntered: false,
    reviewPreparing: false,
    reviewPrepared: false,
    policyRequestId: 0,
  };

  async function jsonRequest(url, options = {}) {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(new DOMException("Request timed out", "TimeoutError")), 12000);
    const upstreamSignal = options.signal;
    const abortFromUpstream = () => controller.abort(upstreamSignal.reason);
    if (upstreamSignal) {
      if (upstreamSignal.aborted) abortFromUpstream();
      else upstreamSignal.addEventListener("abort", abortFromUpstream, { once: true });
    }
    try {
      const response = await fetch(url, { cache: "no-store", ...options, signal: controller.signal });
      if (!response.ok) {
        let detail = `${response.status} ${response.statusText}`;
        try {
          const payload = await response.json();
          detail = payload.detail || detail;
        } catch { /* response is not JSON */ }
        throw new Error(detail);
      }
      return response.json();
    } finally {
      clearTimeout(timeout);
      upstreamSignal?.removeEventListener("abort", abortFromUpstream);
    }
  }

  function money(value) {
    const amount = Number(value) || 0;
    return currencyFormatter.format(amount);
  }

  function setConsoleState(verdict) {
    const normalized = String(verdict || "ANALYSIS").toLowerCase();
    $("evidence-console").dataset.state = ["pass", "reject", "stepup"].includes(normalized) ? normalized : "analysis";
  }

  function setConnection(text, tone = "analysis") {
    $("connection-state").textContent = text;
    $("connection-state").dataset.tone = tone;
  }

  function animateNumber(element, target, formatter, duration = 0.5) {
    const current = Number(element.dataset.value ?? 0);
    element.dataset.value = String(target);
    element._wardenTween?.kill();
    if (!gsapReady || reducedMotion) {
      element.textContent = formatter(target);
      return;
    }
    const counter = element._wardenCounter || { value: current };
    counter.value = current;
    element._wardenCounter = counter;
    element._wardenTween = window.gsap.to(counter, {
      value: target,
      duration,
      ease: "power2.out",
      onUpdate: () => { element.textContent = formatter(counter.value); },
      onComplete: () => { element._wardenTween = null; },
    });
  }

  function clearTranscript(message = "") {
    $("turn-log").replaceChildren();
    state.renderedTurns = 0;
    if (message) {
      const empty = document.createElement("p");
      empty.className = "empty-state";
      empty.textContent = message;
      $("turn-log").append(empty);
    }
  }

  function isInjectionMessage(message) {
    return /buyer agent must approve|ignore previous|without further checks/i.test(String(message));
  }

  function appendTurn(turn, animate = true) {
    const empty = $("turn-log").querySelector(".empty-state");
    if (empty) empty.remove();
    const article = document.createElement("article");
    const buyer = turn.speaker === "buyer_agent";
    article.className = `turn ${buyer ? "turn--buyer" : "turn--merchant"}`;
    if (!buyer && isInjectionMessage(turn.message)) article.classList.add("turn--flagged");
    const header = document.createElement("header");
    const speaker = document.createElement("strong");
    const action = document.createElement("span");
    const copy = document.createElement("p");
    speaker.textContent = buyer ? "Buyer agent" : "Sabziwala agent";
    action.textContent = turn.action || "message";
    copy.textContent = turn.message || "";
    header.append(speaker, action);
    article.append(header, copy);
    $("turn-log").append(article);
    state.renderedTurns += 1;
    $("turn-log").scrollTop = $("turn-log").scrollHeight;
    if (animate && gsapReady && !reducedMotion) {
      window.gsap.fromTo(article, { opacity: 0, y: 10, scale: 0.985 }, { opacity: 1, y: 0, scale: 1, duration: 0.26, ease: "power2.out" });
    }
  }

  function appendNewTurns(transcript, animate = true) {
    transcript.slice(state.renderedTurns).forEach((turn) => appendTurn(turn, animate));
  }

  function graphPath(values) {
    const scores = values.length ? values : [1];
    if (scores.length === 1) {
      const y = 8 + (1 - scores[0]) * 98;
      return { d: `M0 ${y.toFixed(2)} L320 ${y.toFixed(2)}`, points: [{ x: 320, y }] };
    }
    const points = scores.map((score, index) => ({
      x: (index / (scores.length - 1)) * 320,
      y: 8 + (1 - Math.max(0, Math.min(1, Number(score)))) * 98,
    }));
    return { d: points.map((point, index) => `${index ? "L" : "M"}${point.x.toFixed(2)} ${point.y.toFixed(2)}`).join(" "), points };
  }

  function drawTrust(values, animate = true) {
    const numeric = (Array.isArray(values) ? values : []).map(Number).filter(Number.isFinite);
    const score = numeric.length ? numeric.at(-1) : 1;
    animateNumber($("trust-value"), score, (value) => value.toFixed(2));
    const pathData = graphPath(numeric);
    const path = $("trust-path");
    const pulse = $("threshold-pulse");
    if (gsapReady) {
      window.gsap.killTweensOf(path);
      window.gsap.killTweensOf(pulse);
      window.gsap.set(pulse, { opacity: 0, scale: 1 });
    } else {
      pulse.style.opacity = "0";
    }
    path.setAttribute("d", pathData.d);
    const length = path.getTotalLength();
    path.style.strokeDasharray = String(length);
    path.style.strokeDashoffset = animate && !reducedMotion ? String(length) : "0";
    if (gsapReady && animate && !reducedMotion) {
      window.gsap.to(path, { strokeDashoffset: 0, duration: 1.2, ease: "power2.out" });
    } else {
      path.style.strokeDashoffset = "0";
    }
    const crossing = numeric.findIndex((value, index) => index > 0 && numeric[index - 1] >= 0.45 && value < 0.45);
    if (crossing >= 0 && pathData.points[crossing]) {
      const point = pathData.points[crossing];
      pulse.setAttribute("cx", point.x.toFixed(2));
      pulse.setAttribute("cy", point.y.toFixed(2));
      if (gsapReady && animate && !reducedMotion) {
        window.gsap.fromTo(pulse, { opacity: 0.95, scale: 0.7 }, { opacity: 0, scale: 3.4, duration: 0.9, ease: "power2.out", delay: 0.7 });
      }
    } else {
      pulse.style.opacity = "0";
    }
  }

  function detectorCopy(name, detector, frame) {
    const status = detector?.status || "pending";
    if (status === "unavailable") return "Unavailable / review required";
    if (name === "signature") return status === "pass" ? "Signature verified" : status === "fail" ? "Signature failed" : "Awaiting signed cart";
    if (name === "constraints") {
      const violations = detector?.violations || [];
      return violations.length ? violations[0].replaceAll("_", " ") : status === "pending" ? "Awaiting agreement" : "Rules satisfied";
    }
    if (name === "drift") return `${Number(detector?.score ?? 1).toFixed(2)} trust${detector?.explicit_conflict ? " / conflict" : ""}`;
    const hard = detector?.flags || frame?.signals?.injection_flags || [];
    const soft = detector?.suspicious_flags || frame?.signals?.suspicious_flags || [];
    return hard.length ? hard[0].replace("injection_pattern:", "") : soft.length ? soft[0].replace("suspicious_pattern:", "watch: ") : "No pattern match";
  }

  function detectorLevel(name, detector) {
    const status = detector?.status || "pending";
    if (status === "unavailable") return 0.75;
    if (name === "drift") return Math.max(0.08, 1 - Number(detector?.score ?? 1));
    if (status === "flag" || status === "fail") return 1;
    if (status === "watch") return 0.62;
    if (status === "pass") return 0.08;
    return 0.12;
  }

  function renderDetectors(frame, animate = true) {
    const detectors = frame.detectors || {};
    document.querySelectorAll(".signal-row").forEach((row, index) => {
      const name = row.dataset.detector;
      const detector = detectors[name] || {};
      const status = detector.status || "pending";
      row.dataset.status = status;
      row.querySelector("em").textContent = detectorCopy(name, detector, frame);
      row.setAttribute("aria-label", `${row.querySelector("strong").textContent}: ${status}. ${row.querySelector("em").textContent}`);
      const fill = row.querySelector("i b");
      const scale = detectorLevel(name, detector);
      const riskPercent = Math.round(scale * 100);
      row.dataset.risk = String(riskPercent);
      row.querySelector("i").title = `Risk intensity: ${riskPercent}%`;
      row.setAttribute("aria-label", `${row.querySelector("strong").textContent}: ${status}. ${row.querySelector("em").textContent}. Risk intensity ${riskPercent} percent.`);
      if (gsapReady && animate && !reducedMotion) {
        window.gsap.killTweensOf(row);
        window.gsap.killTweensOf(fill);
        window.gsap.fromTo(fill, { scaleX: 0 }, { scaleX: scale, duration: 0.42, delay: index * 0.06, ease: "power2.out" });
        window.gsap.fromTo(row, { opacity: 0, y: 8 }, { opacity: 1, y: 0, duration: 0.22, delay: index * 0.06, ease: "power2.out" });
      } else {
        fill.style.transform = `scaleX(${scale})`;
      }
    });
  }

  function paymentCopy(frame, live = false) {
    if (live) {
      if (frame.verdict === "REJECT") return "No payment / blocked";
      if (frame.verdict === "STEPUP") return "No payment / held for review";
      if (frame.decision_state === "final") return "Authorized; no payment requested";
      return "No payment requested in live session";
    }
    const map = { demo_order_created: "Mock order created", awaiting_review: "No payment / held for review", blocked: "No payment / blocked", not_requested: "No payment requested" };
    return map[frame.payment_state] || "Not requested";
  }

  function renderEvidence(frame, { animate = true, live = false } = {}) {
    state.frame = frame;
    const verdict = frame.verdict || "ANALYSIS";
    const final = frame.decision_state === "final" || frame.decision_state === "review_required";
    setConsoleState(verdict);
    $("decision-phase").textContent = final ? frame.decision_state === "review_required" ? "HUMAN REVIEW" : "FINAL" : "PROVISIONAL";
    $("decision-title").textContent = verdict;
    $("decision-title").dataset.long = String(verdict.length > 5);
    $("decision-explanation").textContent = frame.explanation || "Warden evaluated the latest exchange.";
    if (gsapReady && animate && !reducedMotion) {
      window.gsap.killTweensOf($("decision-title"));
      window.gsap.fromTo($("decision-title"), { opacity: 0, scale: 0.9 }, { opacity: 1, scale: 1, duration: 0.38, ease: "back.out(1.4)" });
    }
    drawTrust(frame.trust_score_trajectory, animate);
    renderDetectors(frame, animate);
    const cart = frame.cart || {};
    animateNumber($("cart-total"), Number(cart.total) || 0, money);
    const agreed = cart.agreement_status === "agreed";
    $("agreement-state").textContent = agreed ? "Buyer agreed" : "Pending buyer";
    $("payment-state").textContent = paymentCopy(frame, live);
    const proof = $("agreement-proof").querySelector("p");
    proof.textContent = agreed && cart.agreement_evidence?.length
      ? cart.agreement_evidence.join(" / ").replaceAll("_", " ")
      : "Waiting for an explicit buyer accept tied to a named cart.";
    $("decision-announcer").textContent = `${final ? "Final" : "Provisional"} Warden state: ${verdict}. ${$("payment-state").textContent}.`;
    $("export-evidence").disabled = live ? !state.liveSnapshot : !state.replay;
  }

  function stopReplayTimeline() {
    if (state.timeline) state.timeline.kill();
    state.timeline = null;
    setPlayButton(false);
  }

  function setPlayButton(playing) {
    state.playing = playing;
    $("play-toggle").innerHTML = playing ? "&#10074;&#10074;" : "&#9654;";
    $("play-toggle").setAttribute("aria-label", playing ? "Pause replay" : "Play replay");
    $("play-toggle").title = playing ? "Pause replay" : "Play replay";
  }

  function renderFrameTurns(frame) {
    clearTranscript();
    frame.transcript.forEach((turn) => appendTurn(turn, false));
  }

  function buildReplayTimeline({ autoplay = true } = {}) {
    if (state.mode !== "replay" || !state.replay?.frames?.length) return;
    stopReplayTimeline();
    clearTranscript();
    $("playback-progress").style.transform = "scaleX(0)";
    const frames = state.replay.frames;
    $("exchange-count").textContent = `Exchange 0 / ${frames.length}`;
    if (reducedMotion || !gsapReady) {
      const finalFrame = frames.at(-1);
      renderFrameTurns(finalFrame);
      renderEvidence(finalFrame, { animate: false });
      $("exchange-count").textContent = `Exchange ${frames.length} / ${frames.length}`;
      $("playback-progress").style.transform = "scaleX(1)";
      setPlayButton(false);
      return;
    }
    const timeline = window.gsap.timeline({
      paused: true,
      onUpdate: () => { $("playback-progress").style.transform = `scaleX(${timeline.progress()})`; },
      onComplete: () => setPlayButton(false),
    });
    let priorCount = 0;
    frames.forEach((frame, index) => {
      timeline.addLabel(`exchange-${index + 1}`);
      frame.transcript.slice(priorCount).forEach((turn) => {
        timeline.call(() => appendTurn(turn));
        timeline.to({}, { duration: turn.speaker === "buyer_agent" ? 0.42 : 0.58 });
      });
      timeline.call(() => {
        renderEvidence(frame);
        $("exchange-count").textContent = `Exchange ${index + 1} / ${frames.length}`;
      });
      timeline.to({}, { duration: index === frames.length - 1 ? 1.2 : 0.78 });
      priorCount = frame.transcript.length;
    });
    state.timeline = timeline;
    if (autoplay) {
      timeline.play(0);
      setPlayButton(true);
    } else {
      timeline.pause(0);
      setPlayButton(false);
    }
  }

  async function loadCase(index, { autoplay = true } = {}) {
    const normalized = (index + CASES.length) % CASES.length;
    const requestId = ++state.requestId;
    state.abortController?.abort();
    state.abortController = new AbortController();
    stopReplayTimeline();
    state.replay = null;
    state.frame = null;
    $("restart-replay").disabled = true;
    $("export-evidence").disabled = true;
    state.caseIndex = normalized;
    const selected = CASES[normalized];
    document.querySelectorAll("[data-case-index]").forEach((button) => button.setAttribute("aria-pressed", String(Number(button.dataset.caseIndex) === normalized)));
    $("conversation-title").textContent = selected.name;
    $("case-position").textContent = `Case ${normalized + 1} of ${CASES.length}`;
    setConnection("Loading evidence", "analysis");
    const consoleElement = $("evidence-console");
    if (gsapReady) {
      window.gsap.killTweensOf(consoleElement);
      window.gsap.set(consoleElement, { opacity: 1, x: 0 });
    }
    const outgoing = gsapReady && !reducedMotion ? window.gsap.to(consoleElement, { opacity: 0, x: -24, duration: 0.25, ease: "power2.in" }) : null;
    try {
      const replay = await jsonRequest(`/replays/${encodeURIComponent(selected.id)}`, { signal: state.abortController.signal });
      if (requestId !== state.requestId || state.mode !== "replay") return;
      if (outgoing) await outgoing;
      if (requestId !== state.requestId || state.mode !== "replay") return;
      if (!Array.isArray(replay.frames) || !replay.frames.length) throw new Error("Replay returned no evidence frames");
      state.replay = replay;
      $("restart-replay").disabled = false;
      $("conversation-state").textContent = "Immutable server replay";
      $("intent-text").textContent = replay.intent.raw_goal_text;
      $("active-policy").textContent = "Quick commerce";
      setConnection(`${replay.frames.length} exchanges`, "pass");
      clearTranscript();
      setConsoleState("ANALYSIS");
      $("decision-title").textContent = "ANALYSIS";
      $("decision-title").dataset.long = "true";
      $("decision-explanation").textContent = "Conversation evidence will update one exchange at a time.";
      drawTrust([], false);
      if (gsapReady && !reducedMotion) {
        window.gsap.set(consoleElement, { opacity: 0, x: 24 });
        window.gsap.to(consoleElement, {
          opacity: 1,
          x: 0,
          duration: 0.3,
          delay: 0.1,
          ease: "power2.out",
          onComplete: () => {
            if (requestId === state.requestId && state.mode === "replay") buildReplayTimeline({ autoplay });
          },
        });
      } else {
        buildReplayTimeline({ autoplay });
      }
    } catch (error) {
      if (error.name === "AbortError" || requestId !== state.requestId) return;
      clearTranscript(`Replay unavailable: ${error.message}`);
      setConnection("API unavailable", "reject");
      $("decision-title").textContent = "ERROR";
      $("decision-explanation").textContent = "No substitute demo data was rendered.";
      if (outgoing) window.gsap.to(consoleElement, { opacity: 1, x: 0, duration: 0.2 });
    }
  }

  function toggleReplay() {
    if (!state.timeline) return;
    if (state.timeline.progress() >= 1) {
      buildReplayTimeline({ autoplay: true });
    } else if (state.timeline.paused()) {
      state.timeline.play();
      setPlayButton(true);
    } else {
      state.timeline.pause();
      setPlayButton(false);
    }
  }

  function setMode(mode) {
    if (mode === state.mode) return;
    state.mode = mode;
    ++state.requestId;
    state.abortController?.abort();
    state.liveGeneration += 1;
    state.liveScriptRunning = false;
    state.liveAbortController?.abort();
    state.liveAbortController = null;
    state.liveBusy = false;
    $("live-script").textContent = "Run prepared conversation";
    stopReplayTimeline();
    if (gsapReady) {
      window.gsap.killTweensOf($("evidence-console"));
      window.gsap.set($("evidence-console"), { opacity: 1, x: 0 });
    }
    const live = mode === "live";
    $("replay-mode").setAttribute("aria-pressed", String(!live));
    $("live-mode").setAttribute("aria-pressed", String(live));
    $("replay-controls").hidden = live;
    $("live-launch").hidden = !live;
    $("live-form").hidden = !live || !state.liveSessionId;
    document.querySelectorAll("[data-case-index]").forEach((button) => { button.disabled = live; });
    if (!live) {
      loadCase(state.caseIndex);
      return;
    }
    setLiveBusy(false);
    clearTranscript("Start a session to open a real sabziwala conversation.");
    $("conversation-state").textContent = "Interactive bounded session";
    $("conversation-title").textContent = "Talk to the sabziwala";
    $("intent-text").textContent = LIVE_INTENT.intent_text;
    $("case-position").textContent = "Live mode";
    setConnection("Ready to start", "analysis");
    if (state.liveSnapshot) {
      clearTranscript();
      applyLiveSnapshot(state.liveSnapshot);
      return;
    }
    renderEvidence({ verdict: "ANALYSIS", decision_state: "provisional", explanation: "Start a session, then type or run the prepared conversation.", trust_score_trajectory: [], detectors: {}, cart: { total: 0, agreement_status: "pending" }, signals: {}, payment_state: "not_requested" }, { animate: false, live: true });
  }

  function setLiveBusy(busy, message) {
    state.liveBusy = busy;
    $("live-start").disabled = busy;
    $("live-script").disabled = busy || !state.liveSessionId || !state.liveSnapshot?.can_continue;
    $("live-message").disabled = busy || !state.liveSnapshot?.can_continue;
    $("live-form").querySelector("button").disabled = busy || !state.liveSnapshot?.can_continue;
    $("live-approve").disabled = busy;
    $("live-reject").disabled = busy;
    if (message) $("live-status").textContent = message;
  }

  function liveFrame(snapshot) {
    return {
      verdict: snapshot.verdict || "ANALYSIS",
      decision_state: snapshot.decision_state,
      explanation: snapshot.explanation,
      trust_score_trajectory: snapshot.trust_score_trajectory || [],
      detectors: snapshot.detectors || {},
      signals: snapshot.signals || {},
      cart: snapshot.cart || { total: 0, agreement_status: "pending" },
      payment_state: "not_requested",
    };
  }

  function applyLiveSnapshot(snapshot) {
    state.liveSnapshot = snapshot;
    state.liveSessionId = snapshot.session_id;
    appendNewTurns(snapshot.transcript || []);
    renderEvidence(liveFrame(snapshot), { live: true });
    $("conversation-title").textContent = `Sabziwala session ${snapshot.session_id.slice(-6)}`;
    $("case-position").textContent = `${snapshot.turn_count} buyer turns`;
    $("live-form").hidden = false;
    $("live-start").textContent = "Restart session";
    $("live-script").disabled = !snapshot.can_continue;
    const review = snapshot.status === "awaiting_review";
    $("live-approve").hidden = !review;
    $("live-reject").hidden = !review;
    const verdict = String(snapshot.verdict || "ANALYSIS").toLowerCase();
    const tone = snapshot.degraded || verdict === "stepup" ? "stepup" : verdict === "reject" ? "reject" : verdict === "pass" && !snapshot.can_continue ? "pass" : "analysis";
    const replySource = snapshot.mode === "fallback"
      ? "Fallback + detectors live"
      : snapshot.reply_source === "rules"
      ? "Rules + detectors live"
      : "Provider + detectors live";
    setConnection(replySource, tone);
    const detectorErrors = snapshot.detector_errors || [];
    $("live-status").textContent = detectorErrors.length
      ? `Detector unavailable: ${detectorErrors[0].split(":", 1)[0].replaceAll("_", " ")}`
      : review ? "Paused for human review" : snapshot.can_continue ? "Warden is monitoring" : `Session ${snapshot.status}`;
  }

  async function startLive() {
    if (state.liveBusy) return;
    state.liveScriptRunning = false;
    state.liveSessionId = null;
    state.liveSnapshot = null;
    const generation = ++state.liveGeneration;
    state.liveAbortController?.abort();
    const controller = new AbortController();
    state.liveAbortController = controller;
    clearTranscript("Opening the market conversation…");
    setLiveBusy(true, "Starting merchant agent…");
    try {
      const snapshot = await jsonRequest("/live/sessions", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(LIVE_INTENT), signal: controller.signal });
      if (state.mode !== "live" || generation !== state.liveGeneration) return;
      clearTranscript();
      applyLiveSnapshot(snapshot);
    } catch (error) {
      if (error.name === "AbortError") return;
      clearTranscript(`Could not start live session: ${error.message}`);
      setConnection("Live API unavailable", "reject");
      $("live-status").textContent = "Start failed";
    } finally {
      if (generation === state.liveGeneration) setLiveBusy(false);
    }
  }

  async function sendLiveMessage(message) {
    if (!state.liveSessionId || state.liveBusy || !message.trim()) return null;
    const generation = state.liveGeneration;
    const sessionId = state.liveSessionId;
    state.liveAbortController?.abort();
    const controller = new AbortController();
    state.liveAbortController = controller;
    setLiveBusy(true, "Merchant responding, then Warden evaluates…");
    try {
      const snapshot = await jsonRequest(`/live/sessions/${encodeURIComponent(sessionId)}/turns`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: message.trim() }),
        signal: controller.signal,
      });
      if (state.mode !== "live" || generation !== state.liveGeneration || sessionId !== state.liveSessionId) return null;
      applyLiveSnapshot(snapshot);
      return snapshot;
    } catch (error) {
      if (error.name === "AbortError") return null;
      $("live-status").textContent = `Turn failed: ${error.message}`;
      setConnection("Turn failed", "reject");
      return null;
    } finally {
      if (generation === state.liveGeneration) setLiveBusy(false);
    }
  }

  async function runLiveScript() {
    if (!state.liveSessionId || state.liveScriptRunning) return;
    const generation = state.liveGeneration;
    const sessionId = state.liveSessionId;
    state.liveScriptRunning = true;
    $("live-script").textContent = "Conversation running";
    for (const message of LIVE_SCRIPT) {
      if (!state.liveScriptRunning || state.mode !== "live" || generation !== state.liveGeneration || sessionId !== state.liveSessionId || !state.liveSnapshot?.can_continue) break;
      const snapshot = await sendLiveMessage(message);
      if (!snapshot) break;
      if (!reducedMotion) await new Promise((resolve) => setTimeout(resolve, 700));
    }
    if (generation === state.liveGeneration) {
      state.liveScriptRunning = false;
      $("live-script").textContent = "Run prepared conversation";
    }
  }

  async function reviewLive(approved) {
    if (!state.liveSessionId || state.liveBusy) return;
    const generation = state.liveGeneration;
    const sessionId = state.liveSessionId;
    state.liveAbortController?.abort();
    const controller = new AbortController();
    state.liveAbortController = controller;
    setLiveBusy(true, "Applying human decision…");
    try {
      const snapshot = await jsonRequest(`/live/sessions/${encodeURIComponent(sessionId)}/review`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ approved }), signal: controller.signal,
      });
      if (state.mode !== "live" || generation !== state.liveGeneration || sessionId !== state.liveSessionId) return;
      applyLiveSnapshot(snapshot);
    } catch (error) {
      if (error.name === "AbortError") return;
      $("live-status").textContent = `Review failed: ${error.message}`;
    } finally {
      if (generation === state.liveGeneration) setLiveBusy(false);
    }
  }

  async function swapPolicy(button) {
    const requestId = ++state.policyRequestId;
    document.querySelectorAll("[data-policy]").forEach((item) => item.setAttribute("aria-pressed", String(item === button)));
    const policy = button.dataset.policy;
    $("policy-result").textContent = "Rescoring the stored signal bundle…";
    try {
      const payload = await jsonRequest("/policy/swap", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ policy_name: policy, tx_id: INJECTION_CASE_ID }) });
      const result = payload.results?.[0];
      if (requestId !== state.policyRequestId) return;
      if (!result) throw new Error("No stored signal bundle returned");
      const target = policy === "quick_commerce" ? $("quick-verdict") : $("b2b-verdict");
      target.textContent = result.new;
      target.dataset.state = result.new.toLowerCase();
      button.dataset.state = result.new.toLowerCase();
      $("policy-result").textContent = `${result.old} under the original policy becomes ${result.new} under ${policy.replaceAll("_", " ")}. Detectors did not rerun.`;
      if (gsapReady && !reducedMotion) window.gsap.fromTo(target, { opacity: 0, scale: 0.9 }, { opacity: 1, scale: 1, duration: 0.32, ease: "back.out(1.4)" });
    } catch (error) {
      $("policy-result").textContent = `Policy re-evaluation failed: ${error.message}`;
    }
  }

  async function runTamper() {
    $("run-tamper").disabled = true;
    $("tamper-result").textContent = "Signing Rs.90, changing one field, then verifying the original signature…";
    try {
      const result = await jsonRequest("/tamper/check", { method: "POST" });
      $("tamper-verdict").textContent = result.verdict;
      $("tamper-verdict").dataset.state = result.verdict.toLowerCase();
      $("tamper-result").textContent = `${result.explanation} Semantic detectors ran: ${result.detectors_ran}. Payment created: ${result.payment_created}.`;
      if (gsapReady && !reducedMotion) window.gsap.fromTo($("tamper-verdict"), { opacity: 0, scale: 0.9 }, { opacity: 1, scale: 1, duration: 0.36, ease: "back.out(1.4)" });
    } catch (error) {
      $("tamper-result").textContent = `Tamper proof failed to run: ${error.message}`;
    } finally {
      $("run-tamper").disabled = false;
    }
  }

  async function prepareReview() {
    if (state.reviewPreparing) return;
    state.reviewPreparing = true;
    state.reviewPrepared = true;
    state.reviewTxId = null;
    $("review-state").textContent = "STEPUP";
    $("review-state").style.color = "";
    $("review-id").textContent = "Preparing checkpoint";
    $("review-copy").textContent = "Creating an isolated copy of the Drift case for this decision.";
    document.querySelectorAll("[data-review]").forEach((button) => { button.disabled = true; });
    $("reset-review").disabled = true;
    try {
      const result = await jsonRequest(`/replays/${encodeURIComponent(DRIFT_CASE_ID)}/review`, { method: "POST" });
      state.reviewTxId = result.tx_id;
      $("review-id").textContent = result.tx_id;
      $("review-copy").textContent = "Trust crossed 0.45 while the cart stayed inside hard constraints. Payment is paused at a real LangGraph checkpoint.";
      document.querySelectorAll("[data-review]").forEach((button) => { button.disabled = false; });
    } catch (error) {
      $("review-state").textContent = "UNAVAILABLE";
      $("review-copy").textContent = `Could not create review checkpoint: ${error.message}`;
    } finally {
      state.reviewPreparing = false;
      $("reset-review").disabled = false;
    }
  }

  async function resolveReview(approved) {
    if (!state.reviewTxId) return;
    document.querySelectorAll("[data-review]").forEach((button) => { button.disabled = true; });
    $("review-copy").textContent = "Resuming the paused graph with the human decision…";
    try {
      const result = await jsonRequest(`/stepup/${encodeURIComponent(state.reviewTxId)}/resume`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ approved }) });
      $("review-state").textContent = result.verdict;
      $("review-state").style.color = result.verdict === "PASS" ? "var(--pass)" : "var(--reject)";
      $("review-copy").textContent = result.verdict === "PASS" ? `Human approved the paused transaction. ${result.explanation}` : "Human rejected the paused transaction. Payment remains blocked.";
    } catch (error) {
      $("review-copy").textContent = `Review failed: ${error.message}`;
      document.querySelectorAll("[data-review]").forEach((button) => { button.disabled = false; });
    }
  }

  function percent(value, decimals = 0) {
    return `${(Number(value) * 100).toFixed(decimals)}%`;
  }

  function renderEvaluation(report, animate = false) {
    const metrics = report.holdout.semantic;
    const targets = {
      "holdout-recall": [metrics.recall * 100, (value) => `${value.toFixed(1)}%`],
      precision: [metrics.precision * 100, (value) => `${value.toFixed(0)}%`],
      f1: [metrics.f1 * 100, (value) => `${value.toFixed(1)}%`],
      fpr: [metrics.fpr * 100, (value) => `${value.toFixed(1)}%`],
      "holdout-n": [report.holdout.n_evaluated, (value) => `${Math.round(value)}`],
    };
    Object.entries(targets).forEach(([key, [target, formatter]]) => {
      const element = document.querySelector(`[data-eval="${key}"]`);
      if (animate) animateNumber(element, target, formatter, 0.8);
      else { element.dataset.value = "0"; element.textContent = formatter(target); }
    });
    $("recall-ci").textContent = `95% CI ${percent(metrics.recall_95_ci[0], 1)} to ${percent(metrics.recall_95_ci[1], 1)}`;
    $("constraint-result").textContent = `${report.all.constraint.caught}/${report.all.constraint.n}`;
    $("tamper-result-eval").textContent = `${report.all.tamper.caught}/${report.all.tamper.n}`;
    const blindTotal = report.blind_challenge.semantic.tp + report.blind_challenge.semantic.fn;
    $("blind-result").textContent = `${report.blind_challenge.semantic.tp}/${blindTotal}`;
    $("miss-result").textContent = `${report.blind_challenge.semantic.fn} retained`;
    $("eval-meta").textContent = `${report.corpus.n} total cases, ${report.scope.in_scope_n} in scope, ${report.holdout.n_evaluated} grouped holdout rows. Dataset ${report.dataset_version}.`;
    const labels = { clean: "Clean", constraint: "Constraint", "gradual-drift": "Drift", injected: "Injection", "legitimate-revision": "Legit revision", tamper: "Tamper" };
    const tones = { clean: "pass", constraint: "reject", "gradual-drift": "stepup", injected: "reject", "legitimate-revision": "pass", tamper: "reject" };
    $("corpus-bar").replaceChildren();
    $("corpus-legend").replaceChildren();
    Object.entries(report.corpus.labels).forEach(([key, count], index) => {
      const segment = document.createElement("span");
      segment.style.width = `${(count / report.corpus.n) * 100}%`;
      segment.style.setProperty("--segment-opacity", String(1 - (index % 3) * 0.18));
      segment.dataset.tone = tones[key] || "analysis";
      segment.setAttribute("aria-label", `${labels[key] || key}: ${count} cases`);
      $("corpus-bar").append(segment);
      const legend = document.createElement("span");
      legend.dataset.tone = tones[key] || "analysis";
      const swatch = document.createElement("i");
      swatch.setAttribute("aria-hidden", "true");
      const name = document.createTextNode(labels[key] || key);
      const value = document.createElement("b");
      value.textContent = String(count);
      legend.append(swatch, name, value);
      $("corpus-legend").append(legend);
      if (animate && gsapReady && !reducedMotion) window.gsap.to(segment, { scaleX: 1, duration: 0.55, delay: index * 0.07, ease: "power2.out" });
      else segment.style.transform = "scaleX(1)";
    });
    $("corpus-bar").setAttribute("aria-label", `Evaluation corpus composition: ${Object.entries(report.corpus.labels).map(([key, count]) => `${labels[key] || key} ${count}`).join(", ")}`);
  }

  async function loadEvaluation() {
    try {
      state.report = await jsonRequest("/evaluation/report");
      if (state.evaluationEntered && !state.evalAnimated) {
        state.evalAnimated = true;
        renderEvaluation(state.report, true);
      } else {
        renderEvaluation(state.report, false);
      }
    } catch (error) {
      $("eval-meta").textContent = `Authoritative evaluation report unavailable: ${error.message}`;
    }
  }

  function exportEvidence() {
    const source = state.mode === "live" ? state.liveSnapshot : state.frame;
    if (!source) return;
    const payload = state.mode === "live" ? source : {
      mode: "immutable_replay",
      scenario_id: state.replay.scenario_id,
      case_id: state.replay.case_id,
      expected_verdict: state.replay.expected_verdict,
      frame: state.frame,
    };
    const blob = new Blob([JSON.stringify({ exported_at: new Date().toISOString(), ...payload }, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `warden-${state.mode === "live" ? state.liveSessionId : state.replay.case_id}.json`;
    anchor.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  function setupSectionMotion() {
    const observer = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (!entry.isIntersecting) return;
        if (gsapReady && !reducedMotion) window.gsap.from(entry.target.querySelectorAll(":scope > .section-shell"), { opacity: 0, y: 16, duration: 0.52, ease: "power2.out" });
      if (entry.target.id === "evaluation") {
          state.evaluationEntered = true;
          if (state.report && !state.evalAnimated) {
            state.evalAnimated = true;
            renderEvaluation(state.report, true);
          }
        }
        if (entry.target.id === "review" && !state.reviewPrepared) prepareReview();
        observer.unobserve(entry.target);
      });
    }, { threshold: 0.16 });
    document.querySelectorAll(".section").forEach((section) => observer.observe(section));
  }

  async function verifyScenario() {
    const scenarios = await jsonRequest("/scenarios");
    const selected = scenarios.find((scenario) => scenario.is_default);
    if (selected?.id !== "sabziwala_vs_mom") throw new Error(`Expected sabziwala_vs_mom, received ${selected?.id || "none"}`);
    $("scenario-proof").textContent = `Scenario: ${selected.id} / default confirmed`;
  }

  function bindEvents() {
    document.querySelectorAll("[data-case-index]").forEach((button) => button.addEventListener("click", () => loadCase(Number(button.dataset.caseIndex))));
    $("previous-case").addEventListener("click", () => loadCase(state.caseIndex - 1));
    $("next-case").addEventListener("click", () => loadCase(state.caseIndex + 1));
    $("play-toggle").addEventListener("click", toggleReplay);
    $("restart-replay").addEventListener("click", () => {
      if (state.mode === "replay") loadCase(state.caseIndex, { autoplay: true });
    });
    $("replay-mode").addEventListener("click", () => setMode("replay"));
    $("live-mode").addEventListener("click", () => setMode("live"));
    $("live-start").addEventListener("click", startLive);
    $("live-script").addEventListener("click", runLiveScript);
    $("live-approve").addEventListener("click", () => reviewLive(true));
    $("live-reject").addEventListener("click", () => { if (confirm("Reject this live authorization and block payment?")) reviewLive(false); });
    $("live-form").addEventListener("submit", async (event) => {
      event.preventDefault();
      const input = $("live-message");
      const message = input.value.trim();
      if (!message) return;
      input.value = "";
      await sendLiveMessage(message);
    });
    document.querySelectorAll("[data-policy]").forEach((button) => button.addEventListener("click", () => swapPolicy(button)));
    $("run-tamper").addEventListener("click", runTamper);
    $("copy-mcp").addEventListener("click", async () => {
      try {
        await navigator.clipboard.writeText(MCP_COMMAND);
        $("copy-mcp").textContent = "Command copied";
        setTimeout(() => { $("copy-mcp").textContent = "Copy run command"; }, 1800);
      } catch {
        $("copy-mcp").textContent = "Copy unavailable";
        $("copy-mcp").title = MCP_COMMAND;
      }
    });
    document.querySelectorAll("[data-review]").forEach((button) => button.addEventListener("click", () => {
      const approved = button.dataset.review === "approve";
      if (approved || confirm("Reject this authorization and abort the payment path?")) resolveReview(approved);
    }));
    $("reset-review").addEventListener("click", prepareReview);
    $("export-evidence").addEventListener("click", exportEvidence);
    document.addEventListener("keydown", (event) => {
      if (state.mode !== "replay" || event.defaultPrevented || ["INPUT", "TEXTAREA", "SELECT", "BUTTON"].includes(document.activeElement.tagName)) return;
      if (event.key === "ArrowLeft" || event.key === "ArrowRight") {
        event.preventDefault();
        loadCase(state.caseIndex + (event.key === "ArrowLeft" ? -1 : 1));
      }
      if (event.key === " ") { event.preventDefault(); toggleReplay(); }
    });
    document.addEventListener("visibilitychange", () => {
      if (!state.timeline) return;
      if (document.hidden && !state.timeline.paused()) {
        state.pausedForVisibility = true;
        state.timeline.pause();
      } else if (!document.hidden && state.pausedForVisibility) {
        state.pausedForVisibility = false;
        state.timeline.play();
      }
    });
  }

  async function initialize() {
    bindEvents();
    setupSectionMotion();
    setPlayButton(false);
    const replayReady = loadCase(0);
    verifyScenario().catch((error) => {
      $("scenario-proof").textContent = `Scenario verification failed: ${error.message}`;
      $("scenario-proof").dataset.state = "reject";
    });
    loadEvaluation();
    await replayReady;
  }

  initialize();
})();
