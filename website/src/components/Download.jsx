import { useEffect, useState } from 'react';
import Section from './Section.jsx';
import ExternalLink, { REPO } from './ExternalLink.jsx';

// Point the button at the installer once a GitHub release exists; until then it opens the Releases page.
function useLatestRelease() {
  const [state, setState] = useState({ status: 'loading' });
  useEffect(() => {
    fetch('https://api.github.com/repos/AbhineetSaha/UniRGB/releases/latest')
      .then(r => (r.ok ? r.json() : null))
      .then(rel => {
        if (!rel) return setState({ status: 'none' });
        const asset = rel.assets.find(a => /setup.*\.exe$/i.test(a.name)) || rel.assets.find(a => /\.exe$/i.test(a.name));
        setState({ status: 'ready', rel, url: asset?.browser_download_url });
      })
      .catch(() => setState({ status: 'error' }));
  }, []);
  return state;
}

function Status({ status, rel }) {
  if (status === 'loading') return 'Checking for the latest release…';
  if (status === 'none') return 'No release is published yet. Run from source for now, or watch the repository for the first release.';
  if (status === 'error') return "Couldn't check for releases. The button opens the Releases page on GitHub.";
  const date = new Date(rel.published_at).toLocaleDateString(undefined, { dateStyle: 'medium' });
  return <>{rel.tag_name} · released {date} · <ExternalLink href={rel.html_url}>release notes</ExternalLink></>;
}

export default function Download() {
  const release = useLatestRelease();
  return (
    <Section id="download">
      {/* min-w-0 lets the <pre> scroll instead of widening its column */}
      <div className="grid gap-12 lg:grid-cols-[1.2fr_1fr] [&>*]:min-w-0">
        <div>
          <p className="eyebrow">Download</p>
          <h2 className="mt-3 mb-4 text-[clamp(28px,4vw,40px)] font-bold">Get UniRGB for Windows.</h2>
          <div className="relative overflow-hidden rounded-[14px] border border-line bg-surface p-7">
            <div className="bg-rgb absolute inset-x-0 top-0 h-[3px]" />
            <ExternalLink className="btn btn-primary" href={release.url || `${REPO}/releases`}>Download UniRGB</ExternalLink>
            <p className="mt-5 flex items-start gap-2.5 text-[15px] text-muted" role="status">
              <span className={`mt-2 size-2 shrink-0 rounded-full ${release.status === 'ready' ? 'bg-ok' : 'bg-warn'}`} />
              <span><Status {...release} /></span>
            </p>
            <dl className="mt-6 grid grid-cols-[auto_1fr] gap-x-5 gap-y-2 text-[15px] [&_dt]:text-muted">
              <dt>Platform</dt><dd>Windows 10 / 11, x64</dd>
              <dt>Install</dt><dd>Per-user, no admin rights</dd>
              <dt>License</dt><dd>GPL-3.0-or-later</dd>
            </dl>
          </div>
        </div>
        <div>
          <p className="eyebrow">Or run from source</p>
          <p className="lead mt-3 text-base">Requires Python 3.11+. Standard library only, no dependencies.</p>
          <pre className="mt-3 overflow-x-auto rounded-[10px] border border-line bg-bg p-4 font-mono text-sm leading-[1.7]"><code>{`git clone ${REPO}\ncd UniRGB\npython -m unirgb`}</code></pre>
          <p className="note">UniRGB opens its own window. The one-time driver setup for CPU temperature works only in the installed app. If something doesn't work, see <ExternalLink href={`${REPO}#troubleshooting`}>troubleshooting</ExternalLink>.</p>
        </div>
      </div>
    </Section>
  );
}
