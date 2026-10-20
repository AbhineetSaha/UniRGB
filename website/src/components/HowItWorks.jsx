import Section from './Section.jsx';

// Step colors walk the logo gradient: red, amber, green, blue.
const STEPS = [
  ['Install', 'Run the per-user installer. It needs no admin prompt and adds a Start Menu entry and an uninstaller.', 'border-led-r'],
  ['Detect', 'UniRGB scans your devices and splits them into controllable and monitor-only, with a reason for each.', 'border-[#c9a227]'],
  ['Customize', 'Set color, brightness, zones, and mouse settings such as DPI and polling rate.', 'border-led-g'],
  ['Sync & save', 'Sync every device to one color, save it as a scene, and quit to hand lighting back.', 'border-led-b'],
];

export default function HowItWorks() {
  return (
    <Section id="how" eyebrow="How it works" title="Four steps from install to synced.">
      <ol className="mt-10 grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
        {STEPS.map(([title, text, border], i) => (
          <li key={title} className={`border-t-2 pt-4 ${border}`}>
            <span className="font-mono text-[13px] text-muted">0{i + 1}</span>
            <h3 className="my-2 text-lg font-bold">{title}</h3>
            <p className="text-[15px] text-muted">{text}</p>
          </li>
        ))}
      </ol>
    </Section>
  );
}
