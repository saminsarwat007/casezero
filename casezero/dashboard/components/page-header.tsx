import { Guilloche } from "./design/guilloche";
import { MicroRule } from "./design/micro-rule";

export function PageHeader({ eyebrow, title, lede, action }: { eyebrow: string; title: string; lede: string; action?: React.ReactNode }) {
  return (
    <>
      <header className="page-header">
        <Guilloche className="guilloche" />
        <div className="header-copy">
          <p className="eyebrow mono">{eyebrow}</p>
          <h1 className="page-title">{title}</h1>
          <p className="page-lede">{lede}</p>
          {action ? <div style={{ marginTop: 18 }}>{action}</div> : null}
        </div>
      </header>
      <MicroRule />
    </>
  );
}
