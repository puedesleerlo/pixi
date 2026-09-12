// The eight bipolar scales (Osgood semantic differential), contract §1.
// Negative values = first pole, positive = second pole. Values −3..+3.
export const AXES: [string, string][] = [
  ["active", "passive"],
  ["beginning", "ending"],
  ["giving", "withholding"],
  ["inward", "outward"],
  ["gain", "loss"],
  ["willing", "compelled"],
  ["certain", "uncertain"],
  ["singular", "collective"],
];

export const N_AXES = 8;
export const AXIS_MAX = 3;

/** Render an axis vector as words, e.g. "ending · passive · giving". */
export function axesToWords(vec: number[], k = 3): string {
  const idx = vec
    .map((v, i) => ({ i, v }))
    .filter((x) => Math.abs(x.v) > 0)
    .sort((a, b) => Math.abs(b.v) - Math.abs(a.v))
    .slice(0, k);
  if (idx.length === 0) return "neutral";
  return idx.map(({ i, v }) => (v < 0 ? AXES[i][0] : AXES[i][1])).join(" · ");
}

/** Word for one axis value (sign chooses the pole). */
export function poleWord(i: number, v: number): string {
  return v < 0 ? AXES[i][0] : AXES[i][1];
}
