/** Account page: login / sign-up against /api/auth, the logged-in account, and the privacy notes. */
import { useState, type FormEvent } from "react";

import type { UserRole } from "../api";
import { Seg } from "../components/ui";
import { useAuthActions, useMe } from "../data/auth";
import { tr } from "../i18n";
import { authErrorMessage } from "../lib/authErrors";
import { setState, useUi, type Role } from "../store";

const ROLE_LABEL: Record<UserRole, string> = { user: "Utilisateur", team: "Équipe CosmoDrôme", admin: "Administrateur" };

export default function Compte() {
  const role = useUi((s) => s.role);
  const me = useMe();
  const user = me.data?.user ?? null;

  return (
    <section>
      <h1>{tr("Compte")}</h1>
      {!user && (
        <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap", margin: "0 0 10px" }}>
          <span className="small muted">{tr("Vue de la maquette :")}</span>
          <Seg<Role>
            value={role}
            onChange={(r) => setState({ role: r })}
            options={[
              ["user", tr("Utilisateur")],
              ["team", tr("Équipe CosmoDrôme")],
              ["admin", tr("Administrateur")],
            ]}
          />
          <span className="small muted">
            {tr("Les K des sites publics ne sont visibles que par l'administrateur ; chacun voit les K de ses propres lieux.")}
          </span>
        </div>
      )}
      <p className="lead">
        {tr(
          "Un compte est nécessaire pour enregistrer des lieux, importer des mesures, régler les K et calculer un fisheye. Sans compte, on peut consulter la carte et les lieux partagés.",
        )}
      </p>
      <div className="panel" style={{ marginBottom: 14 }}>
        <h2>{tr("Types de comptes")}</h2>
        <div className="tiles" style={{ gridTemplateColumns: "repeat(auto-fit,minmax(200px,1fr))" }}>
          {[
            ["Administrateur", "Compte personnel", "Calibre la carte globale et les sites publics, voit tous les K."],
            [
              "Équipe CosmoDrôme",
              "Compte commun",
              "Partagé par l'équipe : mesures et calage du CosmoDrôme, ses K visibles par l'équipe, partage avec la communauté.",
            ],
            ["Utilisateur", "Compte individuel", "Ses lieux, ses mesures, ses K ; consulte les sites publics et partagés."],
          ].map(([l, v, d]) => (
            <div className="tile" key={l}>
              <div className="l">{tr(l!)}</div>
              <div className="v" style={{ fontSize: 15 }}>
                {tr(v!)}
              </div>
              <div className="small muted">{tr(d!)}</div>
            </div>
          ))}
        </div>
      </div>
      <div className="grid2">
        <div className="panel">{me.isLoading ? <p className="muted">{tr("Chargement…")}</p> : user ? <Account /> : <LoginForm />}</div>
        <div className="panel">
          <h2>{tr("Vie privée et données")}</h2>
          <ul className="small" style={{ margin: 0, paddingLeft: 18, display: "grid", gap: 6 }}>
            <li>
              {tr("Un lieu partagé apparaît aux autres par un symbole à")} <b>5–11 km</b>{" "}
              {tr("de sa vraie position (2 à 4 cellules AROME), toujours au même endroit, sans nom ni position exacte.")}
            </li>
            <li>{tr("La position exacte sert seulement au calcul de la maille AROME et des K par défaut des voisins.")}</li>
            <li>{tr("Les mesures partagées aident à caler les K des lieux voisins.")}</li>
            <li>{tr("Tu peux exporter toutes tes données ou supprimer ton compte à tout moment.")}</li>
          </ul>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 12, alignItems: "center" }}>
            <button disabled={!user}>{tr("Exporter mes données")}</button>
            <button disabled={!user}>{tr("Supprimer le compte")}</button>
            {user && <span className="small muted">{tr("(bientôt disponible)")}</span>}
          </div>
        </div>
      </div>
    </section>
  );
}

