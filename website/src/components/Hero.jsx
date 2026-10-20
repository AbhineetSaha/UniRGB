export default function Hero() {
  return (
    <div className="overflow-hidden pt-22 text-center" id="top">
      <div className="wrap">
        <p className="eyebrow">Open source · Windows 10/11 · GPL-3.0</p>
        <h1 className="mx-auto my-5 max-w-[14ch] text-[clamp(40px,7vw,76px)] font-bold">
          One app for <span className="bg-rgb bg-clip-text text-transparent">every light</span> it can truly control.
        </h1>
        <p className="lead mx-auto mb-8">UniRGB drives supported mice, motherboards, keyboards and cooler displays directly, without vendor software running. For anything it can't control safely, it tells you which device and why.</p>
        <div className="flex flex-wrap justify-center gap-3">
          <a className="btn btn-primary" href="#download">Download UniRGB</a>
          <a className="btn" href="#features">Explore features</a>
        </div>
        <small className="mt-4 block text-sm text-muted">No admin rights needed. No telemetry, no accounts.</small>
        <figure className="relative isolate mt-16">
          <div className="bg-rgb absolute inset-x-[8%] top-[10%] -bottom-[10%] -z-10 opacity-20 blur-[90px]" />
          <img className="rounded-t-[14px] border border-b-0 border-line" src="app.png" width="2560" height="1600" alt="The UniRGB app: a device list split into controllable and monitor-only devices, with lighting controls and requested versus confirmed state for the selected device." />
          <figcaption className="pt-3 text-[13px] text-muted">The real UniRGB v0.1.0 app, shown with simulation mode on.</figcaption>
        </figure>
      </div>
    </div>
  );
}
