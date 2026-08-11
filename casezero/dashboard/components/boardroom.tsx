"use client";

import { motion, useReducedMotion } from "framer-motion";
import { clsx } from "clsx";
import { useEffect, useMemo, useState } from "react";

/** One participant in the case, as reported by GET /demo/agents. Never hardcoded:
 *  if a provider key is missing the API discloses the fallback, and the badge
 *  must repeat that disclosure rather than advertise intended diversity. */
export type RosterSeat = {
  id: string;
  name: string;
  kind: "agent" | "kernel";
  role: string;
  replaces: string;
  obligation: string;
  uses_model: boolean;
  provider: string | null;
  model: string | null;
  fallback_from: string | null;
};

export type AgentsRoster = {
  seats: RosterSeat[];
  providers: string[];
  baseline_minutes_total: number;
  analyst_hourly_rm: number;
  stage_baseline_minutes: Record<string, number>;
};

export type HandoffFact = { label: string; value: string };

/** What one agent said to the next, assembled server-side from chained events.
 *  `spoken: false` means the stage has no event yet — the seat stays quiet. */
export type Handoff = {
  stage: string;
  label: string;
  event_type: string;
  from: string;
  to: string;
  spoken: boolean;
  says: string;
  facts: HandoffFact[];
  seq?: number | null;
  hash?: string | null;
  recorded_at?: string | null;
  baseline_minutes: number;
  refused?: boolean;
};

export type RunValue = {
  baseline_minutes_total: number;
  baseline_minutes_realised: number;
  elapsed_seconds: number;
  minutes_saved: number;
  stages_spoken: number;
  stages_total: number;
};

export type BoardroomState = "IDLE" | "RUNNING" | "COMPLETED" | "FAILED";

/** Muted intaglio inks. Used only on a seat's status dot and bubble border —
 *  refusal red stays reserved for the kernel. */
const SEAT_ACCENTS: Record<string, string> = {
  intake: "#2f5d50",
  classifier: "#31506e",
  verifier: "#6b4f2a",
  resolver: "#585c2e",
  communicator: "#5b3a5e",
  supervisor: "#4a5560",
};

/** Clockwise circulation: the chip enters top-left and exits bottom-left. */
const SEAT_AREAS: Record<string, string> = {
  intake: "t1",
  classifier: "t2",
  verifier: "t3",
  resolver: "b3",
  communicator: "b2",
  supervisor: "b1",
};

const FALLBACK_SEAT_NAMES: Record<string, string> = {
  intake: "Intake",
  classifier: "Classifier",
  kernel: "Compliance Kernel",
  verifier: "Verifier",
  resolver: "Resolver",
  communicator: "Communicator",
  supervisor: "Supervisor",
  customer: "Customer",
};

type SeatStatus = "waiting" | "thinking" | "spoke" | "refused" | "silenced" | "watching";

const STATUS_COPY: Record<SeatStatus, string> = {
  waiting: "Waiting",
  thinking: "Working",
  spoke: "Spoke",
  refused: "Refused the case",
  silenced: "Never saw it",
  watching: "Watching deadlines",
};

type KernelVerdict = "AUTHORISED" | "HELD" | "REFUSED";

type KernelMark = {
  stage: string;
  verdict: KernelVerdict;
  gate: string;
  handoff: Handoff;
};

function fact(handoff: Handoff | undefined, label: string): string | null {
  const hit = handoff?.facts.find((entry) => entry.label === label);
  return hit ? hit.value : null;
}

/** The kernel's decisions this run, derived only from recorded handoffs. */
function kernelMarks(handoffs: Handoff[], quarantined: boolean): KernelMark[] {
  const marks: KernelMark[] = [];
  const refusal = handoffs.find((h) => h.refused);
  if (quarantined && refusal) {
    marks.push({ stage: refusal.stage, verdict: "REFUSED", gate: "Injection firewall", handoff: refusal });
  }
  for (const handoff of handoffs) {
    if (!handoff.spoken || handoff.from !== "kernel") continue;
    if (handoff.stage === "sla") {
      marks.push({ stage: "sla", verdict: "AUTHORISED", gate: "BNM working-day window", handoff });
    } else if (handoff.stage === "gate") {
      const ruling = fact(handoff, "Ruling");
      const verdict: KernelVerdict = ruling === "POST" ? "AUTHORISED" : ruling === "DENY" ? "REFUSED" : "HELD";
      marks.push({ stage: "gate", verdict, gate: "Financial gate", handoff });
    }
  }
  return marks;
}

