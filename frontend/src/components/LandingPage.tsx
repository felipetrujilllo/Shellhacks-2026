import type { ReactNode } from 'react'
import '../landing.css'
import LandingHero from './LandingHero'

/** Where "Try the map" and "Get Started" go: the planned hash route for the map workspace (App). */
export const MAP_HREF = '#/map'

const FEATURES: { title: string; text: string; icon: ReactNode }[] = [
  {
    title: 'Visualize projects',
    text: 'See planned transmission work from neighboring utilities on one map.',
    icon: <path d="M9 4 3 6v14l6-2 6 2 6-2V4l-6 2-6-2zM9 4v14M15 6v14" />,
  },
  {
    title: 'Find overlaps',
    text: 'Flag cross-utility projects within 25 miles of each other.',
    icon: <path d="M17.5 11a6.5 6.5 0 1 1-13 0 6.5 6.5 0 0 1 13 0zM20 20l-4.4-4.4" />,
  },
  {
    title: 'Prioritize opportunities',
    text: 'Rank pairs by distance, timing and potential savings.',
    icon: <path d="M4 20h16M7 16v-4M12 16V7M17 16v-7" />,
  },
  {
    title: 'Estimate impact',
    text: 'See a rough estimate of what coordinating could save.',
    icon: (
      <>
        <circle cx="12" cy="12" r="9" />
        <path d="M14.8 9.2c-.5-1-1.6-1.6-2.8-1.6-1.6 0-2.8.9-2.8 2.1 0 2.9 5.8 1.4 5.8 4.4 0 1.2-1.3 2.2-3 2.2-1.3 0-2.5-.6-3-1.6M12 6v1.6M12 16.3V18" />
      </>
    ),
  },
]

const NAV_LINKS = [
  { label: 'Product', href: '#product' },
  { label: 'Data', href: '#data' },
  { label: 'About', href: '#about' },
]

function LineIcon({ children, size = 24 }: { children: ReactNode; size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false">
      {children}
    </svg>
  )
}

/** Marketing landing page. Not wired into the app yet: see landing-preview.html for the dev-only preview. */
export default function LandingPage({ mapHref = MAP_HREF }: { mapHref?: string }) {
  return (
    <div className="landing">
      <section className="landing-hero" id="top">
        {/* To use a real photo instead, replace <LandingHero /> with
            <img className="landing-hero-art" src="/landing/hero.jpg" alt="" /> (object-fit is already set). */}
        <LandingHero />
        <div className="landing-hero-shade" />

        <header className="landing-nav">
          <a className="landing-brand" href="#top">
            <img className="landing-logo" src="/relay-logo.svg" alt="Relay" width="162" height="36" />
          </a>
          <nav aria-label="Primary" className="landing-nav-links">
            <ul>
              {NAV_LINKS.map(({ label, href }) => (
                <li key={href} className="landing-nav-anchor">
                  <a href={href}>{label}</a>
                </li>
              ))}
              <li>
                <a className="landing-button landing-button-primary landing-button-small" href={mapHref}>
                  Get Started
                </a>
              </li>
            </ul>
          </nav>
        </header>

        <div className="landing-hero-copy">
          <h1 className="landing-headline">
            <span>Plan together.</span>{' '}
            <span className="landing-headline-accent">Build once.</span>
          </h1>
          <p className="landing-subline">
            Relay finds where neighboring utilities' planned transmission projects overlap, before the digging starts.
          </p>
          <div className="landing-actions">
            <a className="landing-button landing-button-primary" href={mapHref}>
              Try the map
              <LineIcon size={18}>
                <path d="M5 12h14M13 6l6 6-6 6" />
              </LineIcon>
            </a>
          </div>
        </div>

        <ul className="landing-features" id="product">
          {FEATURES.map(({ title, text, icon }) => (
            <li key={title} className="landing-feature">
              <span className="landing-feature-icon">
                <LineIcon>{icon}</LineIcon>
              </span>
              <h2>{title}</h2>
              <p>{text}</p>
            </li>
          ))}
        </ul>
      </section>

      <section className="landing-info">
        <div id="data">
          <h2>Data</h2>
          <p>
            Built on public filings: Dominion Energy South Carolina's project sheets and Georgia Power's IRP, located
            with OpenStreetMap.
          </p>
        </div>
        <div id="about">
          <h2>About</h2>
          <p>Built at ShellHacks 2026 for the Sperry Tech Gridlock challenge.</p>
        </div>
      </section>
    </div>
  )
}
