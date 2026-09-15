import { useEffect, useRef, useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { MapContainer, TileLayer, GeoJSON } from "react-leaflet";
import type { Layer, Path, GeoJSON as LeafletGeoJSON } from "leaflet";
import type { Feature, GeoJsonObject } from "geojson";
import { useCouncilList, CouncilListEntry } from "../councils";
import { getMode } from "../devMode";
import { RatingData, RatingBandId } from "../api";

// Governance rating band → the same CSS custom properties RatingBand.tsx's
// stylesheet already defines (index.css's --rating-*-t tokens), so a
// council's map colour always matches its own rating band elsewhere on the
// site — never a second, independently-tuned colour scale.
const BAND_COLOR: Record<RatingBandId, string> = {
  green: "var(--rating-green-t)",
  yellow: "var(--rating-yellow-t)",
  red: "var(--rating-red-t)",
  insufficient: "var(--rating-insufficient-t)",
};
const NO_DATA_COLOR = "#cbd5e1";

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

const WA_CENTER: [number, number] = [-26.5, 121.8];
const WA_ZOOM = 5;

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
        <span className="map-legend-dot" style={{ background: BAND_COLOR.green }} />
        <span>Green</span>
      </div>
      <div className="map-legend-row">
        <span className="map-legend-dot" style={{ background: BAND_COLOR.yellow }} />
        <span>Yellow</span>
      </div>
      <div className="map-legend-row">
        <span className="map-legend-dot" style={{ background: BAND_COLOR.red }} />
        <span>Red</span>
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

function HoverCard({ name, info }: { name: string; info: CouncilMapInfo | null }) {
  return (
    <div className="map-hover-card">
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
          color: rating ? BAND_COLOR[rating.band] : NO_DATA_COLOR,
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
        mouseover: () => {
          const info = key ? infoByKey[key] : null;
          path.setStyle({ fillOpacity: info ? 0.85 : 0.5, weight: 1.5 });
          setHovered({ name, info: info ?? null });
        },
        mouseout: () => {
          geoLayerRef.current?.resetStyle(path);
          setHovered(null);
        },
        click: () => {
          if (key) navigateRef.current(`/c/${key}`);
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
        style={{ height: "100%", width: "100%" }}
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
      </MapContainer>

      {backdropError && <MapSetupOverlay />}

      {!backdropError && backdrop && "features" in backdrop && (
        <>
          <MapLegend analysed={list.length} total={(backdrop as GeoJSON.FeatureCollection).features.length} />
          {hovered && <HoverCard name={hovered.name} info={hovered.info} />}
        </>
      )}
    </div>
  );
}
