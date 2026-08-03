import { clsx } from "clsx";

export function SlaStrip({ urgency = "Medium", elapsed = 7 }: { urgency?: string | null; elapsed?: number }) {
  const days = urgency === "High" ? 5 : 20;
  const risk = elapsed / days >= .8;
  const cells = Array.from({ length: days + Math.floor(days / 5) * 2 }, (_, index) => {
    const weekPosition = index % 7;
    const weekend = weekPosition === 5 || weekPosition === 6;
    const workingIndex = index - Math.floor(index / 7) * 2;
    return { weekend, elapsed: !weekend && workingIndex < elapsed };
  });
  return (
    <div className="sla-strip" aria-label={`${elapsed} of ${days} working days elapsed`}>
      {cells.map((cell, index) => (
        <span key={index} className={clsx("sla-day", cell.weekend && "weekend", cell.elapsed && "elapsed", risk && "risk")} />
      ))}
    </div>
  );
}
