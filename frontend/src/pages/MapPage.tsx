import { useEffect, useRef, useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { MapContainer, TileLayer, GeoJSON } from "react-leaflet";
import type { Layer, Path, GeoJSON as LeafletGeoJSON } from "leaflet";
import type { Feature, GeoJsonObject } from "geojson";

// Map of GeoJSON lga_name_2021 value → internal council key.
const LGA_TO_KEY: Record<string, string> = {
  "Cambridge": "cambridge",
};

interface ScoreSummary {
  supportive: number;
  critical: number;
  neutral: number;
  not_computable: number;
}

interface ScoreInfo {
  key: string;
  label: string;
  color: string;
  score: number;
  summary: ScoreSummary;
}

// Score → fill colour.  Amber for Cambridge's current 6 supportive / 5 critical.
function scoreColor(supportive: number, critical: number): string {
  const total = supportive + critical;
  if (total === 0) return "#94a3b8";
  const s = supportive / total;
  if (s >= 0.6) return "#22c55e";
  if (s >= 0.4) return "#f59e0b";
  return "#f87171";
}

function scoreLabel(supportive: number, critical: number): string {
  const total = supportive + critical;
  if (total === 0) return "No data";
  const s = supportive / total;
  if (s >= 0.6) return "Broadly clean";
  if (s >= 0.4) return "Mixed record";
  return "Governance concerns";
}

function lgaName(props: Record<string, unknown>): string {
  // ABS ASGS 2021 REST API returns lowercase field names.
  return (
    (props["lga_name_2021"] as string) ||
    (props["lga_name_2016"] as string) ||
    (props["LGA_NAME_2021"] as string) ||
    (props["LGA_NAME"] as string) ||
    (props["name"] as string) ||
    (props["NAME"] as string) ||
    ""
  );
}

const WA_CENTER: [number, number] = [-26.5, 121.8];
const WA_ZOOM = 5;

// Instructions shown when the GeoJSON file hasn't been downloaded yet.
function MapSetupOverlay() {
  return (
    <div className="map-setup-overlay">
      <div className="map-setup-card">
        <div className="map-setup-icon">🗺</div>
        <h2 className="map-setup-title">Map data not loaded</h2>
        <p className="map-setup-body">
          The WA council boundary file hasn't been added yet. Run the download
          script to enable the region map:
        </p>
        <pre className="map-setup-cmd">bash scripts/download_wa_lga.sh</pre>
        <p className="map-setup-body" style={{ marginTop: 12 }}>
          Once downloaded, restart the dev server or rebuild to see all{" "}
          137 Western Australian council regions colour-coded by their
          governance scorecard.
        </p>
      </div>
    </div>
  );
}

function MapLegend({ councils }: { councils: number }) {
  return (
    <div className="map-legend">
      <div className="map-legend-title">Governance score</div>
      <div className="map-legend-row">
        <span className="map-legend-dot" style={{ background: "#22c55e" }} />
        <span>Broadly clean</span>
      </div>
      <div className="map-legend-row">
        <span className="map-legend-dot" style={{ background: "#f59e0b" }} />
        <span>Mixed record</span>
      </div>
      <div className="map-legend-row">
        <span className="map-legend-dot" style={{ background: "#f87171" }} />
        <span>Governance concerns</span>
      </div>
      <div className="map-legend-row">
        <span className="map-legend-dot" style={{ background: "#cbd5e1" }} />
        <span>Not yet analysed</span>
      </div>
      <div className="map-legend-count">
        <strong>{councils}</strong> of 137 WA councils analysed
      </div>
    </div>
  );
}

function HoverCard({
  name,
  info,
}: {
  name: string;
  info: ScoreInfo | null;
}) {
  return (
    <div className="map-hover-card">
      <div className="map-hover-name">{name}</div>
      {info ? (
        <>
          <div
            className="map-hover-score"
            style={{ color: info.color }}
          >
            {scoreLabel(info.summary.supportive, info.summary.critical)}
          </div>
          <div className="map-hover-counts">
            <span style={{ color: "#22c55e" }}>
              {info.summary.supportive} clean
            </span>
            {" · "}
            <span style={{ color: "#f87171" }}>
              {info.summary.critical} concern
            </span>
            {" · "}
            <span style={{ color: "#64748b" }}>
              {info.summary.neutral} neutral
            </span>
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
  const [geoData, setGeoData] = useState<GeoJsonObject | null>(null);
  const [geoError, setGeoError] = useState(false);
  const [scores, setScores] = useState<Record<string, ScoreInfo>>({});
  const [hovered, setHovered] = useState<{ name: string; info: ScoreInfo | null } | null>(null);
  const geoLayerRef = useRef<LeafletGeoJSON | null>(null);
  const navigateRef = useRef(navigate);
  useEffect(() => { navigateRef.current = navigate; }, [navigate]);

  // Load scorecard for the active councils.
  useEffect(() => {
    fetch("/data/scorecard.json")
      .then(r => r.json())
      .then((d) => {
        const s: ScoreSummary = d.summary;
        const color = scoreColor(s.supportive, s.critical);
        setScores({
          cambridge: {
            key: "cambridge",
            label: "Town of Cambridge",
            color,
            score: s.supportive / (s.supportive + s.critical || 1),
            summary: s,
          },
        });
      })
      .catch(() => {});
  }, []);

  // Load WA LGA GeoJSON.
  useEffect(() => {
    fetch("/data/wa_lga.geojson")
      .then(r => {
        if (!r.ok) throw new Error("not found");
        return r.json();
      })
      .then(setGeoData)
      .catch(() => setGeoError(true));
  }, []);

  const styleFeature = useCallback(
    (feature?: Feature) => {
      const name = lgaName((feature?.properties || {}) as Record<string, unknown>);
      const key = LGA_TO_KEY[name];
      const info = key ? scores[key] : null;
      return {
        fillColor: info ? info.color : "#cbd5e1",
        fillOpacity: info ? 0.65 : 0.35,
        color: "#475569",
        weight: 0.8,
        cursor: info ? "pointer" : "default",
      };
    },
    [scores],
  );

  const onEachFeature = useCallback(
    (feature: Feature, layer: Layer) => {
      const name = lgaName((feature.properties || {}) as Record<string, unknown>);
      const key = LGA_TO_KEY[name];
      const path = layer as Path;

      layer.on({
        mouseover: () => {
          const info = key ? scores[key] : null;
          path.setStyle({ fillOpacity: info ? 0.85 : 0.5, weight: 1.5 });
          setHovered({ name, info: info ?? null });
        },
        mouseout: () => {
          geoLayerRef.current?.resetStyle(path);
          setHovered(null);
        },
        click: () => {
          if (key) navigateRef.current("/");
        },
      });
    },
    [scores],
  );

  const activeCount = Object.keys(LGA_TO_KEY).filter(n => LGA_TO_KEY[n] in scores).length;

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
        {geoData && (
          <GeoJSON
            key={JSON.stringify(Object.keys(scores))}
            ref={geoLayerRef}
            data={geoData}
            style={styleFeature}
            onEachFeature={onEachFeature}
          />
        )}
      </MapContainer>

      {geoError && <MapSetupOverlay />}

      {!geoError && (
        <>
          <MapLegend councils={activeCount} />
          {hovered && (
            <HoverCard name={hovered.name} info={hovered.info} />
          )}
        </>
      )}
    </div>
  );
}
