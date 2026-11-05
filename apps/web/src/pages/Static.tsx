/** Static pages of the mockup: Tutoriel, À propos, Besoin d'un seeing monitor ? */
import { useState, type ReactNode } from "react";

import { tr } from "../i18n";

const linkPill = { padding: "6px 12px", border: "1px solid var(--line)", borderRadius: 999, color: "#9cc7ff", textDecoration: "none" };

/** Scientific references of the method (links checked on 05/11/2026), shown in "Méthode et sources". */
const SOURCES: [string, string | null][] = [
  ["Cuevas, Marín, Blázquez & Meyer (2024), Combining Cn² models to forecast the optical turbulence at Paranal, MNRAS 529, 2208 — méthode GmMC", "https://doi.org/10.1093/mnras/stae630"],
  ["Masciadri & Jabouille (2001), Improvements in the optical turbulence parameterization for 3D simulations in a region around a telescope, A&A 376, 727 — Cn² de la couche limite (TKE)", "https://doi.org/10.1051/0004-6361:20010999"],
  ["Masciadri, Lascaux & Turchi (2017), Optical turbulence forecast: ready for an operational application, MNRAS 466, 520 — modèle de Gladstone modifié (cisaillement)", "https://doi.org/10.1093/mnras/stw3111"],
  ["Dewan, Good, Beland & Brown (1993), A model for Cn² (optical turbulence) profiles using radiosonde data, PL-TR-93-2043 — modèle comparé", "https://apps.dtic.mil/sti/pdfs/ADA279399.pdf"],
  ["Wyngaard, Izumi & Collins (1971), Behavior of the refractive-index-structure parameter near the ground, JOSA 61, 1646 — convection libre", "https://doi.org/10.1364/JOSA.61.001646"],
  ["Wyngaard & LeMone (1980), Behavior of the refractive index structure parameter in the entraining convective boundary layer, J. Atmos. Sci. 37, 1573", "https://doi.org/10.1175/1520-0469(1980)037<1573:BOTRIS>2.0.CO;2"],
  ["Trinquet & Vernin (2006), A model to forecast seeing and estimate Cn² profiles from meteorological data, PASP 118, 756", "https://doi.org/10.1086/503165"],
  ["Osborn & Sarazin (2018), Atmospheric turbulence forecasting with a general circulation model for Cerro Paranal, MNRAS 480, 1278", "https://doi.org/10.1093/mnras/sty1898"],
  ["Fried (1966), Optical resolution through a randomly inhomogeneous medium for very long and very short exposures, JOSA 56, 1372 — paramètre r₀", "https://doi.org/10.1364/JOSA.56.001372"],
  ["Roddier (1981), The effects of atmospheric turbulence in optical astronomy, Progress in Optics 19, 281 — du Cn² au seeing", "https://doi.org/10.1016/S0079-6638(08)70204-X"],
  ["Sarazin & Roddier (1990), The ESO differential image motion monitor, A&A 227, 294 — principe des seeing monitors (DIMM)", "https://ui.adsabs.harvard.edu/abs/1990A&A...227..294S/abstract"],
  ["Tatarskii (1961), Wave propagation in a turbulent medium, McGraw-Hill (livre) — relation entre turbulence et Cn²", null],
  ["Seity et al. (2011), The AROME-France convective-scale operational model, Monthly Weather Review 139, 976", "https://doi.org/10.1175/2010MWR3425.1"],
];

