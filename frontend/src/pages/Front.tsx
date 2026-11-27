import { useEffect, useRef, useState, type ReactNode } from 'react'
import { api, type Run, type Summary } from '../api'
import { Header } from '../components/Header'
import { agentSaid, FLAG, headline, plainQuote, proofState } from '../verdict'

const pct = (x: number) => `${Math.round(x * 100)}%`

export function Front() {
  const [s, setS] = useState<Summary | null>(null)
  const [featured, setFeatured] = useState<Run | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const how = useRef<HTMLElement>(null)
  useEffect(() => {
    api.summary().then(setS, (e: Error) => setErr(e.message))
    api.featured().then((f) => setFeatured(f.run), () => undefined)
  }, [])

  const yellow = s?.flags.yellow ?? 0
  const stats = s && s.judged > 0
    ? [
        { big: s.auto_accuracy_vs_experts != null ? pct(s.auto_accuracy_vs_experts) : '–',
          small: `accuracy on the ${s.auto_decided.toLocaleString()} runs it decided alone`,
          note: 'Its calls checked against expert labels' },
        { big: pct(yellow / s.judged), small: `sent to a person (${yellow} runs)`,
          note: 'Everything below high confidence' },
        { big: s.cost_per_1000_runs != null ? `$${s.cost_per_1000_runs.toFixed(2)}` : '–',
          small: 'per 1,000 runs judged',
          note: 'GPT-4o cost about $13 on the same runs' },
      ]
    : null

  return (
    <div className="flex min-h-screen flex-col">
      <Header />

      <main className="mx-auto flex w-full max-w-[1280px] flex-1 flex-col gap-12 px-5 pb-16 pt-12 sm:px-10">
        <section className="grid items-start gap-10 lg:grid-cols-[minmax(0,1.15fr)_minmax(0,1fr)]">
          <div className="flex flex-col gap-5">
            <h1 className="m-0 font-display text-[clamp(44px,6.4vw,84px)] font-extrabold uppercase leading-[0.95] tracking-[0.01em]">
              AI agents say “done” when they aren't.
            </h1>
            <p className="m-0 max-w-[620px] text-xl leading-normal text-ink-2">
              Agent Verdict uses Muse Ember to check every run of a web agent against its own screenshots, for under a
              dollar per thousand runs. When it isn't sure, it hands the run to a person, with the proof.
            </p>
            <div className="mt-2 flex flex-wrap gap-3">
              <a href="#/review"
                 className="inline-flex min-h-[52px] items-center gap-2.5 bg-ink px-6 text-[17px] font-semibold text-paper no-underline hover:bg-ink-2">
                Review the runs it flagged
                {s ? <span className="font-mono text-[15px]">({s.to_review})</span> : null}
                <span aria-hidden="true">→</span>
              </a>
              <button type="button" onClick={() => how.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })}
                      className="inline-flex min-h-[52px] items-center border-2 border-ink bg-transparent px-5 text-[17px] font-semibold text-ink hover:bg-paper-2">
                How the flags work
              </button>
            </div>
          </div>
          {featured ? <Preview run={featured} /> : <div aria-hidden="true" className="hidden min-h-[360px] border-2 border-dashed border-rule lg:block" />}
        </section>

        {err ? (
          <p role="alert" className="m-0 border-2 border-flag-red bg-card p-4">
            Can't reach the backend ({err}). Start it with <code className="font-mono">agent-verdict serve</code>.
          </p>
        ) : null}
        {s && s.judged === 0 ? (
          <p className="m-0 border-2 border-ink bg-card p-4">
            No runs yet. Load the benchmark runs with <code className="font-mono">agent-verdict seed-arb</code> ($0), or
            judge your own with <code className="font-mono">agent-verdict judge run.json --save</code>.
          </p>
        ) : null}

        {stats ? (
          <div className="flex flex-col gap-3">
            <section aria-label="Results" className="grid grid-cols-1 border-y-2 border-ink sm:grid-cols-3">
              {stats.map((x, i) => (
                <div key={x.small}
                     className={`flex flex-col gap-1.5 py-6 ${i > 0 ? 'border-t border-rule sm:border-l sm:border-t-0 sm:pl-6' : 'sm:pr-6'}`}>
                  <span className="font-display text-[64px] font-extrabold leading-none">{x.big}</span>
                  <span className="text-base font-medium text-ink">{x.small}</span>
                  <span className="text-[13px] text-ink-3">{x.note}</span>
                </div>
              ))}
            </section>
            <p className="m-0 max-w-[1000px] text-[13px] leading-relaxed text-ink-3">
              Measured on the {s!.judged.toLocaleString()} test-split runs of AgentRewardBench, which were never used for
              tuning. In the benchmark's own setup (same runs, same prompt), Muse Ember has the highest precision of six
              judges: 80%, against 65–70% for GPT-4o, Claude 3.7 Sonnet, GPT-4o-mini, Qwen2.5-VL and Llama 3.3. Each of those
              gaps holds up in a paired bootstrap test, at 22× less than GPT-4o.
            </p>
          </div>
        ) : null}

        <section ref={how} className="flex scroll-mt-6 flex-col gap-5">
          <h2 className="m-0 font-display text-[32px] font-extrabold uppercase">Every run gets one flag</h2>
          <ul className="m-0 grid list-none grid-cols-1 gap-5 p-0 md:grid-cols-3">
            {([
              ['yellow', 'Yellow: a person decides', "The judge wasn't sure. You see the proof and make the call."],
              ['red', 'Red: it failed', 'Including runs where the agent claimed it had finished.'],
              ['green', 'Green: it succeeded', 'The screens confirm the goal was met.'],
            ] as const).map(([key, title, text]) => (
              <li key={key} className="flex items-start gap-3.5">
                <span aria-hidden="true" className={`h-[30px] w-11 flex-none border-2 border-ink ${FLAG[key].bg}`} />
                <span>
                  <strong className="block text-[17px]">
                    {title}
                    {s?.flags[key] != null ? <span className="ml-2 font-mono text-[13px] font-normal text-ink-3">{s.flags[key]} runs</span> : null}
                  </strong>
                  <span className="text-[15px] text-ink-2">{text}</span>
                </span>
              </li>
            ))}
          </ul>
          <div className="flex flex-col gap-2 border-l-4 border-ink py-1 pl-4">
            <strong className="text-[17px]">Plus tags, on top of the flag</strong>
            <p className="m-0 max-w-[900px] text-[15px] leading-relaxed text-ink-2">
              <Tag>LOOPED</Tag> when the agent repeated itself without progress, and <Tag>SIDE EFFECT?</Tag> when it may have
              changed something nobody asked for. A run can loop and still succeed, so these never replace the flag.
              {s && s.looped > 0 && s.looping_agreement != null ? (
                <> The benchmark's agents loop a lot: the judge tagged {s.looped} runs, the experts {s.looped_by_experts},
                  and the two agree on {pct(s.looping_agreement)} of runs.</>
              ) : null}
            </p>
          </div>
        </section>
      </main>
    </div>
  )
}

