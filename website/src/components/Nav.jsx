import { useState } from 'react';

const LINKS = [['#features', 'Features'], ['#devices', 'Devices'], ['#how', 'How it works'], ['#community', 'Docs & source']];

export default function Nav() {
  const [open, setOpen] = useState(false);
  const close = () => setOpen(false);
  return (
    <header className="sticky top-0 z-10 border-b border-line bg-bg/85 backdrop-blur-md">
      <div className="wrap flex h-16 items-center gap-6">
        <a className="flex items-center gap-2.5 text-lg font-bold" href="#top"><img src="logo.svg" alt="" width="30" height="30" />UniRGB</a>
        <button className="ml-auto cursor-pointer rounded-lg border border-line px-3 py-2 md:hidden" aria-expanded={open} aria-controls="nav-links" onClick={() => setOpen(!open)}>Menu</button>
        <nav id="nav-links" aria-label="Main"
          className={`${open ? 'flex' : 'hidden'} absolute inset-x-0 top-16 flex-col border-b border-line bg-bg px-4 pt-2 pb-4
            md:static md:ml-auto md:flex md:flex-row md:items-center md:gap-6 md:border-0 md:bg-transparent md:p-0`}>
          {LINKS.map(([href, label]) => <a key={href} href={href} onClick={close} className="py-3 text-[15px] text-muted hover:text-fg md:py-0">{label}</a>)}
          <a className="btn btn-primary mt-2 justify-center md:mt-0 md:px-4 md:py-2" href="#download" onClick={close}>Download UniRGB</a>
        </nav>
      </div>
      <div className="bg-rgb absolute inset-x-0 -bottom-px h-px opacity-70" />
    </header>
  );
}
