import ExternalLink, { REPO } from './ExternalLink.jsx';

export default function Footer() {
  return (
    <footer className="border-t border-line py-10 text-sm text-muted">
      <div className="wrap flex flex-wrap items-center gap-x-8 gap-y-4">
        <a className="flex items-center gap-2.5 text-lg font-bold text-fg" href="#top"><img src="logo.svg" alt="" width="24" height="24" />UniRGB</a>
        <span>© 2026 Abhineet Saha · <ExternalLink className="hover:text-fg" href={`${REPO}/blob/main/LICENSE`}>GPL-3.0-or-later</ExternalLink></span>
        <nav aria-label="Footer" className="ml-auto flex flex-wrap gap-x-6 gap-y-4 [&_a]:hover:text-fg">
          <a href="#features">Features</a>
          <a href="#devices">Devices</a>
          <a href="#download">Download</a>
          <ExternalLink href={`${REPO}/tree/main/docs`}>Docs</ExternalLink>
          <ExternalLink href={REPO}>GitHub</ExternalLink>
        </nav>
      </div>
    </footer>
  );
}