function Account() {
  const user = useMe().data!.user!;
  const { logout } = useAuthActions();
  return (
    <>
      <h2>{tr("Mon compte")}</h2>
      <div className="tiles" style={{ marginBottom: 12 }}>
        <div className="tile">
          <div className="l">{tr("Nom")}</div>
          <div className="v" style={{ fontSize: 15 }}>
            {user.display_name ?? "–"}
          </div>
        </div>
        <div className="tile">
          <div className="l">{tr("E-mail")}</div>
          <div className="v" style={{ fontSize: 15, overflowWrap: "anywhere" }}>
            {user.email}
          </div>
        </div>
        <div className="tile">
          <div className="l">{tr("Type de compte")}</div>
          <div className="v" style={{ fontSize: 15 }}>
            {tr(ROLE_LABEL[user.role])}
          </div>
        </div>
      </div>
      <button onClick={() => logout.mutate()} disabled={logout.isPending}>
        {tr("Se déconnecter")}
      </button>
      {logout.isError && <p className="err">{tr("Erreur du serveur. Réessaie dans un instant.")}</p>}
    </>
  );
}

function LoginForm() {
  const { login, signup } = useAuthActions();
  const [mode, setMode] = useState<"login" | "signup">("login");
  const [f, setF] = useState({ email: "", password: "", password2: "", name: "" });
  const [err, setErr] = useState("");
  const busy = login.isPending || signup.isPending;
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => {
    setF({ ...f, [k]: e.target.value });
    setErr("");
  };

  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(f.email.trim())) return setErr("Entre une adresse e-mail valide.");
    if (!f.password) return setErr("Entre ton mot de passe.");
    const fail = (x: unknown) => setErr(authErrorMessage(x, mode));
    if (mode === "login") return login.mutate({ email: f.email.trim(), password: f.password }, { onError: fail });
    if (f.password.length < 10) return setErr("Le mot de passe doit faire au moins 10 caractères.");
    if (f.password !== f.password2) return setErr("Les deux mots de passe ne correspondent pas.");
    signup.mutate({ email: f.email.trim(), password: f.password, display_name: f.name.trim() || undefined }, { onError: fail });
  };

  return (
    <>
      <h2>{tr(mode === "login" ? "Connexion" : "Créer un compte")}</h2>
      <form noValidate onSubmit={submit}>
        {mode === "signup" && (
          <>
            <label className="small muted" htmlFor="nm">
              {tr("Nom affiché (facultatif)")}
            </label>
            <input id="nm" autoComplete="name" style={{ width: "100%", margin: "2px 0 8px" }} value={f.name} onChange={set("name")} />
          </>
        )}
        <label className="small muted" htmlFor="em">
          {tr("E-mail")}
        </label>
        <input
          id="em"
          type="email"
          autoComplete="email"
          style={{ width: "100%", margin: "2px 0 8px" }}
          placeholder={tr("nom@exemple.fr")}
          value={f.email}
          onChange={set("email")}
        />
        <label className="small muted" htmlFor="pw">
          {tr("Mot de passe")}
        </label>
        <input
          id="pw"
          type="password"
          autoComplete={mode === "login" ? "current-password" : "new-password"}
          style={{ width: "100%", margin: "2px 0 8px" }}
          value={f.password}
          onChange={set("password")}
        />
        {mode === "signup" && (
          <>
            <label className="small muted" htmlFor="pw2">
              {tr("Confirme le mot de passe")}
            </label>
            <input
              id="pw2"
              type="password"
              autoComplete="new-password"
              style={{ width: "100%", margin: "2px 0 4px" }}
              value={f.password2}
              onChange={set("password2")}
            />
            <p className="small muted" style={{ margin: "0 0 4px" }}>
              {tr("Au moins 10 caractères.")}
            </p>
          </>
        )}
        <p className="err" role="alert">
          {err ? tr(err) : ""}
        </p>
        <button className="primary" type="submit" disabled={busy}>
          {tr(mode === "login" ? "Se connecter" : "Créer le compte")}
        </button>{" "}
        <button
          type="button"
          className="small"
          style={{ background: "none", border: "none", color: "#9cc7ff", padding: 0 }}
          onClick={() => {
            setMode(mode === "login" ? "signup" : "login");
            setErr("");
          }}
        >
          {tr(mode === "login" ? "Pas de compte ? Créer un compte" : "Déjà un compte ? Se connecter")}
        </button>
      </form>
    </>
  );
}