function seatBadge(seat: RosterSeat): { line: string; fallback: string | null } {
  if (!seat.uses_model) return { line: "No model — deterministic", fallback: null };
  if (!seat.provider) return { line: "Model unresolved", fallback: null };
  const line = `${seat.provider} / ${seat.model ?? "model"}`;
  const fallback = seat.fallback_from
    ? `Intended ${seat.fallback_from}; running ${seat.provider} — no ${seat.fallback_from} key on this deployment`
    : null;
  return { line, fallback };
}

function stageDelta(handoffs: Handoff[], index: number, startedAt?: string | null): string {
  const current = handoffs[index];
  if (!current?.spoken || !current.recorded_at) return "";
  const prev = [...handoffs.slice(0, index)].reverse().find((h) => h.spoken && h.recorded_at);
  const from = prev?.recorded_at ?? startedAt;
  if (!from) return "";
  const ms = new Date(current.recorded_at).getTime() - new Date(from).getTime();
  if (!Number.isFinite(ms)) return "";
  return `${(Math.max(ms, 0) / 1000).toFixed(1)}s`;
}

function sinceStart(handoff: Handoff, startedAt?: string | null): string {
  if (!handoff.spoken || !handoff.recorded_at || !startedAt) return "";
  const ms = new Date(handoff.recorded_at).getTime() - new Date(startedAt).getTime();
  if (!Number.isFinite(ms)) return "";
  return `+${(Math.max(ms, 0) / 1000).toFixed(1)}s`;
}

/** Elliptical guilloché — the table surface itself, drawn like a banknote bed. */
function TableWeave() {
  const rings = Array.from({ length: 7 }, (_, index) => {
    const points: string[] = [];
    const wobble = 3 + (index % 3);
    for (let degree = 0; degree <= 360; degree += 4) {
      const t = (degree * Math.PI) / 180;
      const mod = 1 + 0.022 * Math.cos(wobble * t + index * 0.6);
      const x = 300 + 262 * mod * Math.cos(t);
      const y = 150 + 108 * mod * Math.sin(t);
      points.push(`${degree ? "L" : "M"}${x.toFixed(1)},${y.toFixed(1)}`);
    }
    return points.join(" ") + " Z";
  });
  return (
    <svg className="board-weave" viewBox="0 0 600 300" preserveAspectRatio="none" aria-hidden="true">
      <ellipse cx="300" cy="150" rx="268" ry="112" fill="rgba(242,245,242,.55)" stroke="var(--ink)" strokeWidth=".8" />
      {rings.map((d, index) => (
        <path key={index} d={d} fill="none" stroke="var(--guilloche)" strokeWidth=".5" opacity={0.34 + index * 0.05} />
      ))}
      <ellipse cx="300" cy="150" rx="238" ry="92" fill="none" stroke="var(--guilloche)" strokeWidth=".6" opacity=".8" />
    </svg>
  );
}

/** The case file. It renders only at a seat derived from recorded events. */
function CaseChip({ animate }: { animate: boolean }) {
  return (
    <motion.span
      className="case-chip"
      layoutId={animate ? "case-chip" : undefined}
      transition={{ type: "spring", duration: 0.4, bounce: 0.16 }}
      aria-hidden="true"
    >
      <i />
    </motion.span>
  );
}

function KernelStamp({ mark, snap }: { mark: KernelMark | null; snap: boolean }) {
  if (!mark) {
    return (
      <div className="kernel-stamp idle" aria-hidden="true">
        <span>Awaiting case</span>
      </div>
    );
  }
  const label = mark.verdict === "HELD" ? "Held for human" : mark.verdict;
  return (
    <motion.div
      key={`${mark.stage}-${mark.verdict}`}
      className={clsx("kernel-stamp", mark.verdict.toLowerCase())}
      initial={snap ? { scale: 1.55, opacity: 0 } : false}
      animate={{ scale: 1, opacity: 1 }}
      transition={{ duration: 0.12, ease: [0.2, 0.9, 0.25, 1] }}
    >
      <span>{label}</span>
      <small>{mark.gate}</small>
    </motion.div>
  );
}

