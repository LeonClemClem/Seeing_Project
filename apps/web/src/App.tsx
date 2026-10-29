import { lazy, Suspense } from "react";
import { Link, Navigate, Route, Routes } from "react-router-dom";

import Header from "./components/Header";
import { HatchDefs, Spinner } from "./components/ui";
import { tr } from "./i18n";
import Carte from "./pages/Carte";
import Compte from "./pages/Compte";
import { APropos, SeeingMonitor, Tutoriel } from "./pages/Static";
import { useUi } from "./store";

const Prevision = lazy(() => import("./pages/Prevision"));
const Fisheye = lazy(() => import("./pages/Fisheye"));
const Calibrer = lazy(() => import("./pages/Calibrer"));
const Lieux = lazy(() => import("./pages/Lieux"));

export default function App() {
  // Re-render the whole tree when the language changes: every view reads its strings through tr().
  useUi((s) => s.lang);
  return (
    <>
      <Header />
      <main>
        <Suspense fallback={<Spinner />}>
          <Routes>
            <Route path="/" element={<Navigate to="/carte" replace />} />
            <Route path="/carte" element={<Carte />} />
            <Route path="/prevision" element={<Prevision />} />
            <Route path="/fisheye" element={<Fisheye />} />
            <Route path="/calibrer" element={<Calibrer />} />
            <Route path="/lieux" element={<Lieux />} />
            <Route path="/compte" element={<Compte />} />
            <Route path="/tutoriel" element={<Tutoriel />} />
            <Route path="/a-propos" element={<APropos />} />
            <Route path="/seeing-monitor" element={<SeeingMonitor />} />
            <Route path="*" element={<NotFound />} />
          </Routes>
        </Suspense>
      </main>
      <HatchDefs />
    </>
  );
}

function NotFound() {
  return (
    <div className="panel">
      <h1>{tr("Page introuvable")}</h1>
      <Link to="/carte">{tr("Retour à la carte")}</Link>
    </div>
  );
}
