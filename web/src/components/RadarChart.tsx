import { ATTR_CN } from "../copy";

type Props = {
  values: Record<string, number>;
};

const ATTRS = ["stamina", "skill", "mind", "academics", "social", "finance"];

function point(radius: number, angle: number, cx: number, cy: number): [number, number] {
  return [cx + radius * Math.cos(angle), cy + radius * Math.sin(angle)];
}

export function RadarChart({ values }: Props) {
  const size = 280;
  const cx = size / 2;
  const cy = size / 2;
  const maxR = 105;

  const rings = [20, 40, 60, 80, 100].map((pct) => {
    const r = (pct / 100) * maxR;
    const pts = ATTRS.map((_, idx) => {
      const angle = -Math.PI / 2 + (idx * Math.PI * 2) / ATTRS.length;
      const [x, y] = point(r, angle, cx, cy);
      return `${x},${y}`;
    }).join(" ");
    return <polygon key={pct} points={pts} fill="none" stroke="rgba(80,57,34,0.18)" strokeWidth="1" />;
  });

  const statPts = ATTRS.map((attr, idx) => {
    const angle = -Math.PI / 2 + (idx * Math.PI * 2) / ATTRS.length;
    const r = ((values[attr] ?? 0) / 100) * maxR;
    const [x, y] = point(r, angle, cx, cy);
    return `${x},${y}`;
  }).join(" ");

  return (
    <svg viewBox={`0 0 ${size} ${size}`} className="mx-auto w-full max-w-[320px]">
      {rings}
      {ATTRS.map((attr, idx) => {
        const angle = -Math.PI / 2 + (idx * Math.PI * 2) / ATTRS.length;
        const [x, y] = point(maxR, angle, cx, cy);
        const [lx, ly] = point(maxR + 18, angle, cx, cy);
        return (
          <g key={attr}>
            <line x1={cx} y1={cy} x2={x} y2={y} stroke="rgba(80,57,34,0.2)" />
            <text x={lx} y={ly} textAnchor="middle" dominantBaseline="middle" className="fill-ink-700 text-[11px]">
              {ATTR_CN[attr]}
            </text>
          </g>
        );
      })}
      <polygon points={statPts} fill="rgba(199,111,45,0.30)" stroke="#c76f2d" strokeWidth="2" />
      {ATTRS.map((attr, idx) => {
        const angle = -Math.PI / 2 + (idx * Math.PI * 2) / ATTRS.length;
        const r = ((values[attr] ?? 0) / 100) * maxR;
        const [x, y] = point(r, angle, cx, cy);
        return <circle key={attr} cx={x} cy={y} r={3} fill="#6d3514" />;
      })}
    </svg>
  );
}
