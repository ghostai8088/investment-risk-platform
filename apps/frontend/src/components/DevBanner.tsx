import type { ReactElement } from "react";

/** Permanent and non-dismissable ON PURPOSE (OD-FE-1-D): the header-shim identity is
 * unverified, and nothing on this screen may look like a security boundary. */
export function DevBanner(): ReactElement {
  return (
    <div className="dev-banner" role="note">
      DEV SESSION — identity is unverified; not a security boundary until SSO (AD-007)
    </div>
  );
}
