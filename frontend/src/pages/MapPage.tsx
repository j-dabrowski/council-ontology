import { useEffect, useRef, useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { MapContainer, TileLayer, GeoJSON, useMap } from "react-leaflet";
import type { Layer, Path, GeoJSON as LeafletGeoJSON } from "leaflet";
import type { Feature, GeoJsonObject } from "geojson";
import { useCouncilList, CouncilListEntry } from "../councils";
import { getMode } from "../devMode";
import { RatingData, RatingBandId } from "../api";
import ratingConfig from "@rating-config";

// Governance rating band → the same CSS custom properties RatingBand.tsx's
// stylesheet already defines (index.css's --rating-*-t tokens), so a
// council's map colour always matches its own rating band elsewhere on the
// site — never a second, independently-tuned colour scale. Text only
// (the hover card's score label and supportive/critical counts): these
// tokens are tuned per-theme for contrast against a page background, which
// is correct for prose but not for a fill.
const BAND_COLOR: Record<RatingBandId, string> = {
  green: "var(--rating-green-t)",
  yellow: "var(--rating-yellow-t)",
  red: "var(--rating-red-t)",
  insufficient: "var(--rating-insufficient-t)",
};
// Fills only (the polygon itself, the legend dot, the council-list dot) —
// the --rating-*-swatch tokens, fixed in both themes on purpose (a map
// region shouldn't visibly darken just because the reader's OS is in light
// mode).
const BAND_FILL_COLOR: Record<RatingBandId, string> = {
  green: "var(--rating-green-swatch)",
  yellow: "var(--rating-yellow-swatch)",
  red: "var(--rating-red-swatch)",
  insufficient: "var(--rating-insufficient-swatch)",
};
const NO_DATA_COLOR = "#cbd5e1";

// The legend's band names come from config/rating.json — the same "Broadly
// clean"/"Mixed record"/"Governance concerns"/"Insufficient record" wording
// RatingBand.tsx and the hover card already show, via the @rating-config
// alias (same pattern as @registry for test_registry.json). Never a raw
// colour name ("Green"/"Yellow"/"Red") or a second, independently-worded
// label typed here — one band, one name, everywhere it appears.
interface RatingConfigShape {
  bands: { id: string; label: string }[];
  coverage_gate: { band_id: string; label: string };
}
const RATING_CONFIG = ratingConfig as unknown as RatingConfigShape;
const BAND_LABEL: Record<RatingBandId, string> = {
  ...(Object.fromEntries(RATING_CONFIG.bands.map((b) => [b.id, b.label])) as Record<RatingBandId, string>),
  [RATING_CONFIG.coverage_gate.band_id as RatingBandId]: RATING_CONFIG.coverage_gate.label,
};

interface CouncilMapInfo {
  key: string;
  displayName: string;
  color: string;
  rating: RatingData | null;
}

function lgaName(props: Record<string, unknown>): string {
  // ABS ASGS 2021 REST API returns lowercase field names.
  return (
    (props["lga_name_2021"] as string) ||
    (props["lga_name_2016"] as string) ||
    (props["LGA_NAME_2021"] as string) ||
    (props["LGA_NAME"] as string) ||
    (props["lga_name"] as string) ||
    (props["name"] as string) ||
    (props["NAME"] as string) ||
    ""
  );
}

function isCoarsePointer(): boolean {
  return typeof window !== "undefined" && !!window.matchMedia?.("(pointer: coarse)").matches;
}

const WA_CENTER: [number, number] = [-26.5, 121.8];
const WA_ZOOM = 5;

// react-leaflet's MapContainer measures its container's size once, via
// Leaflet's own construction-time _onResize — before .map-page's CSS
// height is guaranteed to have actually taken effect (confirmed live: the
// container's own DOM box was correct, but Leaflet's cached internal size
// wasn't, leaving its SVG overlay pane rendered far wider than the visible
// map at a narrow viewport). invalidateSize() forces a fresh read; the
// resize listener covers a real orientation/window-size change too, since
// Leaflet only listens for that on the window it was constructed against.
function InvalidateSizeOnResize() {
  const map = useMap();
  useEffect(() => {
    map.invalidateSize();
    const onResize = () => map.invalidateSize();
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, [map]);
  return null;
}

// Default view (5.5): fit bounds to the union of the council layer's own
// features, not a hardcoded metro box — opens on Perth while there's one
// analysed council, and opens correctly wherever they are once there are
// several, all without this file ever naming a region. WA_CENTER/WA_ZOOM
// stay as the fallback for an empty council list (no bounds to fit).
function FitToCouncilBounds({ geoLayerRef, ready }: {
  geoLayerRef: React.RefObject<LeafletGeoJSON | null>;
  ready: boolean;
}) {
  const map = useMap();
  useEffect(() => {
    if (!ready) return;
    map.invalidateSize();
    const bounds = geoLayerRef.current?.getBounds();
    if (bounds && bounds.isValid()) {
      map.fitBounds(bounds, { padding: [32, 32], maxZoom: 11 });
    }
  }, [ready, map, geoLayerRef]);
  return null;
}

// Shown when the cross-council backdrop hasn't been built yet.
function MapSetupOverlay() {
  return (
    <div className="map-setup-overlay">
      <div className="map-setup-card">
        <div className="map-setup-icon">🗺</div>
        <h2 className="map-setup-title">Map data not loaded</h2>
        <p className="map-setup-body">
          The WA council boundary backdrop hasn't been built yet. Run:
        </p>
        <pre className="map-setup-cmd">council boundary --backdrop</pre>
        <p className="map-setup-body" style={{ marginTop: 12 }}>
          then <code>council publish</code> to ship it, to enable the region
          map colour-coded by each council's governance rating.
        </p>
      </div>
    </div>
  );
}

function MapLegend({ analysed, total }: { analysed: number; total: number }) {
  return (
    <div className="map-legend">
      <div className="map-legend-title">Governance rating</div>
      <div className="map-legend-row">
        <span className="map-legend-dot" style={{ background: BAND_FILL_COLOR.green }} />
        <span>{BAND_LABEL.green}</span>
      </div>
      <div className="map-legend-row">
        <span className="map-legend-dot" style={{ background: BAND_FILL_COLOR.yellow }} />
        <span>{BAND_LABEL.yellow}</span>
      </div>
      <div className="map-legend-row">
        <span className="map-legend-dot" style={{ background: BAND_FILL_COLOR.red }} />
        <span>{BAND_LABEL.red}</span>
      </div>
      <div className="map-legend-row">
        <span className="map-legend-dot" style={{ background: BAND_FILL_COLOR.insufficient }} />
        <span>{BAND_LABEL.insufficient}</span>
      </div>
      <div className="map-legend-row">
        <span className="map-legend-dot" style={{ background: NO_DATA_COLOR }} />
        <span>Not yet analysed</span>
      </div>
      <div className="map-legend-count">
        <strong>{analysed}</strong> of {total} WA councils analysed
      </div>
    </div>
  );
}

// Clamps the card to the viewport so it can't render off-screen near an
// edge — a fixed assumed card size (it varies slightly with content, but
// not enough to matter for this).
function clampToViewport(x: number, y: number): { left: number; top: number } {
  const offset = 16;
  const cardWidth = 280;
  const cardHeight = 150;
  const maxLeft = (typeof window !== "undefined" ? window.innerWidth : 1280) - cardWidth - offset;
  const maxTop = (typeof window !== "undefined" ? window.innerHeight : 800) - cardHeight - offset;
  return {
    left: Math.max(offset, Math.min(x + offset, maxLeft)),
    top: Math.max(offset, Math.min(y + offset, maxTop)),
  };
}

// Follows the cursor (or the tap point, on touch) rather than sitting in a
// fixed corner — `pointer-events: none` (index.css) is what lets mouse/tap
// events pass through it to the polygon underneath even while it's
// positioned right where the pointer is. No link inside it: the card
// itself can't be clicked (pointer-events: none), so a real <a> here would
// be dead weight at best and confusing at worst — "Click to view full
// analysis" is plain text, describing what clicking the *polygon* does.
function HoverCard({ name, info, pos }: {
  name: string;
  info: CouncilMapInfo | null;
  pos: { x: number; y: number };
}) {
  const { left, top } = clampToViewport(pos.x, pos.y);
  return (
    <div className="map-hover-card" style={{ left, top }}>
      <div className="map-hover-name">{info?.displayName ?? name}</div>
      {info?.rating ? (
        <>
          <div
            className="map-hover-score"
            style={{ color: BAND_COLOR[info.rating.band] }}
          >
            {info.rating.band_label}
          </div>
          <div className="map-hover-counts">
            <span style={{ color: BAND_COLOR.green }}>{info.rating.n_supportive} supportive</span>
            {" · "}
            <span style={{ color: BAND_COLOR.red }}>{info.rating.n_critical} critical</span>
            {" · "}
            <span style={{ color: "#64748b" }}>{info.rating.n_neutral} neutral</span>
          </div>
          <div className="map-hover-cta">Click to view full analysis →</div>
        </>
      ) : (
        <div className="map-hover-nodata">Analysis coming soon</div>
      )}
    </div>
  );
}

export function MapPage() {
  const navigate = useNavigate();
  const { list } = useCouncilList();
  const [backdrop, setBackdrop] = useState<GeoJsonObject | null>(null);
  const [backdropError, setBackdropError] = useState(false);
  const [councilFeatures, setCouncilFeatures] = useState<GeoJsonObject | null>(null);
  const [infoByKey, setInfoByKey] = useState<Record<string, CouncilMapInfo>>({});
  const [hovered, setHovered] = useState<{ name: string; info: CouncilMapInfo | null } | null>(null);
  const [mousePos, setMousePos] = useState<{ x: number; y: number } | null>(null);
  const geoLayerRef = useRef<LeafletGeoJSON | null>(null);
  const navigateRef = useRef(navigate);
  useEffect(() => { navigateRef.current = navigate; }, [navigate]);

  // The cross-council boundary layers council publish writes at the top of
  // frontend/public/data/ (never under a per-council subdirectory — these
  // aren't any one council's own data). Both draft- and publish-independent:
  // config-sourced, refreshed by every publish regardless of council.
  useEffect(() => {
    fetch("/data/wa_lga_backdrop.geojson")
      .then((r) => { if (!r.ok) throw new Error("not found"); return r.json(); })
      .then(setBackdrop)
      .catch(() => setBackdropError(true));
    fetch("/data/councils.geojson")
      .then((r) => (r.ok ? r.json() : null))
      .then(setCouncilFeatures)
      .catch(() => {});
  }, []);

  // Each analysed council's own rating.json — one fetch per council in the
  // mode-dependent list (2.5), not the single hardcoded scorecard.json the
  // old single-council map read. Draft-mode paths mirror getSnapshot()'s own
  // council-segmented convention (api.ts) since this needs several councils'
  // snapshots at once, not just the route's active one. A synthetic fixture
  // council (Draft mode only) has no config/council_boundaries/<key>.geojson,
  // so it simply won't match a feature in councilFeatures below — no special
  // case needed, and this fetch for it is harmless either way.
  useEffect(() => {
    const draftMode = getMode() === "draft";
    let cancelled = false;
    Promise.all(
      list.map((c: CouncilListEntry) =>
        fetch(`${draftMode ? "/data/draft" : "/data"}/${c.key}/rating.json`)
          .then((r) => (r.ok ? r.json() : null))
          .then((j) => [c.key, j?.data as RatingData | undefined] as const)
          .catch(() => [c.key, undefined] as const)
      )
    ).then((pairs) => {
      if (cancelled) return;
      const next: Record<string, CouncilMapInfo> = {};
      for (const c of list) {
        const rating = pairs.find(([k]) => k === c.key)?.[1] ?? null;
        next[c.key] = {
          key: c.key,
          displayName: c.display_name,
          color: rating ? BAND_FILL_COLOR[rating.band] : NO_DATA_COLOR,
          rating,
        };
      }
      setInfoByKey(next);
    });
    return () => { cancelled = true; };
  }, [list]);

  const styleFeature = useCallback(
    (feature?: Feature) => {
      const key = feature?.properties?.["council_key"] as string | undefined;
      const info = key ? infoByKey[key] : null;
      return {
        fillColor: info ? info.color : NO_DATA_COLOR,
        fillOpacity: info ? 0.65 : 0.35,
        color: "#475569",
        weight: 0.8,
        cursor: info ? "pointer" : "default",
      };
    },
    [infoByKey],
  );

  const onEachFeature = useCallback(
    (feature: Feature, layer: Layer) => {
      const key = feature.properties?.["council_key"] as string | undefined;
      const name = lgaName((feature.properties || {}) as Record<string, unknown>);
      const path = layer as Path;

      layer.on({
        mouseover: (e) => {
          const info = key ? infoByKey[key] : null;
          path.setStyle({ fillOpacity: info ? 0.85 : 0.5, weight: 1.5 });
          setMousePos({ x: e.originalEvent.clientX, y: e.originalEvent.clientY });
          setHovered({ name, info: info ?? null });
        },
        mousemove: (e) => {
          setMousePos({ x: e.originalEvent.clientX, y: e.originalEvent.clientY });
        },
        mouseout: () => {
          geoLayerRef.current?.resetStyle(path);
          setHovered(null);
        },
        click: (e) => {
          if (!key) return;
          // 5.7: touch has no hover state, so a coarse pointer gets a tap
          // equivalent instead of the desktop hover card — first tap shows
          // the same info a mouseover would, second tap on the same
          // council navigates. A fine pointer (mouse) still navigates on a
          // single click, since hover already previewed it.
          if (isCoarsePointer()) {
            setMousePos({ x: e.originalEvent.clientX, y: e.originalEvent.clientY });
            setHovered((prev) => {
              if (prev?.name === name) {
                navigateRef.current(`/c/${key}`);
                return prev;
              }
              return { name, info: infoByKey[key] ?? null };
            });
            return;
          }
          navigateRef.current(`/c/${key}`);
        },
      });
    },
    [infoByKey],
  );

  return (
    <div className="map-page">
      <MapContainer
        center={WA_CENTER}
        zoom={WA_ZOOM}
        // `height: "100%"` doesn't reliably resolve here — this is a
        // pre-existing bug found while testing 5.5/5.7/5.8, not
        // introduced by them: react-leaflet's MapContainer freezes its
        // `style` prop on first render (useState, no setter — see
        // MapContainer.js), and the resulting .leaflet-container
        // computes to height:0 despite .map-page (position: relative)
        // having a fully resolved, non-percentage height at every
        // ancestor in the chain — confirmed live in headless Chromium.
        // Absolute-filling the already-positioned parent sidesteps
        // percentage-height resolution entirely rather than depending
        // on it, and doesn't need .map-page's own CSS to change.
        style={{ position: "absolute", inset: 0 }}
        zoomControl
      >
        <TileLayer
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          opacity={0.55}
        />
        {backdrop && (
          <GeoJSON data={backdrop} style={{ fillColor: NO_DATA_COLOR, fillOpacity: 0.15, color: "#94a3b8", weight: 0.5 }} />
        )}
        {councilFeatures && (
          <GeoJSON
            key={JSON.stringify(Object.keys(infoByKey))}
            ref={geoLayerRef}
            data={councilFeatures}
            style={styleFeature}
            onEachFeature={onEachFeature}
          />
        )}
        <FitToCouncilBounds geoLayerRef={geoLayerRef} ready={!!councilFeatures} />
        <InvalidateSizeOnResize />
      </MapContainer>

      {backdropError && <MapSetupOverlay />}

      {!backdropError && backdrop && "features" in backdrop && (
        <>
          <MapLegend analysed={list.length} total={(backdrop as GeoJSON.FeatureCollection).features.length} />
          {hovered && mousePos && <HoverCard name={hovered.name} info={hovered.info} pos={mousePos} />}
        </>
      )}
    </div>
  );
}
