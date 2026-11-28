import { useEffect, useState, type ReactNode } from 'react'
import { getResults, type Diff, type ResultsSummary } from '../api'
import { Header } from '../components/Header'

const pct = (x: number | null | undefined, d = 0) => (x == null ? '–' : `${(x * 100).toFixed(d)}%`)
const pts = (d: Diff) => `${d.diff >= 0 ? '+' : ''}${(d.diff * 100).toFixed(1)}`
const ci = (d: Diff) => `${(d.lo * 100).toFixed(1)} to ${(d.hi * 100).toFixed(1)}`

/** A horizontal bar inside a table cell. The number is always printed as text next to it. */
function Bar({ value, max = 1, strong, label }: { value: number; max?: number; strong?: boolean; label: string }) {
  return (
    <span className="flex items-center gap-2.5" title={label}>
      <span className="relative h-3.5 w-full min-w-[80px] max-w-[260px] bg-paper-2" aria-hidden="true">
        <span className={`absolute inset-y-0 left-0 rounded-r-[4px] ${strong ? 'bg-ink' : 'bg-rule'}`}
              style={{ width: `${Math.max(0, Math.min(1, value / max)) * 100}%` }} />
      </span>
    </span>
  )
}

function Section({ id, kicker, title, children }: { id: string; kicker: string; title: string; children: ReactNode }) {
  return (
    <section aria-labelledby={id} className="flex flex-col gap-4 border-t-2 border-ink pt-6">
      <span className="font-mono text-[13px] text-ink-3">{kicker}</span>
      <h2 id={id} className="m-0 max-w-[1000px] font-display text-[32px] font-extrabold uppercase leading-tight">{title}</h2>
      {children}
    </section>
  )
}

const th = 'border-b-2 border-ink px-3 py-2 text-left text-[13px] font-semibold text-ink-2'
const td = 'border-b border-rule px-3 py-2.5 align-middle'

