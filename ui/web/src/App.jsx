import React, { useCallback, useEffect, useRef, useState } from "react";

const SCENARIOS = ["all", "buying", "browsing", "intent_override", "boundary"];
const usd = (n) => (n === 0 ? "$0.00" : n < 0.01 ? `$${n.toFixed(6)}` : `$${n.toFixed(4)}`);

export default function App() {
  const [health, setHealth] = useState(null);
  const [sessions, setSessions] = useState([]);
  const [scenario, setScenario] = useState("all");
  const [picked, setPicked] = useState("");
  const [mode, setMode] = useState("offline");
  const [extract, setExtract] = useState("shipped");
  const [speed, setSpeed] = useState(1);
  const [running, setRunning] = useState(false);
  const [meta, setMeta] = useState(null);
  const [turns, setTurns] = useState([]);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);

  const queue = useRef([]);
  const source = useRef(null);
  const timer = useRef(null);
  const finished = useRef(false);
  const speedRef = useRef(speed);
  speedRef.current = speed;

  useEffect(() => {
    fetch("/api/health").then((r) => r.json()).then((h) => {
      setHealth(h);
      if (!h.llm_available) { setMode("offline"); setExtract("shipped"); }   // never offer a mode the server cannot run
    }).catch(() => setError("API not reachable. Is ui/server.py running?"));
  }, []);

  useEffect(() => {
    const q = scenario === "all" ? "" : `?scenario=${scenario}`;
    fetch(`/api/sessions${q}`).then((r) => r.json()).then((s) => {
      setSessions(s);
      setPicked(s[0]?.session_id ?? "");
    }).catch(() => {});
  }, [scenario]);

  const closeStream = useCallback(() => {
    source.current?.close();
    source.current = null;
  }, []);

  const stop = useCallback(() => {
    closeStream();
    clearInterval(timer.current);
    timer.current = null;
    queue.current = [];
    setRunning(false);
  }, [closeStream]);

  useEffect(() => stop, [stop]);

  // Turns are buffered as they stream in, then released on a timer so the conversation is watchable.
  const drain = useCallback(() => {
    const item = queue.current.shift();
    if (!item) return;
    if (item.kind === "turn") setTurns((t) => [...t, item.data]);
    if (item.kind === "done") { setResult(item.data); stop(); }
  }, [stop]);

  const run = useCallback(() => {
    if (!picked) return;
    stop();
    setTurns([]); setResult(null); setMeta(null); setError(null);
    finished.current = false;
    setRunning(true);

    const es = new EventSource(`/api/run/${picked}?top=10&mode=${mode}&extract=${extract}`);
    source.current = es;
    es.addEventListener("start", (e) => setMeta(JSON.parse(e.data)));
    es.addEventListener("turn", (e) => queue.current.push({ kind: "turn", data: JSON.parse(e.data) }));
    es.addEventListener("superseded", () => {
      finished.current = true;
      closeStream();
      setError("this run was superseded by a newer one");
      stop();
    });
    es.addEventListener("done", (e) => {
      // The server streams far faster than we display. Close as soon as the last event ARRIVES —
      // EventSource auto-reconnects on stream close, which would re-run the whole session server-side
      // while turns are still being paced out. The payload stays queued for its turn on screen.
      finished.current = true;
      queue.current.push({ kind: "done", data: JSON.parse(e.data) });
      closeStream();
    });
    es.onerror = () => {
      if (finished.current) return;
      closeStream();
      if (!queue.current.length) { setError("stream failed, check the server log"); stop(); }
    };

    timer.current = setInterval(() => drain(), 2600 / speedRef.current);
  }, [picked, mode, extract, stop, drain, closeStream]);

  // Restart the pacing timer when the speed slider moves mid-run.
  useEffect(() => {
    if (!running || !timer.current) return;
    clearInterval(timer.current);
    timer.current = setInterval(() => drain(), 2600 / speed);
  }, [speed, running, drain]);

  const last = turns[turns.length - 1];
  const cost = result?.cost ?? last?.cost;
  const tail = useRef(null);

  // Keep the newest turn in view as it is revealed, or the whole demo scrolls off the bottom unattended.
  useEffect(() => { tail.current?.scrollIntoView({ behavior: "smooth", block: "end" }); }, [turns.length, result]);

  return (
    <div className="app">
      <header>
        <div className="brand">
          <h1>Shopping Copilot</h1>
        </div>
        <div className="controls">
          <select value={scenario} onChange={(e) => setScenario(e.target.value)} disabled={running}>
            {SCENARIOS.map((s) => <option key={s} value={s}>{s.replace("_", " ")}</option>)}
          </select>
          <select value={picked} onChange={(e) => setPicked(e.target.value)} disabled={running} className="wide">
            {sessions.map((s) => (
              <option key={s.session_id} value={s.session_id}>
                {s.session_id} · {s.scenario} · {s.difficulty}
              </option>
            ))}
          </select>
          <select
            value={mode}
            onChange={(e) => { setMode(e.target.value); if (e.target.value !== "online") setExtract("shipped"); }}
            disabled={running}
            className={`mode ${mode}`}
            title={health && !health.llm_available ? health.llm_reason : "offline is the scored configuration"}
          >
            <option value="offline">Offline</option>
            <option value="online" disabled={health ? !health.llm_available : true}>
              Online{health && !health.llm_available ? " (unavailable)" : ""}
            </option>
          </select>
          <select
            value={extract}
            onChange={(e) => setExtract(e.target.value)}
            disabled={running || mode !== "online"}
            className="mode"
            title={mode !== "online" ? "LLM extraction needs online mode" : "who parses the customer's message"}
          >
            <option value="shipped">Templates</option>
            <option value="fallback">Template &rarr; LLM</option>
            <option value="llm">LLM only</option>
          </select>
          <button className="run" onClick={running ? stop : run} disabled={!picked}>
            {running ? "■ Stop" : "▶ Run session"}
          </button>
          <label className="speed">
            speed
            <input type="range" min="0.5" max="4" step="0.5" value={speed} onChange={(e) => setSpeed(+e.target.value)} />
            <b>{speed}×</b>
          </label>
        </div>
      </header>

      {error && <div className="error">{error}</div>}

      <div className="main">
        <section className="chat">
          {meta && <SessionCard meta={meta} />}
          {!meta && !error && <div className="placeholder">Pick a session and press <b>Run</b>.<br />The evaluator's own simulator plays the customer.</div>}
          {turns.map((t) => <Turn key={t.turn} t={t} />)}
          {result && <ResultCard r={result} />}
          {running && <div className="thinking"><span /><span /><span /></div>}
          <div ref={tail} />
        </section>

        <aside className="side">
          <CostPanel cost={cost} health={health} result={result} turns={turns} runMode={meta?.mode ?? mode} />
          <TracePanel turns={turns} />
        </aside>
      </div>
    </div>
  );
}

