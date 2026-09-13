import { useEffect, useState } from "react";
import { ChevronDown, Loader2 } from "lucide-react";
import type { Meta, ProductCard, ProductDetail } from "./types";
import { ProductGrid } from "./components/ProductGrid";
import { DetailPanel } from "./components/DetailPanel";
import { PersonaPicker } from "./components/PersonaPicker";
import { ImpactBar } from "./components/ImpactBar";
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

  useEffect(() => {
    const esc = (e: KeyboardEvent) => e.key === "Escape" && setSelected(null);
    window.addEventListener("keydown", esc);
    return () => window.removeEventListener("keydown", esc);
  }, []);

  if (error)
    return <div className="mx-auto max-w-lg p-12 text-sm text-check">{error}</div>;

  if (!meta)
    return (
      <div className="flex h-screen items-center justify-center gap-2 text-sm text-faint">
        <Loader2 size={16} className="animate-spin" /> Loading screening data…
      </div>
    );

  const cost = meta.api.snapshot_cost;
  const accountTotal = Object.values(meta.api.account_usage_last_30d ?? {}).reduce(
    (a: number, b) => a + (Number(b) || 0),
    0,
  );

  return (
    <div className="mx-auto max-w-6xl px-6 pb-24 pt-12">
      <header className="mb-10 max-w-3xl">
        <p className="mb-2 text-xs font-medium uppercase tracking-[0.18em] text-faint">
          Sayari · supply chain screening
        </p>
        <h1 className="text-4xl font-semibold leading-tight tracking-tight text-fg">
          Who's allowed to buy this?
        </h1>
        <p className="mt-3 text-[15px] leading-relaxed text-muted">
          Twenty-five ordinary smart-home devices, screened against US restriction
          regimes.{" "}
          <span className="text-fg">
            &ldquo;Legal&rdquo; is not a property of the product — it is a property
            of the buyer.
          </span>{" "}
          TP-Link is the best-selling router brand in America and sits on a
          Department of Defense prohibition list. Both are true. Nothing on the box
          tells you which situation you are in.
        </p>
      </header>

      <PersonaPicker
        personas={meta.personas}
        cards={cards}
        active={persona}
        onChange={setPersona}
      />

      <ImpactBar cards={cards} persona={persona} personas={meta.personas} />

      <ProductGrid cards={cards} persona={persona} onSelect={open} />

      <footer className="mt-14 space-y-2 border-t border-line pt-6 text-xs text-faint">
        <Disclosure title={`What this data cannot see (${meta.caveats.length})`}>
          <ul className="mt-2 space-y-1.5 pl-4">
            {meta.caveats.map((c) => (
              <li key={c} className="list-disc leading-relaxed">{c}</li>
            ))}
          </ul>
        </Disclosure>

        <Disclosure title="Restriction regimes and who they bind">
          <ul className="mt-2 space-y-3 pl-4">
            {meta.regimes.map((r) => (
              <li key={r.key} className="list-disc leading-relaxed">
                <span className="text-muted">{r.authority}</span> — binds {r.binds}.{" "}
                <span className="text-faint/80">{r.citation}</span>
                <div className="mt-0.5 text-faint/80">{r.scope}</div>
              </li>
            ))}
          </ul>
        </Disclosure>

        <Disclosure
          title={`API cost — ${cost.total.toLocaleString()} Sayari calls built this snapshot`}
        >
          <ul className="mt-2 space-y-1.5 pl-4">
            {Object.entries(cost.by_stage).map(([stage, n]) => (
              <li key={stage} className="list-disc">
                {stage} — {n.toLocaleString()} calls
              </li>
            ))}
            {accountTotal > 0 && (
              <li className="list-disc leading-relaxed">
                Separately, {accountTotal.toLocaleString()} calls were metered
                against the account over 30 days. That includes exploratory work
                during development and is <b>not</b> what this app costs to run.
              </li>
            )}
          </ul>
        </Disclosure>

        <p className="pt-2 text-faint/70">
          Snapshot {new Date(meta.generated_at).toLocaleString()} · source{" "}
          {meta.source} · {meta.product_count} products
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

function Disclosure({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <details className="group">
      <summary className="flex cursor-pointer list-none items-center gap-1.5 py-1 hover:text-muted">
        <ChevronDown size={12} className="transition-transform group-open:rotate-180" />
        {title}
      </summary>
      {children}
    </details>
  );
}
