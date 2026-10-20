export const REPO = 'https://github.com/AbhineetSaha/UniRGB';

export default function ExternalLink({ href, children, ...rest }) {
  return <a href={href} target="_blank" rel="noopener noreferrer" {...rest}>{children}</a>;
}