/** Tutorial: the method in a few unrolling panels (opened one by one; the first one open). */
const TUTO: [string, ReactNode][] = [
  [
    "D'où vient la prévision ?",
    <p key="a">
      {tr(
        "AROME, le modèle de prévision à maille fine de Météo-France, calcule toutes les heures le vent, la température, l'humidité et la turbulence de l'air, sur une grille d'environ 2 km et sur des dizaines de niveaux, du sol jusqu'à plus de 15 km. Quatre fois par jour (runs de 00, 06, 12 et 18 h TU), le site récupère ces champs et en tire le seeing de chaque heure, pour chaque lieu et pour toute la carte.",
      )}
    </p>,
  ],
  [
    "Du modèle au seeing",
    <>
      <p key="b1">
        {tr(
          "Le seeing vient de la turbulence optique, le Cn² : de petites fluctuations de température qui dévient la lumière. On la reconstruit couche par couche, avec deux origines :",
        )}
      </p>
      <ul key="b2">
        <li>{tr("près du sol, dans la couche limite : la turbulence calculée par AROME, et la convection quand le sol chauffe ;")}</li>
        <li>{tr("au-dessus : le cisaillement du vent entre les couches, jusqu'au jet stream.")}</li>
      </ul>
      <p key="b3">
        {tr("En additionnant toutes les couches, on obtient le seeing. C'est la méthode GmMC de Cuevas et al. (2024).")}
      </p>
    </>,
  ],
  [
    "Pourquoi calibrer ?",
    <>
      <p key="c1">{tr("Le seeing brut du modèle suit bien les variations d'une nuit à l'autre, mais son niveau peut être décalé :")}</p>
      <ul key="c2">
        <li>{tr("une maille d'AROME fait environ 2 km : elle ne voit pas les effets locaux du terrain ;")}</li>
        <li>{tr("le relief y est moyenné : un sommet, un col ou un fond de vallée prennent l'altitude « lissée » de la maille ;")}</li>
        <li>{tr("le modèle ignore l'environnement immédiat de l'instrument : bâtiments, arbres, coupole, chaleur du sol ;")}</li>
        <li>{tr("les formules qui passent de la turbulence du modèle au Cn² ont des coefficients réglés en moyenne, pas pour ton site.")}</li>
      </ul>
      <p key="c3">
        {tr(
          "Le choix du modèle de turbulence compte finalement peu : Cuevas et al. (2024) ont comparé plusieurs modèles de Cn² et, une fois calibrés, ils donnent presque les mêmes résultats. C'est la calibration sur des mesures qui fait la différence.",
        )}
      </p>
    </>,
  ],
  [
    "Comment calibrer ?",
    <>
      <p key="d1">
        {tr(
          "On compare les prévisions passées aux mesures d'un seeing monitor, heure par heure, nuit après nuit. Deux coefficients sont ajustés pour que la prévision colle aux mesures :",
        )}
      </p>
      <ul key="d2">
        <li>{tr("K1, pour la turbulence de la couche limite (près du sol) ;")}</li>
        <li>{tr("K2, pour la turbulence au-dessus (cisaillement, jet stream).")}</li>
      </ul>
      <p key="d3">
        {tr(
          "Les nuits aberrantes (instrument en défaut, nuages) peuvent être retirées. Plus il y a de nuits mesurées, et des nuits variées, plus le calage est fiable. La carte utilise une calibration commune ; chaque lieu calibré a la sienne.",
        )}
      </p>
    </>,
  ],
  [
    "Calibrer son lieu, pas à pas",
    <ol key="e">
      <li>{tr("Crée ton lieu depuis la carte (zoome, puis clique à l'endroit voulu) ou avec « Ajouter un lieu » dans Lieux.")}</li>
      <li>{tr("Importe les mesures de ton seeing monitor dans Calibrer.")}</li>
      <li>{tr("Lance le calage : K1 et K2 sont calculés avec tes nuits.")}</li>
      <li>{tr("Regarde la corrélation prévu / mesuré et l'erreur selon l'âge du run ; retire les nuits douteuses si besoin.")}</li>
      <li>{tr("Enregistre : tes K servent à partir du run AROME suivant.")}</li>
    </ol>,
  ],
  [
    "Lire les panneaux",
    <ul key="f">
      <li>{tr("Carte : le seeing prévu partout, heure par heure ou en moyenne de nuit ; on peut n'afficher qu'une partie de la turbulence (couche limite, tranches d'altitude, jet stream).")}</li>
      <li>{tr("Fisheye : le seeing dans chaque direction du ciel depuis ton lieu, avec les nuages et le relief à l'horizon.")}</li>
      <li>{tr("Cn² : la turbulence en altitude au fil des heures ; le passage de la couche limite à l'atmosphère libre y est visible.")}</li>
      <li>{tr("Corrélation : chaque point compare une heure (ou une nuit) prévue et mesurée ; plus les points sont près de la diagonale, meilleure est la prévision.")}</li>
      <li>{tr("Erreur selon l'âge du run : la prévision est-elle meilleure à quelques heures qu'à deux jours ?")}</li>
    </ul>,
  ],
];

