export function Logo() {
  return (
    <svg
      viewBox="0 0 210 48"
      height="90"
      role="img"
      aria-label="Intelcrier"
      className="intelcrier-logo"
    >
      {/* Globe mark — native geometry: cx=60 cy=70 r=34, arcs crown top */}
      {/* Bounding box: x=26–94, y≈6–104 → scale 0.41 to fill 40px height */}
      <g transform="translate(4 4) scale(0.41) translate(-26 -6)">
        <circle cx="60" cy="70" r="34" fill="none" className="logo-globe" strokeWidth="2.4" />
        <ellipse cx="60" cy="70" rx="12" ry="34" fill="none" className="logo-globe" strokeWidth="1.8" />
        <path d="M53.11 30.21 A9 9 0 0 1 66.89 30.21" fill="none" className="logo-globe" strokeWidth="2.4" strokeLinecap="round" />
        <path d="M47.74 25.71 A16 16 0 0 1 72.26 25.71" fill="none" className="logo-globe" strokeWidth="2.4" strokeLinecap="round" opacity="0.6" />
        <path d="M42.38 21.21 A23 23 0 0 1 77.62 21.21" fill="none" className="logo-globe" strokeWidth="2.4" strokeLinecap="round" opacity="0.38" />
        <circle cx="60" cy="36" r="4.6" className="logo-globe-dot" />
      </g>
      <text x="36" y="25" className="logo-wordmark" fontSize="20" fontFamily="Georgia, 'Times New Roman', serif">
        Intelcrier
      </text>
      <text x="37" y="37" className="logo-tagline" fontSize="6.5" fontFamily="monospace" letterSpacing="1.8">
        A CIVIC INTELLIGENCE COMPANY
      </text>
    </svg>
  );
}
