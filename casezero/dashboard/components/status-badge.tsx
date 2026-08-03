import { clsx } from "clsx";

export function StatusBadge({ status }: { status?: string | null }) {
  const value = status || "PENDING";
  return <span className={clsx("status-badge", value.toLowerCase().replaceAll("_", "-"), value === "REVIEW_PENDING" && "review")}>{value.replaceAll("_", " ")}</span>;
}