export function Tag({ children }: { children: ReactNode }) {
  return <span className="mx-0.5 inline-block border border-ink px-1.5 py-px font-mono text-xs font-semibold text-ink">{children}</span>
}

/** A small, real flagged run, so the hero shows the product instead of empty space. */
function Preview({ run }: { run: Run }) {
  const v = run.verdict!
  const proof = proofState(run)
  const f = FLAG[v.flag]
  return (
    <a href={`#/review/${run.id}`} aria-label={`Open flagged run ${run.id}`}
       className="group flex flex-col border-2 border-ink bg-card text-ink no-underline shadow-[6px_6px_0_var(--color-ink)] hover:-translate-y-0.5">
      <div className="flex items-stretch bg-ink text-paper">
        <span className={`flex items-center px-3 py-2 font-display text-[15px] font-extrabold tracking-[0.04em] ${f.bg} ${f.ink}`}>
          {f.word.toUpperCase()}
        </span>
        <span className="flex items-center px-3 py-2 font-display text-[16px] font-bold uppercase leading-tight tracking-[0.02em]">
          {headline(v, run)}
        </span>
      </div>
      <div className="flex flex-col gap-3 p-4">
        <p className="m-0 line-clamp-2 text-[15px] font-semibold leading-snug">{run.goal.split(/\n\s*\n/)[0]}</p>
        <p className="m-0 line-clamp-2 text-sm text-ink-2"><span className="font-mono text-xs text-ink-3">AGENT SAID </span>{agentSaid(run)}</p>
        {proof != null && run.screens.includes(proof) ? (
          <img src={api.screenUrl(run.id, proof)} alt="The screen the judge points to as proof"
               className="block max-h-[240px] w-full border border-ink object-cover object-top" />
        ) : null}
        {v.evidence_quote ? (
          <p className="m-0 line-clamp-2 text-sm">
            <span className="mr-2 border border-ink bg-flag-yellow px-1.5 py-px font-mono text-[11px] font-semibold">PROOF</span>
            {plainQuote(v.evidence_quote)}
          </p>
        ) : null}
        <span className="text-sm font-semibold underline decoration-2 underline-offset-4 group-hover:no-underline">Open this run →</span>
      </div>
    </a>
  )
}
