'use client'

import { useOrbit } from './Shell'

/**
 * Wraps one screen component so it keeps the props it was written against
 * (session, canApprove, goTo, refresh) now that routing comes from Next.js.
 * The key remounts the screen whenever refresh() is called.
 */
export function screen(Component) {
  return function Screen() {
    const orbit = useOrbit()
    if (!orbit.session) return null
    return <Component key={orbit.version} {...orbit} />
  }
}