type BoardroomProps = {
  seats: RosterSeat[] | null;
  rosterError?: string;
  handoffs: Handoff[];
  state: BoardroomState;
  quarantined: boolean;
  caseRef?: string | null;
  startedAt?: string | null;
  elapsedSeconds?: number | null;
  reused?: boolean;
};

export function Boardroom({
  seats,
  rosterError,
  handoffs,
  state,
  quarantined,
  caseRef,
  startedAt,
  elapsedSeconds,
  reused,
}: BoardroomProps) {
  const reduceMotion = useReducedMotion() ?? false;
  const [openStage, setOpenStage] = useState<string | null>(null);
  const [bubbleOpen, setBubbleOpen] = useState(false);

  const spoken = handoffs.filter((h) => h.spoken);
  const latest = spoken.length ? spoken[spoken.length - 1] : null;
  const nextIndex = handoffs.findIndex((h) => !h.spoken);
  const thinkingSeat =
    state === "RUNNING" && !quarantined && nextIndex >= 0 ? handoffs[nextIndex].from : null;
  const chipSeat =
    state === "IDLE" ? null : quarantined ? "intake" : (thinkingSeat ?? latest?.from ?? "intake");
  const marks = useMemo(() => kernelMarks(handoffs, quarantined), [handoffs, quarantined]);
  const latestMark = marks.length ? marks[marks.length - 1] : null;

  // A fresh line collapses the previous bubble's expansion.
  useEffect(() => setBubbleOpen(false), [latest?.stage]);

  const seatList: RosterSeat[] =
    seats ??
    // Roster endpoint unreachable: seat the table from the handoffs themselves so
    // the run still renders. Badges honestly read "unresolved", never a guess.
    Object.keys(SEAT_AREAS).concat("kernel").map((id) => ({
      id,
      name: FALLBACK_SEAT_NAMES[id] ?? id,
      kind: id === "kernel" ? ("kernel" as const) : ("agent" as const),
      role: "",
      replaces: "",
      obligation: "",
      uses_model: false,
      provider: null,
      model: null,
      fallback_from: null,
    }));

  const seatById = new Map(seatList.map((seat) => [seat.id, seat]));
  const seatName = (id: string) => seatById.get(id)?.name ?? FALLBACK_SEAT_NAMES[id] ?? id;

  function seatStatus(id: string): SeatStatus {
    if (quarantined) {
      if (id === "intake") return "refused";
      return id === "supervisor" ? "watching" : "silenced";
    }
    if (id === "supervisor") return state === "IDLE" ? "waiting" : "watching";
    if (thinkingSeat === id) return "thinking";
    if (spoken.some((h) => h.from === id)) return "spoke";
    return "waiting";
  }

  const agentSeats = seatList.filter((seat) => seat.kind !== "kernel" && SEAT_AREAS[seat.id]);
  const kernelSeat = seatList.find((seat) => seat.kind === "kernel");
  const bubbleSeat = latest && latest.from !== "kernel" ? latest.from : null;
  const bubbleArea = bubbleSeat ? SEAT_AREAS[bubbleSeat] : null;

  const headline =
    state === "IDLE"
      ? "Models propose; the kernel disposes."
      : quarantined
        ? "Refused before any model call."
        : state === "RUNNING"
          ? (latest ? latest.label : "The case file is on the table.")
          : state === "FAILED"
            ? "The run stopped. The receipts kept."
            : `Case closed in ${elapsedSeconds != null ? `${elapsedSeconds.toFixed(1)}s` : "seconds"}.`;

  const subline =
    state === "IDLE"
      ? "Six seats and one deterministic kernel. The case file enters when a complaint runs."
      : quarantined
        ? "The firewall stopped this message before the first model read it. Six brains stayed silent."
        : state === "RUNNING"
          ? "A seat speaks only once its chained event exists. Nothing on this table runs ahead of evidence."
          : state === "FAILED"
            ? "Every stage that landed below is still signed. Nothing was invented to cover the stop."
            : "Every line below is the audit trail speaking. Click any of them for its sequence number and hash.";

  return (
    <section
      className={clsx("boardroom", quarantined && "is-refused", state === "IDLE" && "is-idle")}
      aria-label="Boardroom — the governed handoffs of this case"
      data-state={state}
    >
      <header className="board-head">
        <div>
          <p className="eyebrow mono">
            The boardroom / {state === "IDLE" ? "in session" : (caseRef ?? "case pending")}
            {reused ? " · reopened proof" : ""}
          </p>
          <h2>{headline}</h2>
          <p>{subline}</p>
        </div>
        {state !== "IDLE" ? (
          <strong className="mono board-clock">
            {elapsedSeconds != null ? `${elapsedSeconds.toFixed(1)}s` : "—"}
            <small>{spoken.length} / {handoffs.length} handoffs</small>
          </strong>
        ) : null}
      </header>

      {rosterError ? (
        <p className="board-roster-note" role="status">
          The seating plan could not be loaded ({rosterError}). The run itself is unaffected — every
          receipt below still comes from the chain.
        </p>
      ) : null}

      <p className="sr-only" role="status">
        {latest
          ? `${seatName(latest.from)} to ${seatName(latest.to)}: ${latest.says}`
          : state === "IDLE"
            ? "The boardroom is idle. No case is on the table."
            : "The case file is on the table. No handoff recorded yet."}
      </p>

      <div className="board-table" data-chip-seat={chipSeat ?? "none"}>
        {agentSeats.map((seat) => {
          const status = seatStatus(seat.id);
          const badge = seatBadge(seat);
          return (
            <article
              key={seat.id}
              className={clsx("seat", `seat-${SEAT_AREAS[seat.id]}`, `is-${status}`)}
              style={{ "--seat-accent": SEAT_ACCENTS[seat.id] ?? "var(--ink-2)" } as React.CSSProperties}
              aria-label={`${seat.name} — ${STATUS_COPY[status]}`}
            >
              <header>
                <strong>{seat.name}</strong>
                <span className="seat-dock">{chipSeat === seat.id ? <CaseChip animate={!reduceMotion} /> : null}</span>
              </header>
              {seat.role ? <p className="seat-role">{seat.role}</p> : null}
              <footer>
                <span className="seat-brain mono" title={badge.fallback ?? undefined}>{badge.line}</span>
                <span className="seat-status">
                  <i aria-hidden="true" />
                  {STATUS_COPY[status]}
                </span>
              </footer>
              {badge.fallback ? <p className="seat-fallback">{badge.fallback}</p> : null}
            </article>
          );
        })}

        <div className="board-oval">
          <TableWeave />
          <div className={clsx("kernel-block", latestMark && `is-${latestMark.verdict.toLowerCase()}`)}
            aria-label={kernelSeat ? `${kernelSeat.name} — deterministic, no model` : "Compliance kernel"}
          >
            <p className="mono">{kernelSeat?.name ?? "Compliance Kernel"}</p>
            <KernelStamp mark={latestMark} snap={!reduceMotion} />
            <span className="kernel-dock">{chipSeat === "kernel" ? <CaseChip animate={!reduceMotion} /> : null}</span>
            <small>No model. No thinking state. It snaps.</small>
            {marks.length ? (
              <ol className="kernel-ledger">
                {marks.map((mark) => (
                  <li key={`${mark.stage}-${mark.verdict}`} className={mark.verdict.toLowerCase()}>
                    <span className="mono">{mark.verdict === "HELD" ? "HELD" : mark.verdict}</span>
                    <em>{mark.gate}</em>
                  </li>
                ))}
              </ol>
            ) : null}
          </div>

          {latest && bubbleArea ? (
            <motion.div
              key={latest.stage}
              layout={!reduceMotion}
              className={clsx("board-bubble", `at-${bubbleArea}`, latest.refused && "refused")}
              style={{ "--seat-accent": SEAT_ACCENTS[latest.from] ?? "var(--ink-2)" } as React.CSSProperties}
              initial={reduceMotion ? false : { opacity: 0, y: bubbleArea.startsWith("t") ? -8 : 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.2, ease: [0.22, 0.8, 0.2, 1] }}
            >
              <button
                type="button"
                aria-expanded={bubbleOpen}
                onClick={() => setBubbleOpen((open) => !open)}
              >
                <span className="mono">{seatName(latest.from)} → {seatName(latest.to)}</span>
                <q>{latest.says}</q>
              </button>
              {bubbleOpen ? (
                <div className="bubble-evidence">
                  <dl>
                    {latest.facts.map((entry) => (
                      <div key={entry.label}><dt>{entry.label}</dt><dd>{entry.value}</dd></div>
                    ))}
                  </dl>
                  <p className="mono">
                    {latest.event_type} · SEQ {latest.seq ?? "—"} · {latest.hash ? `${latest.hash.slice(0, 14)}…` : "hash pending"}
                  </p>
                </div>
              ) : null}
            </motion.div>
          ) : null}
        </div>
      </div>

      {state !== "IDLE" ? (
        <div className="board-minutes">
          <div className="minutes-head">
            <h3>The minutes</h3>
            <span className="mono">Every line derives from a hashed event. Click one to check it.</span>
          </div>
          <ol>
            {handoffs.map((handoff, index) => {
              const open = openStage === handoff.stage;
              const kernelRow = handoff.from === "kernel";
              const mark = marks.find((entry) => entry.stage === handoff.stage);
              return (
                <li
                  key={handoff.stage}
                  className={clsx(
                    "minute",
                    handoff.spoken ? "spoken" : "quiet",
                    handoff.refused && "refused",
                    thinkingSeat && handoff.from === thinkingSeat && !handoff.spoken && index === nextIndex && "active",
                  )}
                  style={{ "--seat-accent": SEAT_ACCENTS[handoff.from] ?? "var(--ink)" } as React.CSSProperties}
                >
                  <span className="minute-seq mono">{handoff.spoken ? `SEQ ${handoff.seq ?? "—"}` : "· ·"}</span>
                  <div className="minute-body">
                    <p className="minute-route mono">
                      {seatName(handoff.from)} → {seatName(handoff.to)} · {handoff.label}
                      {kernelRow && mark ? (
                        <em className={clsx("minute-mark", mark.verdict.toLowerCase())}>
                          {mark.verdict === "HELD" ? "HELD FOR HUMAN" : mark.verdict}
                        </em>
                      ) : null}
                    </p>
                    {handoff.spoken ? (
                      <>
                        <button
                          type="button"
                          className="minute-line"
                          aria-expanded={open}
                          onClick={() => setOpenStage(open ? null : handoff.stage)}
                        >
                          {handoff.says}
                        </button>
                        {open ? (
                          <div className="minute-evidence">
                            <dl>
                              {handoff.facts.map((entry) => (
                                <div key={entry.label}><dt>{entry.label}</dt><dd>{entry.value}</dd></div>
                              ))}
                            </dl>
                            <p className="mono">
                              {handoff.event_type} · SEQ {handoff.seq ?? "—"} ·{" "}
                              {handoff.hash ? `${handoff.hash.slice(0, 18)}…` : "hash pending"}
                            </p>
                          </div>
                        ) : null}
                      </>
                    ) : (
                      <p className="minute-quiet">
                        {state === "RUNNING" && index === nextIndex
                          ? "Working. This line appears when its event is recorded."
                          : quarantined
                            ? "Never ran — the case was refused upstream."
                            : state === "RUNNING"
                              ? "Waiting for the case file."
                              : "No chained event. This stage never ran."}
                      </p>
                    )}
                  </div>
                  <span className="minute-time mono">{sinceStart(handoff, startedAt) || (handoff.spoken ? "recorded" : "")}</span>
                </li>
              );
            })}
          </ol>
        </div>
      ) : null}
    </section>
  );
}

export { stageDelta };