function SessionCard({ meta }) {
  return (
    <div className="session-card">
      <div className="row">
        <span className={`tag s-${meta.scenario}`}>{meta.scenario.replace("_", " ")}</span>
        <span className="tag">{meta.difficulty}</span>
        <span className="tag">{meta.category}</span>
      </div>
      <div className="hidden-card">
        <div className="hc-title">Target:</div>
        <div className="hc-body">
          <code>{meta.target.asin}</code> {meta.target.title}
          <div className="hc-constraints">
            {meta.intent_card.hard.map((c, i) => <span key={`h${i}`} className="chip hard">{c}</span>)}
            {meta.intent_card.soft.map((c, i) => <span key={`s${i}`} className="chip soft">{c}</span>)}
          </div>
        </div>
      </div>
      <div className="profile">
        profile tags: {meta.profile.preference_tags?.map((t) => <span key={t} className="chip">{t}</span>)}
      </div>
    </div>
  );
}

function Turn({ t }) {
  const found = t.shelf.some((s) => s.is_target) && t.counts;
  return (
    <div className={`turn ${found ? "hit" : ""}`}>
      <div className="turn-divider"><span>turn {t.turn}</span></div>

      <div className="row-right">
        <div className="bubble customer"><p>{t.customer}</p></div>
      </div>

      <div className="row-left">
        <div className="understood">
          <span className="pill">{t.trace.extract.kind}</span>
          {t.trace.extract.new_constraints.length > 0 ? (
            t.trace.extract.new_constraints.map((c, i) => <span key={i} className="chip new">+ {c.text}</span>)
          ) : (
            <span className="chip muted">no new constraint</span>
          )}
        </div>
      </div>

      <div className="row-left">
        <div className="bubble agent">
          <p>{t.agent}</p>
          <div className="ask">asks <code>{t.ask_attribute}</code> · {t.shelf_size} shown · {t.latency_ms.toFixed(0)} ms
            {t.cost.turn_usd > 0 && <> · <b>{usd(t.cost.turn_usd)}</b></>}
          </div>
        </div>
      </div>

      {t.trace.rank.committed_to_one && (
        <div className="note">Many candidates tie on everything stated so far, so the copilot commits to one pick and asks the tie-splitting question.</div>
      )}

      <div className="shelf">
        {t.shelf.map((s) => (
          <div key={s.asin} className={`item ${s.is_target && t.counts ? "target" : ""}`}>
            <span className="rk">{s.rank}</span>
            <span className={`delta ${s.delta === "NEW" ? "new" : s.delta.startsWith("↑") ? "up" : s.delta.startsWith("↓") ? "down" : ""}`}>{s.delta}</span>
            <span className="asin">{s.asin}</span>
            <span className="title">{s.title}</span>
            {s.matched.length > 0 && <span className="matched">{s.matched.join(" · ")}</span>}
            {s.is_target && t.counts && <span className="target-flag">TARGET</span>}
          </div>
        ))}
        {t.dropped.length > 0 && <div className="dropped">dropped out: {t.dropped.join(", ")}</div>}
      </div>
    </div>
  );
}

