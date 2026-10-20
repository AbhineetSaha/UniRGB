import Section from './Section.jsx';

const Dot = ({ className }) => <span className={`size-2 shrink-0 rounded-full ${className}`} />;
const Swatch = () => <span className="size-7 shrink-0 rounded-md bg-[#7c6cff]" />;

function Feature({ eyebrow, title, visual, flip, children }) {
  const text = <div><p className="eyebrow">{eyebrow}</p><h3 className="mt-2 mb-3 text-2xl font-bold">{title}</h3><p className="text-muted">{children}</p></div>;
  const panel = <div className="panel" aria-hidden="true">{visual}</div>;
  return (
    <div className="grid items-center gap-6 border-t border-dashed border-line py-12 first-of-type:border-t-0 md:grid-cols-2 md:gap-12">
      {flip ? <>{panel}{text}</> : <>{text}{panel}</>}
    </div>
  );
}

export default function Features() {
  return (
    <Section id="features" eyebrow="Features" title="Built to be trusted with your hardware."
      lead="UniRGB writes only to devices whose protocol has been verified, and it shows you exactly what each device confirmed.">

      <Feature eyebrow="Direct control" title="No vendor app in the background" visual={<>
        <div className="row"><Dot className="bg-ok" />Razer Basilisk V3 Pro <span className="tag text-ok">direct HID</span></div>
        <div className="row"><Dot className="bg-ok" />MSI Mystic Light 761 <span className="tag text-ok">direct HID</span></div>
        <div className="row"><Dot className="bg-ok" />Kreo Hive RGB <span className="tag text-ok">direct HID</span></div>
        <div className="row"><Dot className="bg-muted" />GPU <span className="tag text-muted">read-only · I²C not used</span></div>
      </>}>
        UniRGB talks to supported devices over USB HID using open, community-documented protocols. Razer Synapse, MSI Center and similar apps don't need to be running.
      </Feature>

      <Feature flip eyebrow="Honest state" title="What you asked for vs. what the device confirmed" visual={<>
        <div className="row"><Swatch /><span>Requested<br /><span className="font-mono">static · #7c6cff</span></span></div>
        <div className="row"><Swatch /><span>Confirmed<br /><span className="font-mono">brightness 100%</span></span><span className="tag text-ok">hardware read-back</span></div>
        <div className="row"><Swatch /><span>Confirmed<br /><span className="font-mono">static · #7c6cff</span></span><span className="tag text-warn">API accepted</span></div>
      </>}>
        Every device shows its requested and confirmed state, and how sure UniRGB is: read back from the hardware, or only accepted by the API. Untested paths are labelled as untested.
      </Feature>

      <Feature eyebrow="Sync & scenes" title="One color across everything, saved as a scene" visual={
        <div className="grid grid-cols-4 gap-2.5">
          {['mouse', 'board', 'keyboard', 'RAM'].map(d => (
            <div key={d} className="grid aspect-square items-end rounded-[10px] bg-led-b p-2 font-mono text-[11px] text-white shadow-[0_0_24px_rgb(10_132_255/.35)]">{d}</div>
          ))}
        </div>
      }>
        <strong>Sync all</strong> sets every controllable device at once. Save the result as a scene, then apply, import or export it later. UniRGB restores your last lighting when it starts.
      </Feature>

      <Feature flip eyebrow="Safety first" title="Volatile writes, restore paths, no firmware code" visual={<>
        <div className="row"><span className="grid size-7 shrink-0 place-items-center rounded-md bg-[#1d2b3a] font-mono text-xs font-semibold text-led-b">52°</span>Pump display: CPU temperature <span className="tag text-ok">°C / °F</span></div>
        <div className="row"><Dot className="bg-warn" />Sends nothing until you confirm the device</div>
        <div className="row"><Dot className="bg-ok" />Quit hands lighting back</div>
      </>}>
        UniRGB contains no SMBus, I²C, EC or firmware code, and a test enforces this. It uses volatile writes where the device allows them, every writable device has a restore path, and <strong>Quit</strong> releases your devices.
      </Feature>
    </Section>
  );
}