export function Tutoriel() {
  return (
    <section>
      <h1>{tr("Tutoriel")}</h1>
      <p className="lead">{tr("La méthode en quelques panneaux : clique sur un titre pour le dérouler.")}</p>
      <div className="tuto">
        {TUTO.map(([title, body], k) => (
          <details key={title} className="panel" open={k === 0}>
            <summary>
              <h2>{tr(title)}</h2>
            </summary>
            <div className="tuto-body">{body}</div>
          </details>
        ))}
      </div>
    </section>
  );
}

export function APropos() {
  const [mail, setMail] = useState("");
  return (
    <section>
      <h1>{tr("À propos")}</h1>
      <div className="grid2" style={{ alignItems: "start" }}>
        <div className="panel">
          <h2>{tr("L'auteur")}</h2>
          <img
            src="/img/auteur.jpg"
            alt={tr("L'auteur à la barre d'un voilier")}
            style={{ display: "block", width: "100%", maxWidth: 360, height: "auto", borderRadius: 12, margin: "0 0 12px", border: "1px solid var(--line)" }}
          />
          <div style={{ fontFamily: "var(--f-display)", fontSize: 22, fontWeight: 700, margin: "0 0 2px" }}>Clément Brustel</div>
          <div style={{ lineHeight: 1.6, margin: "0 0 10px" }}>
            {tr("PhD · Sciences planétaires")}
            <br />
            {tr("Ingénieur géologue · Astrophotographe · Escaladeur")}
            <br />
            <b>{tr("Observatoire CosmoDrôme")}</b>
          </div>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 10 }}>
            <a href="https://www.observatoire-cosmodrome.net/" target="_blank" rel="noopener" style={linkPill}>
              🔭 {tr("Observatoire CosmoDrôme")}
            </a>
            <a href="https://www.instagram.com/clement_brustel/" target="_blank" rel="noopener" style={linkPill}>
              📷 Instagram
            </a>
            <a href="https://www.flickr.com/photos/clementbrustel/" target="_blank" rel="noopener" style={linkPill}>
              🌌 Flickr
            </a>
          </div>
        </div>
        <div className="stack" style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          <div className="panel">
            <h2>{tr("Remerciements")}</h2>
            <ul style={{ margin: 0, paddingLeft: 18, lineHeight: 1.7 }}>
              <li>{tr("Météo-France, pour le modèle AROME")}</li>
              <li>Christian Viladrich</li>
              <li>Tom Williams</li>
              <li>Thomas Hossler</li>
              <li>
                Cyril Joly, {tr("pour sa bibliothèque Python")}{" "}
                <a href="https://github.com/CyrilJl/MeteoFetch" target="_blank" rel="noopener noreferrer">
                  MeteoFetch
                </a>
              </li>
            </ul>
          </div>
          <div className="panel">
            <h2>{tr("Méthode et sources")}</h2>
            <p style={{ margin: "0 0 8px" }}>
              {tr(
                "Seeing calculé à partir des prévisions AROME (Météo-France), par intégration du profil de Cn² selon la méthode GmMC (Cuevas et al. 2024), puis calé sur les mesures des seeing monitors. La méthode est expliquée dans le tutoriel.",
              )}
            </p>
            <ul className="small" style={{ margin: 0, paddingLeft: 18, lineHeight: 1.55 }}>
              {SOURCES.map(([t, url]) => (
                <li key={t}>
                  {url ? (
                    <a href={url} target="_blank" rel="noopener noreferrer">
                      {t}
                    </a>
                  ) : (
                    t
                  )}
                </li>
              ))}
            </ul>
          </div>
          <div className="panel">
            <h2>{tr("Travaux futurs")}</h2>
            <ul style={{ margin: 0, paddingLeft: 18, lineHeight: 1.7 }}>
              <li>
                <span aria-hidden="true">☀️</span> {tr("Seeing de jour : peut-être bientôt implémenté")}
              </li>
              <li>{tr("De nouveaux modèles seront testés")}</li>
              <li>
                <span aria-hidden="true">🗺️</span> {tr("Élargissement à d'autres zones géographiques")}
              </li>
            </ul>
          </div>
          <div className="panel">
            <h2>{tr("Contact et suggestions")}</h2>
            <p className="small muted" style={{ margin: "0 0 10px" }}>
              {tr("Une idée, un bug, une remarque ? Les messages sont lus régulièrement.")}
            </p>
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
              <span style={{ padding: "6px 12px", border: "1px dashed var(--line)", borderRadius: 999, color: "var(--muted)" }}>
                💡 {tr("Envoyer une suggestion [formulaire à venir]")}
              </span>
              <button style={{ borderRadius: 999 }} onClick={() => setMail("adresse à venir")}>
                ✉️ {tr("Écrire")}
              </button>
              <span className="small muted">{tr(mail)}</span>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