function ResultCard({ r }) {
  return (
    <div className={`result ${r.hit ? "ok" : "miss"}`}>
      <div className="r-head">{r.hit ? `HIT on turn ${r.hit_turn} at rank ${r.rank}` : "MISS after 10 turns"}</div>
      <div className="r-body">
        <div><span>target</span><code>{r.target.asin}</code> {r.target.title}</div>
        <div className="r-score">
          <div><b>{r.hit ? "1.00" : "0.00"}</b><span>Hit@10</span></div>
          <div><b>{r.reciprocal_rank.toFixed(3)}</b><span>RR</span></div>
          <div><b>{r.hit_turn ?? 11}</b><span>turns</span></div>
          <div className="hi"><b>{r.score.toFixed(3)}</b><span>session score</span></div>
        </div>
      </div>
    </div>
  );
}

function CostPanel({ cost, health, result, turns, runMode }) {
  const live = runMode === "online";
  const ms = turns.map((t) => t.latency_ms);

  // Offline has no tokens and no cost, so a panel of zeroes says nothing. Report latency only.
  if (!live) {
    return (
      <div className="panel">
        <h3>Performance</h3>
        {ms.length === 0 ? (
          <div className="muted small">Deterministic, no network. Run a session to see per-turn latency.</div>
        ) : (
          <>
            <div className="metric"><span>latency p50</span><b>{median(ms).toFixed(0)} ms</b></div>
            <div className="metric"><span>slowest turn</span><b>{Math.max(...ms).toFixed(0)} ms</b></div>
            <div className="metric"><span>turns</span><b>{turns.length}</b></div>
          </>
        )}
      </div>
    );
  }

  const totalTokens = cost?.total_tokens ?? cost?.tokens ?? [0, 0];
  const total = cost?.total_usd ?? cost?.session_usd ?? 0;
  return (
    <div className="panel">
      <h3>Cost &amp; usage</h3>
      <div className="metric"><span>session cost</span><b>{usd(total)}</b></div>
      <div className="metric"><span>prompt tokens</span><b>{totalTokens[0].toLocaleString()}</b></div>
      <div className="metric"><span>completion tokens</span><b>{totalTokens[1].toLocaleString()}</b></div>
      <div className="metric"><span>turns</span><b>{turns.length}</b></div>
      {ms.length > 0 && <div className="metric"><span>latency p50</span><b>{median(ms).toFixed(0)} ms</b></div>}
      {result && (
        <>
          <div className="metric"><span>cost / turn</span><b>{usd(result.cost.per_turn_usd)}</b></div>
          <div className="metric hi">
            <span>projected · {result.cost.private_set_size} sessions</span>
            <b>${result.cost.projected_private_set_usd.toFixed(2)}</b>
          </div>
          <div className="basis">{result.cost.projection_basis}</div>
          {result.cost.unpriced_models?.length > 0 && (
            <div className="warn">no rate in PRICING for {result.cost.unpriced_models.join(", ")}, so the cost above excludes it</div>
          )}
        </>
      )}
      <div className="models">
        {Object.entries(health?.models || {}).map(([k, v]) => (
          <div key={k}><span>{k}</span><code>{v}</code></div>
        ))}
      </div>
    </div>
  );
}