export function Results() {
  const [r, setR] = useState<ResultsSummary | null>(null)
  const [err, setErr] = useState<string | null>(null)
  useEffect(() => { getResults().then(setR, (e: Error) => setErr(e.message)) }, [])

  return (
    <div className="flex min-h-screen flex-col">
      <Header />
      <main className="mx-auto flex w-full max-w-[1280px] flex-col gap-12 px-5 pb-16 pt-10 sm:px-10">
        <section className="flex flex-col gap-3">
          <h1 className="m-0 font-display text-[clamp(40px,5.5vw,68px)] font-extrabold uppercase leading-[0.95]">Results</h1>
          <p className="m-0 max-w-[820px] text-lg text-ink-2">
            Every number here comes from runs the judge was never tuned on (the AgentRewardBench test split) or from our own
            agent on sites whose records give the true outcome. Intervals are 95% paired bootstrap.
          </p>
          {err ? <p role="alert" className="m-0 border-2 border-ink bg-card p-4">No results yet ({err}). Build them with{' '}
            <code className="font-mono">python scripts\build_results.py</code> ($0).</p> : null}
          {!r && !err ? <p className="m-0 text-ink-3">Loading…</p> : null}
        </section>

        {r ? <>
          {/* 1. fair comparison */}
          <Section id="fair" kicker={`1 · SAME RUNS, SAME PROMPT · ${r.fair.runs.toLocaleString()} held-out runs, ${r.fair.successes} successful per the experts`}
                   title="The most precise of six judges, at a fraction of the cost">
            <div className="overflow-x-auto border border-rule bg-card">
              <table className="w-full min-w-[860px] border-collapse text-[15px]">
                <thead><tr>
                  <th className={th}>Judge</th><th className={th}>Precision</th><th className={`${th} text-right`}>Recall</th>
                  <th className={`${th} text-right`}>Accuracy (95% CI)</th><th className={`${th} text-right`}>Cost per 1,000 runs</th>
                  <th className={th}>Ember's precision vs this judge</th>
                </tr></thead>
                <tbody>
                  {r.fair.judges.map((j) => {
                    const ember = !j.ember_minus
                    return (
                      <tr key={j.judge} className={ember ? 'bg-paper-2 font-semibold' : ''}>
                        <td className={td}>{j.judge}</td>
                        <td className={td}><span className="flex items-center gap-2.5"><span className="w-12 font-mono">{pct(j.precision)}</span>
                          <Bar value={j.precision} strong={ember} label={`${j.judge}: precision ${pct(j.precision, 1)}`} /></span></td>
                        <td className={`${td} text-right font-mono`}>{pct(j.recall)}</td>
                        <td className={`${td} text-right font-mono`}>{pct(j.accuracy)} <span className="text-ink-3">({pct(j.accuracy_ci?.[0])}–{pct(j.accuracy_ci?.[1])})</span></td>
                        <td className={`${td} text-right font-mono`}>{j.self_hosted ? 'needs GPUs' : `$${j.cost_per_1000.toFixed(2)}`}</td>
                        <td className={`${td} text-sm`}>{j.ember_minus
                          ? <>{pts(j.ember_minus.precision)} points <span className="text-ink-3">({ci(j.ember_minus.precision)})</span>
                              {j.ember_minus.precision.significant ? ' · significant' : ' · not significant'}</>
                          : <span className="text-ink-3">this is Ember</span>}</td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
            <p className="m-0 max-w-[980px] text-[15px] text-ink-2">
              When Ember says an agent succeeded, it is right {pct(r.fair.judges[0].precision)} of the time, against 65–70% for the others; the
              price of that strictness is lower recall, and the runs it is unsure about go to a person. The published judges' costs are what
              the benchmark's authors paid; the two self-hosted models list $0 because GPU time isn't counted.
            </p>
          </Section>

          {/* 2. escalation */}
          <Section id="esc" kicker={`2 · VERDICT V2 + A PERSON · ${r.v2.runs.toLocaleString()} held-out runs`}
                   title="It knows when it's unsure: send those to a person">
            <div className="grid gap-6 lg:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)]">
              <div className="overflow-x-auto border border-rule bg-card">
                <table className="w-full min-w-[560px] border-collapse text-[15px]">
                  <thead><tr><th className={th}>Send to a person</th><th className={`${th} text-right`}>Runs reviewed</th>
                    <th className={th}>Overall accuracy</th></tr></thead>
                  <tbody>{r.v2.escalation.map((e) => {
                    const chosen = e.rule.includes('rule')
                    return (
                      <tr key={e.rule} className={chosen ? 'bg-paper-2 font-semibold' : ''}>
                        <td className={td}>{e.rule}</td>
                        <td className={`${td} text-right font-mono`}>{pct(e.reviewed)}</td>
                        <td className={td}><span className="flex items-center gap-2.5"><span className="w-12 font-mono">{pct(e.accuracy_overall)}</span>
                          <Bar value={e.accuracy_overall} strong={chosen} label={`${e.rule}: ${pct(e.accuracy_overall, 1)} overall`} /></span></td>
                      </tr>
                    )
                  })}</tbody>
                </table>
              </div>
              <dl className="m-0 grid grid-cols-3 gap-4 self-start">
                {(['high', 'medium', 'low'] as const).map((lvl) => (
                  <div key={lvl} className="border border-rule bg-card p-4">
                    <dt className="text-[13px] text-ink-3">{lvl} confidence · {r.v2.by_confidence[lvl]?.runs} runs</dt>
                    <dd className="m-0 font-display text-[40px] font-extrabold leading-tight">{pct(r.v2.by_confidence[lvl]?.accuracy)}</dd>
                    <dd className="m-0 text-[13px] text-ink-3">accurate</dd>
                  </div>
                ))}
              </dl>
            </div>
            <p className="m-0 max-w-[980px] text-[15px] text-ink-2">
              The confidence is honest: high-confidence verdicts are right {pct(r.v2.by_confidence.high?.accuracy)} of the time, low-confidence ones{' '}
              {pct(r.v2.by_confidence.low?.accuracy)}. The rule was set on the dev split before this test, at {`$${r.v2.cost_per_1000.toFixed(2)}`} per 1,000 runs.
            </p>
          </Section>

          {/* 3. best of attempts */}
          <Section id="best" kicker={`3 · BEST OF SEVERAL ATTEMPTS · ${r.best_attempt.tasks} tasks, each tried by 2–4 different agents`}
                   title="Let the judge pick the attempt, and agents solve more tasks">
            <div className="overflow-x-auto border border-rule bg-card">
              <table className="w-full min-w-[560px] border-collapse text-[15px]">
                <thead><tr><th className={th}>How the attempt is chosen</th><th className={th}>Tasks solved</th></tr></thead>
                <tbody>
                  {[["Judge's pick (Muse Ember)", r.best_attempt.judge, true] as const,
                    ...Object.entries(r.best_attempt.agents).map(([a, v]) => [`Always ${a}${a === r.best_attempt.best_agent ? ' (best single agent)' : ''}`, v, false] as const),
                    ['Random attempt', r.best_attempt.random, false] as const,
                    ['Ceiling: pick right whenever any attempt succeeded', r.best_attempt.ceiling, false] as const,
                  ].map(([name, v, strong]) => (
                    <tr key={name} className={strong ? 'bg-paper-2 font-semibold' : ''}>
                      <td className={td}>{name}</td>
                      <td className={td}><span className="flex items-center gap-2.5"><span className="w-14 font-mono">{pct(v, 1)}</span>
                        <Bar value={v} max={0.6} strong={strong} label={`${name}: ${pct(v, 1)}`} /></span></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <ul className="m-0 flex max-w-[980px] list-none flex-col gap-1.5 p-0 text-[15px] text-ink-2">
              <li><strong className="text-ink">{pts(r.best_attempt.vs_best_agent)} points</strong> over always using {r.best_attempt.best_agent} (95% CI {ci(r.best_attempt.vs_best_agent)}
                {r.best_attempt.vs_best_agent.significant ? ', significant' : ''}), even though that baseline is picked with hindsight.</li>
              <li>It captures {pct(r.best_attempt.share_of_gain)} of the possible gain from choosing well (random to ceiling).</li>
              <li>By benchmark: {Object.entries(r.best_attempt.by_benchmark).map(([b, x]) => `${b} ${pct(x.judge)} vs ${pct(x.best_agent)}`).join(' · ')}.
                WorkArena is the exception: the judge is strict on enterprise forms, so it sometimes passes over a real success.</li>
            </ul>
          </Section>

          {/* 4. live */}
          <Section id="live" kicker="4 · OUR OWN EMBER AGENT, ON SITES THAT KNOW THE TRUTH"
                   title="Live: judged as runs finish, checked against the sites' records">
            <div className="grid gap-4 md:grid-cols-2">
              {r.live.agents.map((a) => (
                <div key={a.agent} className="flex flex-col gap-3 border-2 border-ink bg-card p-5">
                  <h3 className="m-0 text-lg font-semibold">{a.agent}</h3>
                  <dl className="m-0 grid grid-cols-2 gap-x-6 gap-y-3">
                    <div><dt className="text-[13px] text-ink-3">Judge agreed with the truth</dt>
                      <dd className="m-0 font-display text-[34px] font-extrabold leading-tight">{a.agree} of {a.scored}</dd></div>
                    <div><dt className="text-[13px] text-ink-3">False "done" claims caught</dt>
                      <dd className="m-0 font-display text-[34px] font-extrabold leading-tight">{a.false_claims ? `${a.false_claims_caught} of ${a.false_claims}` : 'none made'}</dd></div>
                    <div><dt className="text-[13px] text-ink-3">Agent succeeded</dt><dd className="m-0 font-mono">{a.agent_succeeded} of {a.scored}</dd></div>
                    <div><dt className="text-[13px] text-ink-3">Honestly declined an impossible task</dt><dd className="m-0 font-mono">{a.declined}</dd></div>
                    <div><dt className="text-[13px] text-ink-3">Sent to a person</dt><dd className="m-0 font-mono">{a.sent_to_person} of {a.runs}</dd></div>
                    <div><dt className="text-[13px] text-ink-3">Cost per verdict</dt><dd className="m-0 font-mono">{a.cost_per_verdict != null ? `$${a.cost_per_verdict.toFixed(4)}` : '–'}</dd></div>
                  </dl>
                </div>
              ))}
            </div>
            <p className="m-0 max-w-[980px] text-[15px] text-ink-2">
              Our Ember agent is strong and honest on these sites, so its runs mostly test whether the judge confirms real success. The text-only
              setting (no screenshots, like AgentRewardBench's Llama 3.3 agent) is where false "done" claims appear; the judge, which sees the
              screenshots, catches them.
            </p>
          </Section>

          {/* 5. limits */}
          <Section id="limits" kicker="5 · WHAT WE DON'T CLAIM" title="Limits, stated plainly">
            <ul className="m-0 flex max-w-[980px] list-disc flex-col gap-1.5 pl-5 text-[15px] text-ink-2">
              <li>Side effects: the judge stopped crying wolf, but catches only some real side effects, so the flag is a hint for the reviewer, not a measured detector.</li>
              <li>Enterprise forms (WorkArena): the judge is strict and misses real successes when the final screen doesn't show every field.</li>
              <li>The dev split was used for tuning, so it is left out of every number here.</li>
              <li>Live failures are few: the tasks and sites are ours, and the main agent rarely fails on them.</li>
            </ul>
            <p className="m-0 font-mono text-[13px] text-ink-3">
              Built {new Date(r.generated_at).toLocaleString()} · total Muse Ember spend for the whole project ${r.total_spend_usd.toFixed(2)}
            </p>
          </Section>
        </> : null}
      </main>
    </div>
  )
}
