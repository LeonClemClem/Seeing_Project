import { lazy, Suspense } from "react";
import { Link, Route, Routes } from "react-router-dom";

import Header from "./components/Header";
import Home from "./pages/Home";

const SitePage = lazy(() => import("./pages/SitePage"));

export default function App() {
  return (
    <div className="app">
      <Header />
      <main className="main">
        <Suspense fallback={<div className="loading">Loading…</div>}>
          <Routes>
            <Route path="/" element={<Home />} />
            <Route path="/sites/:slug" element={<SitePage />} />
            <Route path="*" element={<NotFound />} />
          </Routes>
        </Suspense>
      </main>
      <footer className="footer">
        Forecasts from Météo-France AROME (1.3 km) and an empirical Cn² model. Seeing in arcseconds at 500 nm,
        lower is better. Experimental.
      </footer>
    </div>
  );
}

function NotFound() {
  return (
    <div className="panel empty">
      <h1>Page not found</h1>
      <Link to="/">Back to the map</Link>
    </div>
  );
}
