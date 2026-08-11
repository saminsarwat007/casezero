"use client";

import { useState } from "react";
import { clsx } from "clsx";
import type { Handoff, RosterSeat, RunValue } from "@/components/boardroom";
import { stageDelta } from "@/components/boardroom";

const rm = new Intl.NumberFormat("en-MY", { style: "currency", currency: "MYR", maximumFractionDigits: 0 });
const wholeNumber = new Intl.NumberFormat("en-MY", { maximumFractionDigits: 0 });

/** Complaints filed per month. Not in the brief and not measured, so it is an
 *  assumption the viewer is invited to overwrite — never a claimed number. */
const DEFAULT_MONTHLY_VOLUME = 1200;

type ValueLedgerProps = {
  handoffs: Handoff[];
  value: RunValue;
  seats: RosterSeat[] | null;
  analystDefault: number | null;
  startedAt?: string | null;
  quarantined: boolean;
  running: boolean;
};

export function ValueLedger({ handoffs, value, seats, analystDefault, startedAt, quarantined, running }: ValueLedgerProps) {
  const [rate, setRate] = useState<string>(() => String(analystDefault ?? 24));
  const [volume, setVolume] = useState<string>(String(DEFAULT_MONTHLY_VOLUME));

  const replacesBySeat = new Map((seats ?? []).map((seat) => [seat.id, seat.replaces]));
  const rateValue = Number.parseFloat(rate);
  const volumeValue = Number.parseFloat(volume);
  const assumptionsValid = Number.isFinite(rateValue) && rateValue > 0 && Number.isFinite(volumeValue) && volumeValue > 0;
  const hoursPerYear = assumptionsValid ? (value.minutes_saved * volumeValue * 12) / 60 : 0;
  const rmPerYear = assumptionsValid ? hoursPerYear * rateValue : 0;

  if (quarantined) {
    return (
      <section className="value-ledger refused" aria-labelledby="value-title">
        <header className="value-head">
          <div>
            <p className="eyebrow mono">Business value / this case</p>
            <h2 id="value-title">No savings claimed.</h2>
            <p>
              This case was refused before the first model call, so it spent nothing and it saved
              nothing. The value of a refusal is the loss that never happened — we do not put a
              number on that.
            </p>
          </div>
        </header>
      </section>
    );
  }

  return (
    <section className="value-ledger" aria-labelledby="value-title">
      <header className="value-head">
        <div>
          <p className="eyebrow mono">Business value / investigator time freed</p>
          <h2 id="value-title">
            {running ? "The meter is running." : `${value.minutes_saved.toFixed(1)} analyst minutes handed back.`}
          </h2>
          <p>
            Each row is one human desk this run stood in for. Two kinds of number sit side by
            side and are labelled apart: what the chain <strong>measured</strong>, and what the
            case study's 90-minute manual <strong>baseline</strong> attributes to that desk.
          </p>
        </div>
        <dl className="value-tiers" aria-label="How to read these numbers">
          <div className="tier-measured"><dt>Measured</dt><dd>Timestamps on this run's hash chain</dd></div>
          <div className="tier-baseline"><dt>Baseline</dt><dd>The brief's 90 manual minutes, split per desk</dd></div>
          <div className="tier-assumption"><dt>Assumption</dt><dd>Editable below — never presented as fact</dd></div>
        </dl>
      </header>

      <p className="value-scroll-hint mono">Swipe or use the arrow keys to read every column.</p>
      <div className="value-table-wrap" role="region" aria-label="Stage-by-stage value ledger" tabIndex={0}>
        <table className="value-table">
          <caption className="sr-only">Measured run time compared with the stated manual baseline for each complaint stage.</caption>
          <thead>
            <tr>
              <th scope="col">Stage</th>
              <th scope="col">Human desk replaced</th>
              <th scope="col" className="num">Manual <i className="tier-tag baseline">baseline</i></th>
              <th scope="col" className="num">This run <i className="tier-tag measured">measured</i></th>
              <th scope="col" className="num">Handed back</th>
            </tr>
          </thead>
          <tbody>
            {handoffs.map((handoff, index) => {
              const desk = replacesBySeat.get(handoff.from) ?? "—";
              const actual = stageDelta(handoffs, index, startedAt);
              const saved = handoff.spoken
                ? Math.max(handoff.baseline_minutes - (actual ? Number.parseFloat(actual) / 60 : 0), 0)
                : null;
              return (
                <tr key={handoff.stage} className={clsx(!handoff.spoken && "quiet")}>
                  <th scope="row">{handoff.label}</th>
                  <td>{desk}</td>
                  <td className="num mono">{handoff.baseline_minutes} min</td>
                  <td className="num mono">{handoff.spoken ? (actual || "recorded") : running ? "—" : "did not run"}</td>
                  <td className="num mono">{saved == null ? "—" : `${saved.toFixed(1)} min`}</td>
                </tr>
              );
            })}
          </tbody>
          <tfoot>
            <tr>
              <th scope="row" colSpan={2}>
                Case total
                <small>
                  {value.stages_spoken} of {value.stages_total} stages ran — savings are only
                  claimed for those
                </small>
              </th>
              <td className="num mono">{value.baseline_minutes_realised} min</td>
              <td className="num mono">{value.elapsed_seconds.toFixed(1)}s</td>
              <td className="num mono total">{value.minutes_saved.toFixed(1)} min</td>
            </tr>
          </tfoot>
        </table>
      </div>

      <div className="value-annual">
        <div className="value-inputs">
          <p className="eyebrow mono">Assumptions — yours to change</p>
          <div className="value-fields">
            <label>
              Analyst cost, RM per hour
              <input
                className="input mono"
                name="analyst_hourly_rm"
                type="number"
                min="1"
                step="1"
                inputMode="decimal"
                autoComplete="off"
                value={rate}
                onChange={(event) => setRate(event.target.value)}
                aria-describedby="value-rate-note"
              />
            </label>
            <label>
              Complaints per month
              <input
                className="input mono"
                name="monthly_complaints"
                type="number"
                min="1"
                step="50"
                inputMode="numeric"
                autoComplete="off"
                value={volume}
                onChange={(event) => setVolume(event.target.value)}
              />
            </label>
          </div>
          <p id="value-rate-note">
            The rate defaults to the API's declared assumption{analystDefault != null ? ` (RM${analystDefault}/h)` : ""};
            the volume is yours. Neither is measured, which is exactly why you can edit them.
          </p>
        </div>
        <div className="value-projection">
          <p className="eyebrow mono">If every case saved what this one {running ? "is saving" : "saved"}</p>
          <div className="value-figures">
            <div>
              <strong className="mono" aria-live="polite" aria-atomic="true">{assumptionsValid ? wholeNumber.format(Math.round(hoursPerYear)) : "—"}</strong>
              <span>analyst hours freed / year <i className="tier-tag assumption">assumption</i></span>
            </div>
            <div>
              <strong className="mono" aria-live="polite" aria-atomic="true">{assumptionsValid ? rm.format(Math.round(rmPerYear)) : "—"}</strong>
              <span>at your rate / year <i className="tier-tag assumption">assumption</i></span>
            </div>
          </div>
          <p>
            Built from this run's <em>measured</em> {value.minutes_saved.toFixed(1)} minutes ×
            your two assumptions. Change either input and the figure follows.
          </p>
        </div>
      </div>
    </section>
  );
}
