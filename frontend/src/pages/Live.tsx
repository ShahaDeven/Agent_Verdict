import { useEffect, useRef, useState } from 'react'
import { api, type LiveItem } from '../api'
import { Header } from '../components/Header'
import { failureWords, FLAG, money } from '../verdict'

const POLL_MS = 2000

/** Runs from your own agent, newest first, judged by Ember as they finish. Polls the backend. */
export function Live() {
  const [items, setItems] = useState<LiveItem[] | null>(null)
  const [judging, setJudging] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const seen = useRef<Set<number> | null>(null)
  const [fresh, setFresh] = useState<Set<number>>(new Set())

  useEffect(() => {
    let stop = false
    let timer: number | undefined
    const tick = async () => {
      try {
        const r = await api.live()
        if (stop) return
        // highlight runs that arrived (or got their verdict) since the page opened
        const key = (x: LiveItem) => x.id * 10 + (x.flag ? 1 : 0)
        if (seen.current) {
          const add = r.items.filter((x) => !seen.current!.has(key(x))).map((x) => x.id)
          if (add.length) setFresh((f) => new Set([...f, ...add]))
        }
        seen.current = new Set(r.items.map(key))
        setItems(r.items)
        setJudging(r.judging_enabled)
        setErr(null)
      } catch (e) {
        if (!stop) setErr((e as Error).message)
      }
      if (!stop) timer = window.setTimeout(tick, POLL_MS)
    }
    tick()
    return () => { stop = true; window.clearTimeout(timer) }
  }, [])

  const judged = items?.filter((x) => x.flag) ?? []
  const spent = judged.reduce((a, x) => a + (x.cost_usd ?? 0), 0)

  return (
    <div className="flex min-h-screen flex-col">
      <Header />
      <div className="flex flex-wrap items-stretch bg-ink text-paper">
        <span className="flex items-center gap-2.5 bg-flag-green px-6 py-3 font-display text-xl font-extrabold tracking-[0.04em] text-white sm:pl-10">
          <span aria-hidden="true" className="size-2.5 animate-pulse rounded-full bg-white" />
          LIVE
        </span>
        <span className="flex flex-[1_1_420px] items-center px-6 py-3 font-display text-[22px] font-bold uppercase tracking-[0.03em] sm:pr-10">
          Your agent's runs, judged by Muse Ember as they finish
        </span>
      </div>

      <main className="mx-auto flex w-full max-w-[1280px] flex-col gap-6 px-5 pb-14 pt-8 sm:px-10">
        <p className="m-0 flex flex-wrap gap-x-6 gap-y-1 font-mono text-[13px] text-ink-2">
          <span>{items ? `${items.length} runs` : 'Connecting…'}</span>
          <span>{judged.length} judged</span>
          <span>{judged.filter((x) => x.flag === 'yellow').length} sent to a person</span>
          <span>{money(spent)} spent on judging</span>
          <span>Judging {judging ? 'on' : 'off: start the server with --allow-spend to judge new runs'}</span>
        </p>
        {err ? <p role="alert" className="m-0 border-2 border-flag-red bg-card p-4">Can't reach the backend ({err}).</p> : null}

        {items && items.length === 0 ? (
          <div className="flex flex-col gap-3 border-2 border-ink bg-card p-6">
            <h2 className="m-0 font-display text-[26px] font-extrabold">NO LIVE RUNS YET</h2>
            <p className="m-0 max-w-[760px] text-[15px] leading-relaxed text-ink-2">
              Runs from your own agent appear here the moment they finish, then get their verdict a couple of seconds later.
              Send one with <code className="font-mono">agent-verdict judge run.json --save</code>, or have your agent POST it
              to <code className="font-mono">/api/runs</code> and then <code className="font-mono">/api/runs/&lt;id&gt;/judge</code>.
            </p>
          </div>
        ) : null}

        <ol className="m-0 flex list-none flex-col gap-3 p-0" aria-live="polite">
          {items?.map((x) => {
            const f = x.flag ? FLAG[x.flag] : null
            return (
              <li key={x.id}>
                <a href={x.flag ? `#/review/${x.id}` : undefined}
                   className={`flex flex-wrap items-stretch border-2 border-ink bg-card text-ink no-underline ${fresh.has(x.id) ? 'shadow-[6px_6px_0_var(--color-flag-yellow)]' : ''} ${x.flag ? 'hover:bg-paper-2' : ''}`}>
                  <span className={`flex w-[170px] flex-none items-center px-4 py-3 font-display text-[17px] font-extrabold tracking-[0.04em] ${f ? `${f.bg} ${f.ink}` : 'bg-paper-2 text-ink'}`}>
                    {f ? f.word.toUpperCase() : <span className="animate-pulse">JUDGING…</span>}
                  </span>
                  <span className="flex min-w-0 flex-[1_1_420px] flex-col gap-1 px-4 py-3">
                    <span className="line-clamp-2 text-[16px] font-semibold">{x.goal.split(/\n\s*\n/)[0]}</span>
                    <span className="line-clamp-1 text-sm text-ink-2">
                      Agent said: {x.final_message ? `“${x.final_message}”` : 'nothing'}
                    </span>
                    {x.flag ? (
                      <span className="text-sm text-ink-2">
                        {x.success ? 'Judge: it succeeded' : `Judge: it failed, ${failureWords(x.failure_type)}`}
                        {x.looping ? ' · looped' : ''}
                        {x.needs_review ? ` · ${x.confidence} confidence, so a person decides` : ''}
                      </span>
                    ) : null}
                  </span>
                  <span className="flex flex-col justify-center px-4 py-3 text-right font-mono text-xs text-ink-3">
                    <span>#{x.id} · {x.agent ?? x.source}</span>
                    {x.flag ? <span>{money(x.cost_usd)} · {x.latency_s?.toFixed(1)}s</span> : null}
                  </span>
                </a>
              </li>
            )
          })}
        </ol>
      </main>
    </div>
  )
}
