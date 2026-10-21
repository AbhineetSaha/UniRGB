import Section from './Section.jsx';
import ExternalLink, { REPO } from './ExternalLink.jsx';

// Mirrors the README's "Supported devices" table; keep the two in sync.
const DEVICES = [
  ['Razer Basilisk V3 Pro', '1532:00AA / 00AB', 'Color, zones (experimental), hardware brightness with read-back, DPI, DPI stages, polling rate, sleep timer, battery', "Direct HID. Lighting is never written to the mouse's saved profile"],
  ['MSI Mystic Light 761 boards', '0DB0:0076', 'ARGB / EZ Conn headers per zone, setup read-back, baseline restore', 'Direct HID. Blocked while MSI Center lighting runs. Tested on X870E GAMING PLUS WIFI'],
  ['Kreo Hive RGB and other Evision V2 keyboards', '320F:5055', 'Whole-keyboard color, off', 'Direct HID, live colors only. The keyboard reverts by itself when UniRGB stops'],
  ['Ant Esports AIO pump display', '5131:2007', 'CPU or GPU temperature, °C/°F', 'HID output reports, only after you confirm the device'],
  ['RAM', null, 'Color', "Through OpenRGB's SDK server if you run it. UniRGB's own RAM support is in progress"],
  ['Razer Chroma devices', null, 'Color', "Optional fallback through Razer's Chroma SDK if Synapse is installed"],
  ['Everything else', null, "Listed, with the reason it isn't controllable", 'Read-only inventory'],
];

const cell = 'border-b border-line px-4 py-3.5 text-left align-top';

export default function Devices() {
  return (
    <Section id="devices" eyebrow="Compatibility" title="Supported devices, with evidence."
      lead={<>This is a small, verified list, not a long, hopeful one. Each row is backed by the <ExternalLink href={`${REPO}/blob/main/docs/device-capability-matrix.md`}>device capability matrix</ExternalLink>.</>}>
      <div className="mt-8 overflow-x-auto rounded-xl border border-line">
        <table className="w-full min-w-[640px] border-collapse text-[15px]">
          <thead>
            <tr>{['Device', 'What works', 'How'].map(h => <th key={h} scope="col" className={`${cell} bg-surface font-mono text-xs font-semibold tracking-widest text-muted uppercase`}>{h}</th>)}</tr>
          </thead>
          <tbody className="[&_tr:last-child_td]:border-b-0">
            {DEVICES.map(([name, id, works, how]) => (
              <tr key={name}>
                <td className={`${cell} font-semibold`}>{name}{id && <small className="block font-mono text-xs font-normal text-muted">{id}</small>}</td>
                <td className={cell}>{works}</td>
                <td className={cell}>{how}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="note">Missing your device? <ExternalLink href={`${REPO}/issues`}>Request support on GitHub</ExternalLink>. Planned next: RAM lighting without OpenRGB, and Windows Dynamic Lighting devices from any vendor (<ExternalLink href={`${REPO}/blob/main/docs/roadmap.md`}>roadmap</ExternalLink>). Linux and macOS have no device support yet.</p>
    </Section>
  );
}
