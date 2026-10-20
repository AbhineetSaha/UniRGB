import Nav from './components/Nav.jsx';
import Hero from './components/Hero.jsx';
import Features from './components/Features.jsx';
import Devices from './components/Devices.jsx';
import HowItWorks from './components/HowItWorks.jsx';
import Download from './components/Download.jsx';
import Community from './components/Community.jsx';
import Footer from './components/Footer.jsx';

export default function App() {
  return (
    <>
      <a className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-20 focus:bg-surface focus:px-3 focus:py-2" href="#main">Skip to content</a>
      <Nav />
      <main id="main">
        <Hero />
        <Features />
        <Devices />
        <HowItWorks />
        <Download />
        <Community />
      </main>
      <Footer />
    </>
  );
}
