import { useEffect, useState } from 'react'
import { Front } from './pages/Front'
import { Live } from './pages/Live'
import { ReviewPage } from './pages/Review'

// Hash routes, so the backend can serve the build as static files:
//   #/            front page
//   #/review[/id] one run at a time from the review queue
//   #/live        runs from your own agent, judged as they arrive
// In-page jumps use buttons + scrollIntoView, never "#anchor" links, which would change the route.
function useRoute(): string {
  const [hash, setHash] = useState(() => window.location.hash || '#/')
  useEffect(() => {
    const on = () => setHash(window.location.hash || '#/')
    window.addEventListener('hashchange', on)
    return () => window.removeEventListener('hashchange', on)
  }, [])
  return hash
}

export default function App() {
  const route = useRoute()
  const page = route.startsWith('#/review') ? 'review' : route.startsWith('#/live') ? 'live' : 'front'
  // Block body on purpose: newer browsers return a Promise from scrollTo, and React would call it as a cleanup.
  useEffect(() => {
    window.scrollTo(0, 0)
  }, [page])
  if (page === 'review') return <ReviewPage />
  if (page === 'live') return <Live />
  return <Front />
}
