"use client";
import { useEffect, useState } from "react";
import { api, Config, Health } from "@/lib/api";

const FIELDS: { key: keyof Config; label: string; hint: string; step: number }[] = [
  { key: "w_axes", label: "w_axes", hint: "weight of the semantic-differential distance in d_total", step: 0.05 },
  { key: "w_embed", label: "w_embed", hint: "weight of the text-embedding distance (only when both texts exist)", step: 0.05 },
  { key: "radius", label: "radius r", hint: "d_total threshold for “got through”", step: 0.01 },
  { key: "v_lo", label: "V_lo", hint: "raw-variance threshold below which a version is legible", step: 0.01 },
  { key: "alpha", label: "ridge alpha", hint: "regularisation of the grammar regression", step: 0.1 },
];

export default function DevPage() {
  const [cfg, setCfg] = useState<Config | null>(null);
  const [health, setHealth] = useState<Health | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  useEffect(() => {
    api.getConfig().then(setCfg).catch((e) => setMsg(String(e)));
    api.health().then(setHealth).catch(() => {});
  }, []);
  async function save() {
    if (!cfg) return;
    try {
      const c = await api.setConfig(cfg);
      setCfg(c);
      setMsg("saved");
    } catch (e) {
      setMsg(e instanceof Error ? e.message : String(e));
    }
  }
  return (
    <section className="pt-6 flex flex-col gap-5 max-w-md">
      <header>
        <div className="text-xs uppercase tracking-widest text-muted">dev panel</div>
        <h1 className="font-display text-2xl mt-1">Hyperparameters</h1>
        <p className="text-xs text-muted mt-1">Exposed, not tuned live (spec §6.2).</p>
      </header>
      {health && (
        <div className="text-xs text-muted border border-rule p-3 font-mono">
          store {health.store} · embed {health.embed_backend} · naming {health.naming_backend} · libraries {health.n_libraries ?? "–"} · elements{" "}
          {health.n_elements ?? "–"} · decks {health.n_decks ?? "–"} · cards {health.n_cards ?? "–"} · readings {health.n_readings} ({health.n_real} real,{" "}
          {health.n_synthetic} synthetic)
        </div>
      )}
      {cfg && (
        <div className="flex flex-col gap-3">
          {FIELDS.map((f) => (
            <label key={f.key} className="flex items-center gap-3 text-sm">
              <span className="w-24 font-mono">{f.label}</span>
              <input type="number" step={f.step} value={cfg[f.key]} onChange={(e) => setCfg({ ...cfg, [f.key]: parseFloat(e.target.value) })} className="w-24 border border-rule px-2 py-1" />
              <span className="text-xs text-muted">{f.hint}</span>
            </label>
          ))}
          <button onClick={save} className="bg-ink text-paper py-2 mt-2">
            Save
          </button>
        </div>
      )}
      {msg && <p className="text-xs text-muted">{msg}</p>}
    </section>
  );
}