function TracePanel({ turns }) {
  const [open, setOpen] = useState(null);
  useEffect(() => { if (turns.length) setOpen(turns[turns.length - 1].turn); }, [turns.length]);
  return (
    <div className="panel trace">
      <h3>Trace</h3>
      <div className="trace-scroll">
      {turns.length === 0 && <div className="muted small">Per-turn pipeline steps appear here.</div>}
      {turns.map((t) => (
        <div key={t.turn} className="trace-turn">
          <button onClick={() => setOpen(open === t.turn ? null : t.turn)}>
            {open === t.turn ? "▾" : "▸"} turn {t.turn}
            <span className="t-ms">{t.latency_ms.toFixed(0)}ms</span>
          </button>
          {open === t.turn && (
            <div className="trace-body">
              <Step name="extract" detail={`${t.trace.extract.path} · ${t.trace.extract.kind}`}>
                {t.trace.extract.new_constraints.map((c, i) => (
                  <div key={i} className="kv"><code>{c.text}</code><span>{c.provenance}</span></div>
                ))}
              </Step>
              <Step name="state" detail={`${t.trace.state.ledger_size} constraints · asked: ${t.trace.state.consumed.join(", ") || "none"}`}>
                <div className="kv"><span>category</span><code>{t.trace.state.categories.join(", ") || "none"}</code></div>
                {t.trace.state.ledger.map((c, i) => <div key={i} className="kv"><code>{c}</code></div>)}
              </Step>
              <Step name="build_terms" detail={`${t.trace.retrieve.term_count} / ${t.trace.retrieve.max_terms} terms`}>
                <div className="terms">{t.trace.retrieve.terms.map((x, i) => <span key={i}>{x}</span>)}</div>
              </Step>
              <Step name="retrieve" detail={`BM25 pool ${t.trace.retrieve.pool}`} />
              <Step name="rank" detail={`${t.trace.rank.shown} shown · cutoff "${t.trace.rank.cutoff_rule}"`}>
                {t.trace.rank.top_matched.length > 0 && (
                  <div className="kv"><span>top-1 matched</span><code>{t.trace.rank.top_matched.join(" · ")}</code></div>
                )}
              </Step>
              <Step name="respond" detail={`asks ${t.ask_attribute}`}>
                {t.trace.llm_calls.length === 0
                  ? <div className="kv muted">no LLM call, fully deterministic</div>
                  : t.trace.llm_calls.map((c, i) => (
                      <div key={i} className="kv llm">
                        <span>{c.layer}</span><code>{c.model}</code>
                        <span>{c.prompt_tokens}→{c.completion_tokens}</span>
                        <b className={c.unpriced ? "unpriced" : ""}>{c.unpriced ? "unpriced" : usd(c.cost_usd)}</b>
                      </div>
                    ))}
              </Step>
            </div>
          )}
        </div>
      ))}
      </div>
    </div>
  );
}

function Step({ name, detail, children }) {
  return (
    <div className="step">
      <div className="step-head"><span className="step-name">{name}</span><span className="step-detail">{detail}</span></div>
      {children && <div className="step-body">{children}</div>}
    </div>
  );
}

function median(xs) {
  if (!xs.length) return 0;
  const s = [...xs].sort((a, b) => a - b);
  return s[Math.floor(s.length / 2)];
}
