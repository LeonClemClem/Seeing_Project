/** Password rules of the sign-up form, as the server's (apps/api/seeing_api/passwords.py): length and
 * character kinds are checked here as the user types; common passwords are refused by the server. */

export const MIN_LENGTH = 12;

/** Number of character kinds used: lower case, upper case, digit, other. */
export function kinds(pw: string): number {
  return [/\p{Ll}/u, /\p{Lu}/u, /\d/, /[^\p{L}\d]/u].filter((re) => re.test(pw)).length;
}

export interface RuleCheck {
  length: boolean;
  kinds: boolean;
  email: boolean;
}

/** Each rule, true when followed. `email` = does not contain the part of the e-mail before "@". */
export function checkRules(pw: string, email: string): RuleCheck {
  const local = email.split("@")[0]!.trim().toLowerCase();
  return {
    length: pw.length >= MIN_LENGTH,
    kinds: kinds(pw) >= 3,
    email: local.length < 3 || !pw.toLowerCase().includes(local),
  };
}

/** Strength 0-4 for the meter: 0 = rules not followed, then by length and kinds. */
export function strength(pw: string, email: string): number {
  const c = checkRules(pw, email);
  if (!c.length || !c.kinds || !c.email) return pw ? 1 : 0;
  return Math.min(4, 2 + (pw.length >= 16 ? 1 : 0) + (kinds(pw) === 4 ? 1 : 0));
}
