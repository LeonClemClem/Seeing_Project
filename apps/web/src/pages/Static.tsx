/** Static pages of the mockup: Tutoriel, À propos, Besoin d'un seeing monitor ? */
import { useState } from "react";

import { tr } from "../i18n";

const linkPill = { padding: "6px 12px", border: "1px solid var(--line)", borderRadius: 999, color: "#9cc7ff", textDecoration: "none" };

export function Tutoriel() {
  return (
    <section>
      <h1>{tr("Tutoriel")}</h1>
      <div className="panel" style={{ textAlign: "center", padding: "48px 20px" }}>
        <div style={{ fontSize: 64, lineHeight: 1 }} aria-hidden="true">
          🔭✨
        </div>
        <h2 style={{ fontSize: 28, margin: "18px 0 8px" }}>{tr("Pour bientôt !")}</h2>
        <p className="muted" style={{ maxWidth: 460, margin: "0 auto" }}>
          {tr(
            "On prépare un petit guide pas à pas : lire la carte, comprendre le Cn², caler ses K avec ses mesures… En attendant, bon ciel et beau seeing ! 🌙",
          )}
        </p>
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
            </ul>
          </div>
          <div className="panel">
            <h2>{tr("Méthode et sources")}</h2>
            <p style={{ margin: 0 }}>
              {tr(
                "Seeing calculé à partir des prévisions AROME (Météo-France), par intégration du profil de Cn² selon la méthode GmMC (Cuevas 2024), puis calé sur les mesures des seeing monitors. Le détail viendra dans le tutoriel.",
              )}
            </p>
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