export function SeeingMonitor() {
  return (
    <section>
      <h1>{tr("Besoin d'un seeing monitor ?")}</h1>
      <a
        href="https://www.facebook.com/p/Gallifrey-Optics-61576880595400/"
        target="_blank"
        rel="noopener"
        className="panel"
        style={{ display: "flex", alignItems: "center", gap: 26, margin: "0 0 14px", textDecoration: "none", color: "inherit", maxWidth: 768, padding: "22px 26px", flexWrap: "wrap" }}
      >
        <img
          src="/img/gallifrey-logo.jpg"
          alt={tr("Logo Gallifrey Optics")}
          style={{ width: 170, height: 170, flex: "0 0 170px", borderRadius: 18, objectFit: "cover" }}
        />
        <div>
          <div style={{ fontWeight: 700, fontSize: 34, letterSpacing: ".5px", lineHeight: 1.1 }}>Gallifrey Optics</div>
          <div style={{ marginTop: 8, fontSize: 19 }}>{tr("Fabricant de télescopes et de miroirs")}</div>
          <div className="small muted" style={{ display: "flex", alignItems: "center", gap: 6, marginTop: 2 }}>
            <svg width="14" height="14" viewBox="0 0 24 24" aria-hidden="true">
              <circle cx="12" cy="12" r="12" fill="#1877f2" />
              <path
                d="M13.4 19v-6.1h2l.3-2.4h-2.3V9c0-.7.2-1.2 1.2-1.2h1.2V5.7c-.2 0-1-.1-1.8-.1-1.8 0-3 1.1-3 3.1v1.8h-2v2.4h2V19z"
                fill="#fff"
              />
            </svg>
            {tr("Page Facebook")}
          </div>
        </div>
      </a>
      <div className="panel" style={{ maxWidth: 768 }}>
        <h2>{tr("SID, un seeing monitor DIMM compact, léger et à prix abordable")}</h2>
        <p style={{ margin: "0 0 10px" }}>
          <b>{tr("Prototype en cours de réalisation")}</b>
          {tr(", développé en collaboration avec Paul (Gallifrey Optics). Il s'utilise avec ta propre caméra astro.")}
        </p>
        <div style={{ maxWidth: 720, display: "flex", flexDirection: "column", gap: 12 }}>
          <div style={{ display: "flex", gap: 12, alignItems: "flex-start" }}>
            <figure style={{ margin: 0, flex: "1.233 1 0", minWidth: 0 }}>
              <img src="/img/sid-dessous.jpg" alt={tr("Schéma de SID vu de dessous")} style={{ display: "block", width: "100%", borderRadius: 10, border: "1px solid var(--line)", background: "#fff" }} />
              <figcaption className="small muted" style={{ marginTop: 4 }}>
                {tr("Schéma de SID (vue de dessous)")}
              </figcaption>
            </figure>
            <figure style={{ margin: 0, flex: "1.573 1 0", minWidth: 0 }}>
              <img src="/img/sid-trajet.jpg" alt={tr("Schéma de SID avec le trajet optique")} style={{ display: "block", width: "100%", borderRadius: 10, border: "1px solid var(--line)", background: "#fff" }} />
              <figcaption className="small muted" style={{ marginTop: 4 }}>
                {tr("Schéma de SID et trajet de la lumière")}
              </figcaption>
            </figure>
          </div>
          <figure style={{ margin: 0 }}>
            <img src="/img/sid.gif" alt={tr("SID en fonctionnement : mesure du seeing à l'écran")} style={{ display: "block", width: "100%", borderRadius: 10, border: "1px solid var(--line)" }} />
            <figcaption className="small muted" style={{ marginTop: 4 }}>
              {tr("SID en fonctionnement")}
            </figcaption>
          </figure>
        </div>
      </div>
    </section>
  );
}
