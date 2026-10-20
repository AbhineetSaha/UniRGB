import Section from './Section.jsx';
import ExternalLink, { REPO } from './ExternalLink.jsx';

const LINKS = [
  [REPO, 'Source code', 'Browse the code on GitHub.'],
  [`${REPO}/issues`, 'Issues', 'Report bugs or request a device.'],
  [`${REPO}/blob/main/docs/security-and-safety.md`, 'Safety model', "What UniRGB will and won't write."],
  [`${REPO}/blob/main/CONTRIBUTING.md`, 'Contribute', 'Read this before adding a device.'],
];

export default function Community() {
  return (
    <Section id="community" eyebrow="Docs & source" title="Open source, and open about how it works.">
      <div className="mt-8 grid grid-cols-[repeat(auto-fit,minmax(220px,1fr))] gap-4">
        {LINKS.map(([href, title, text]) => (
          <ExternalLink key={title} href={href} className="block rounded-xl border border-line p-5 transition-colors hover:border-line-hover">
            <strong className="mb-1 block">{title} →</strong>
            <span className="text-sm text-muted">{text}</span>
          </ExternalLink>
        ))}
      </div>
    </Section>
  );
}
