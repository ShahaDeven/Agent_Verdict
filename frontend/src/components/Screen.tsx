import { useState } from 'react'

/** A screenshot in a plain browser frame, with the page's URL. */
export function Screen({ src, url, alt }: { src: string | null; url: string; alt: string }) {
  const [failed, setFailed] = useState<string | null>(null)
  return (
    <div className="border-2 border-ink bg-card">
      <div className="flex items-center border-b border-rule bg-paper-2 px-3 py-1.5">
        <span className="truncate font-mono text-xs text-ink-2">{url || ' '}</span>
      </div>
      {src && failed !== src ? (
        <img src={src} alt={alt} onError={() => setFailed(src)} className="block h-auto w-full" />
      ) : (
        <div className="flex min-h-[220px] items-center px-6 py-10 text-sm text-ink-3">
          {src ? "This screenshot couldn't be loaded." : "The judge wasn't shown this screen. Steps with a dot on the replay below have one."}
        </div>
      )}
    </div>
  )
}
