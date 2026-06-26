import { useState, useRef } from "react";
import { useNavigate } from "react-router-dom";
import type { CSSProperties } from "react";

export function Logo() {
  const navigate = useNavigate();
  const [deg, setDeg] = useState(0);

  // base tracks completed full revolutions so rotate() always increases
  const baseRef = useRef(0);
  // phase: idle → to-half → held → to-full → idle
  const phaseRef = useRef<"idle" | "to-half" | "held" | "to-full">("idle");
  const hoveredRef = useRef(false);

  function onEnter() {
    hoveredRef.current = true;
    if (phaseRef.current === "idle") {
      phaseRef.current = "to-half";
      setDeg(baseRef.current + 180);
    }
  }

  function onLeave() {
    hoveredRef.current = false;
    if (phaseRef.current === "held" || phaseRef.current === "to-half") {
      // Always spin forward to the next full revolution
      phaseRef.current = "to-full";
      setDeg(baseRef.current + 360);
    }
  }

  function onTransitionEnd() {
    if (phaseRef.current === "to-half") {
      // Reached 180° — hold here until mouse leaves
      phaseRef.current = "held";
    } else if (phaseRef.current === "to-full") {
      // Completed the full revolution
      baseRef.current += 360;
      phaseRef.current = "idle";
      // If mouse re-entered before the exit finished, start again
      if (hoveredRef.current) {
        phaseRef.current = "to-half";
        setDeg(baseRef.current + 180);
      }
    }
  }

  const markStyle: CSSProperties = {
    transformOrigin: "60px 70px",
    transform: `rotate(${deg}deg)`,
    transition: "transform 0.45s cubic-bezier(0.4, 0, 0.2, 1)",
  };

  return (
    <svg
      viewBox="0 0 400 48"
      height="90"
      role="img"
      aria-label="Intelcrier — A Civic Intelligence Company"
      className="intelcrier-logo"
    >
      {/* Clickable + hover zone: globe + wordmark only */}
      <g
        onClick={() => navigate("/")}
        onMouseEnter={onEnter}
        onMouseLeave={onLeave}
        style={{ cursor: "pointer" }}
      >
        {/* Invisible hit-area rect so the transparent interior of the globe doesn't break hover */}
        <rect x="6" y="0" width="145" height="40" fill="transparent" style={{ pointerEvents: "all" }} />
        <g transform="translate(14.3 7) scale(0.275) translate(-26 -6)">
          <g className="logo-mark" style={markStyle} onTransitionEnd={onTransitionEnd}>
            <circle cx="60" cy="70" r="34" fill="none" className="logo-globe" strokeWidth="3.6" />
            <ellipse cx="60" cy="70" rx="12" ry="34" fill="none" className="logo-globe" strokeWidth="2.7" />
            <path d="M53.11 30.21 A9 9 0 0 1 66.89 30.21" fill="none" className="logo-globe" strokeWidth="3.6" strokeLinecap="round" />
            <path d="M47.74 25.71 A16 16 0 0 1 72.26 25.71" fill="none" className="logo-globe" strokeWidth="3.6" strokeLinecap="round" opacity="0.6" />
            <path d="M42.38 21.21 A23 23 0 0 1 77.62 21.21" fill="none" className="logo-globe" strokeWidth="3.6" strokeLinecap="round" opacity="0.38" />
            <circle cx="60" cy="36" r="6.9" className="logo-globe-dot" />
          </g>
        </g>
        <text x="38" y="33" className="logo-wordmark" fontSize="24" fontFamily="Georgia, 'Times New Roman', serif">
          Intelcrier
        </text>
      </g>
      {/* Tagline — not clickable */}
      <text x="148" y="31" className="logo-tagline" fontSize="9.5" fontFamily="monospace" letterSpacing="1.4">
        A CIVIC INTELLIGENCE COMPANY
      </text>
    </svg>
  );
}
