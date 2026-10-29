/** Account page: login / sign-up against /api/auth (password rules, e-mail confirmation), the logged-in
 * account, and the privacy notes. */
import { useEffect, useRef, useState, type FormEvent } from "react";
import { useSearchParams } from "react-router-dom";

import { ApiError, type UserRole } from "../api";
import { Seg } from "../components/ui";
import { useAuthActions, useMe } from "../data/auth";
import { tr } from "../i18n";
import { authErrorMessage } from "../lib/authErrors";
import { checkRules, MIN_LENGTH, strength } from "../lib/passwordRules";
import { setState, useUi, type Role } from "../store";

const ROLE_LABEL: Record<UserRole, string> = { user: "Utilisateur", team: "Équipe CosmoDrôme", admin: "Administrateur" };

export default function Compte() {
  const role = useUi((s) => s.role);
  const me = useMe();
  const user = me.data?.user ?? null;
  const verifMsg = useVerifyLink();

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
        <div className="panel">
          {verifMsg && (
            <p className={verifMsg.ok ? "small" : "err"} role="status" style={{ marginTop: 0 }}>
              {tr(verifMsg.text)}
            </p>
          )}
          {me.isLoading ? <p className="muted">{tr("Chargement…")}</p> : user ? <Account /> : <LoginForm />}
        </div>
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

/** The e-mailed confirmation link (/compte?verif=<token>): confirm once, log in, and take the token out of
 * the address bar. */
function useVerifyLink(): { ok: boolean; text: string } | null {
  const [params, setParams] = useSearchParams();
  const { verify } = useAuthActions();
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const done = useRef(false);
  const token = params.get("verif");
  useEffect(() => {
    if (!token || done.current) return;
    done.current = true; // the link works once: never send it twice (React strict mode runs effects twice)
    setParams({}, { replace: true });
    verify.mutate(token, {
      onSuccess: () => setMsg({ ok: true, text: "Adresse e-mail confirmée : ton compte est activé et tu es connecté." }),
      onError: (e) => setMsg({ ok: false, text: authErrorMessage(e, "login") }),
    });
  }, [token, setParams, verify]);
  return msg;
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
  const { login, signup, resend } = useAuthActions();
  const [mode, setMode] = useState<"login" | "signup" | "pending">("login");
  const [f, setF] = useState({ email: "", password: "", password2: "", name: "" });
  const [err, setErr] = useState("");
  const [pending, setPending] = useState({ email: "", sent: true });
  const [resent, setResent] = useState(false);
  const busy = login.isPending || signup.isPending;
  const rules = checkRules(f.password, f.email.trim());
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => {
    setF({ ...f, [k]: e.target.value });
    setErr("");
  };
  const toPending = (email: string, sent: boolean) => {
    setPending({ email, sent });
    setResent(false);
    setErr("");
    setMode("pending");
  };

  const submit = (e: FormEvent) => {
    e.preventDefault();
    const email = f.email.trim();
    if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) return setErr("Entre une adresse e-mail valide.");
    if (!f.password) return setErr("Entre ton mot de passe.");
    const fail = (x: unknown) => {
      if (x instanceof ApiError && x.message === "email_not_verified") return toPending(email, false);
      setErr(authErrorMessage(x, mode === "signup" ? "signup" : "login"));
    };
    if (mode === "login") return login.mutate({ email, password: f.password }, { onError: fail });
    if (!rules.length) return setErr(`Le mot de passe doit faire au moins ${MIN_LENGTH} caractères.`);
    if (!rules.kinds)
      return setErr("Le mot de passe doit mêler au moins 3 types de caractères : minuscules, majuscules, chiffres, symboles.");
    if (!rules.email) return setErr("Le mot de passe ne doit pas contenir ton adresse e-mail.");
    if (f.password !== f.password2) return setErr("Les deux mots de passe ne correspondent pas.");
    signup.mutate(
      { email, password: f.password, display_name: f.name.trim() || undefined },
      { onSuccess: (r) => ("pending" in r ? toPending(r.email, r.sent) : undefined), onError: fail },
    );
  };

  if (mode === "pending")
    return (
      <>
        <h2>{tr("Confirme ton adresse e-mail")}</h2>
        <p className="small">
          {tr(pending.sent ? "Un e-mail de confirmation a été envoyé à" : "Ton adresse n'est pas encore confirmée :")}{" "}
          <b>{pending.email}</b>.{" "}
          {tr("Ouvre le lien qu'il contient (valable 48 heures) pour activer ton compte. Pense à regarder dans les indésirables.")}
        </p>
        <button
          onClick={() =>
            resend.mutate(pending.email, { onSuccess: () => setResent(true), onError: (x) => setErr(authErrorMessage(x, "login")) })
          }
          disabled={resend.isPending || resent}
        >
          {tr(resent ? "E-mail renvoyé" : "Renvoyer l'e-mail")}
        </button>{" "}
        <button
          type="button"
          className="small"
          style={{ background: "none", border: "none", color: "#9cc7ff", padding: 0 }}
          onClick={() => {
            setMode("login");
            setErr("");
          }}
        >
          {tr("Retour à la connexion")}
        </button>
        <p className="err" role="alert">
          {err ? tr(err) : ""}
        </p>
      </>
    );

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
            <StrengthMeter level={strength(f.password, f.email.trim())} />
            <ul className="small" style={{ margin: "4px 0 8px", paddingLeft: 0, listStyle: "none", display: "grid", gap: 2 }}>
              {(
                [
                  [rules.length, `Au moins ${MIN_LENGTH} caractères`],
                  [rules.kinds, "Au moins 3 types : minuscules, majuscules, chiffres, symboles"],
                  [rules.email, "Ne contient pas ton adresse e-mail"],
                ] as const
              ).map(([ok, t]) => (
                <li key={t} style={{ color: !f.password ? "var(--muted)" : ok ? "#6fdc8c" : "#ff8a7a" }}>
                  {ok && f.password ? "✓" : "•"} {tr(t)}
                </li>
              ))}
              <li className="muted">{tr("Les mots de passe courants (motdepasse, azerty…) sont refusés.")}</li>
            </ul>
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

const STRENGTH = [
  ["", "transparent"],
  ["Trop faible", "#ff8a7a"],
  ["Correct", "#f2c14e"],
  ["Bon", "#9cdc6f"],
  ["Très bon", "#4fd18b"],
] as const;

/** Four-segment strength meter of the sign-up password. */
function StrengthMeter({ level }: { level: number }) {
  const [label, color] = STRENGTH[level] ?? STRENGTH[0];
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8 }} aria-live="polite">
      <div style={{ display: "flex", gap: 3, flex: 1 }}>
        {[1, 2, 3, 4].map((k) => (
          <span key={k} style={{ flex: 1, height: 5, borderRadius: 3, background: k <= level ? color : "var(--line)" }} />
        ))}
      </div>
      <span className="small" style={{ minWidth: 64, color }}>
        {label ? tr(label) : ""}
      </span>
    </div>
  );
}
