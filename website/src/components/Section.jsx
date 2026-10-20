export default function Section({ id, eyebrow, title, lead, children }) {
  return (
    <section id={id} className="py-24 border-t border-line">
      <div className="wrap">
        {eyebrow && <p className="eyebrow">{eyebrow}</p>}
        {title && <h2 className="text-[clamp(28px,4vw,40px)] font-bold mt-3 mb-4">{title}</h2>}
        {lead && <p className="lead">{lead}</p>}
        {children}
      </div>
    </section>
  );
}
