import { useId } from "react";

function curve(turn: number, phase: number) {
  const points: string[] = [];
  for (let degree = 0; degree <= 720; degree += 4) {
    const t = (degree * Math.PI) / 180;
    const r = 94 + 22 * Math.cos(turn * t + phase);
    const x = 160 + r * Math.cos(t);
    const y = 105 + .54 * r * Math.sin(t);
    points.push(`${degree ? "L" : "M"}${x.toFixed(2)},${y.toFixed(2)}`);
  }
  return points.join(" ");
}

export function Guilloche({ className = "" }: { className?: string }) {
  const id = useId().replaceAll(":", "");
  return (
    <svg className={className} viewBox="0 0 320 210" aria-hidden="true">
      <defs>
        <clipPath id={id}><rect width="320" height="210" /></clipPath>
      </defs>
      <g clipPath={`url(#${id})`} fill="none" stroke="var(--guilloche)" strokeWidth=".55">
        {Array.from({ length: 14 }, (_, index) => (
          <path key={index} d={curve(5 + (index % 3), index * .31)} opacity={.34 + index * .025} />
        ))}
        <ellipse cx="160" cy="105" rx="148" ry="72" opacity=".7" />
        <ellipse cx="160" cy="105" rx="139" ry="66" opacity=".5" />
      </g>
    </svg>
  );
}
