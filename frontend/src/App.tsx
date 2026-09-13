import { useEffect, useState } from "react";
import type { Meta, ProductCard, ProductDetail } from "./types";
import { ProductGrid } from "./components/ProductGrid";
import { DetailPanel } from "./components/DetailPanel";
import { PersonaSwitch } from "./components/PersonaSwitch";
import "./App.css";

const API = "http://localhost:8000";

export default function App() {
  const [cards, setCards] = useState<ProductCard[]>([]);
  const [meta, setMeta] = useState<Meta | null>(null);
  const [persona, setPersona] = useState("consumer");
  const [selected, setSelected] = useState<ProductDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([
      fetch(`${API}/api/products`).then((r) => r.json()),
      fetch(`${API}/api/meta`).then((r) => r.json()),
    ])
      .then(([products, metadata]) => {
        setCards(products.products);
        setMeta(metadata);
      })
      .catch(() =>
        setError(
          "Could not reach the API. Start it with: uv run --directory backend uvicorn app.main:app",
        ),
      );
  }, []);

  const open = (id: string) =>
    fetch(`${API}/api/products/${id}`)
      .then((r) => r.json())
      .then(setSelected);

  if (error) return <div className="error">{error}</div>;
  if (!meta) return <div className="loading">Loading…</div>;

  const counts = cards.reduce(
    (acc, card) => {
      const status = card.verdicts[persona]?.status ?? "no_restriction";
      acc[status] = (acc[status] ?? 0) + 1;
      return acc;
    },
    {} as Record<string, number>,
  );

  const activePersona = meta.personas.find((p) => p.key === persona);

  // Calls the pipeline made in its last stage vs what Sayari actually metered on
  // the account. The former is near zero when only the tail was re-run, which
  // reads as "this used no API" -- misleading for a deliverable whose whole point
  // is the API usage.
  const measured = Object.values(meta.api.usage_last_30d ?? {}).reduce(
    (a: number, b) => a + (Number(b) || 0),
    0,
  );

  return (
    <div className="app">
      <header>
        <h1>Who's allowed to buy this?</h1>
        <p className="thesis">
          Twenty-five consumer smart devices, screened against US restriction
          regimes. <strong>“Legal” is not a property of the product — it is a
          property of the buyer.</strong> Change who is asking and the same shelf
          re-tiers.
        </p>
      </header>

      <PersonaSwitch
        personas={meta.personas}
        active={persona}
        onChange={setPersona}
      />

      <div className="summary">
        <span className="blurb">{activePersona?.blurb}</span>
        <span className="tally">
          <b>{counts.prohibited ?? 0}</b> prohibited ·{" "}
          <b>{counts.review ?? 0}</b> diligence required ·{" "}
          <b>{counts.no_restriction ?? 0}</b> no restriction identified
        </span>
      </div>

      <ProductGrid cards={cards} persona={persona} onSelect={open} />

      <footer>
        <details>
          <summary>What this data cannot see ({meta.caveats.length})</summary>
          <ul>
            {meta.caveats.map((caveat) => (
              <li key={caveat}>{caveat}</li>
            ))}
          </ul>
        </details>
        <details>
          <summary>Restriction regimes and who they bind</summary>
          <ul>
            {meta.regimes.map((regime) => (
              <li key={regime.key}>
                <b>{regime.authority}</b> — binds {regime.binds}.{" "}
                <span className="cite">{regime.citation}</span>
                <div className="scope">{regime.scope}</div>
              </li>
            ))}
          </ul>
        </details>
        <p className="provenance">
          Snapshot {new Date(meta.generated_at).toLocaleString()} · source{" "}
          {meta.source} · {meta.api.total_calls} Sayari API calls in the final
          stage
          {measured > 0 && (
            <>
              {" "}
              · {measured.toLocaleString()} measured against the account over 30
              days (
              {Object.entries(meta.api.usage_last_30d ?? {})
                .map(([k, v]) => `${k} ${v}`)
                .join(", ")}
              )
            </>
          )}
        </p>
      </footer>

      {selected && (
        <DetailPanel
          detail={selected}
          persona={persona}
          personas={meta.personas}
          onClose={() => setSelected(null)}
        />
      )}
    </div>
  );
}
