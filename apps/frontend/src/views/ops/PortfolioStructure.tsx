import { useState } from "react";
import type { ReactElement } from "react";

import { useApiGet } from "../../api/useApiGet";
import { verbatim } from "../../api/format";
import { Pane } from "../../components/Pane";
import type { components } from "../../api/generated/api-types";
import type { Session } from "../../session";

type TreeNode = components["schemas"]["TreeNodeAsOfOut"];

/** STRUCT-3 (REQ-PPM-001): the Portfolio Structure screen — the hierarchy entity's FIRST read
 * surface, with the as-of toggle. The tree is resolved from the entity's OWN version history
 * (ENT-076) by timestamp, no run or snapshot in scope: pick a past instant and the screen shows
 * the tree AS IT WAS — a re-parent or rename after that instant is invisible to it. */
export function PortfolioStructure({ session }: { session: Session }): ReactElement {
  const [asOf, setAsOf] = useState<string>("");
  const at = asOf === "" ? new Date().toISOString() : new Date(asOf).toISOString();
  const tree = useApiGet<TreeNode[]>(
    `/portfolios/tree-as-of?at=${encodeURIComponent(at)}`,
    session,
  );

  return (
    <section>
      <h2>Portfolio structure</h2>
      <p className="prov-line">
        The tree as recorded by the hierarchy&apos;s own version history — pick a past instant and
        the screen shows the tree AS IT WAS then.
      </p>
      <label>
        As of <input type="datetime-local" value={asOf} onChange={(e) => setAsOf(e.target.value)} />
      </label>{" "}
      {asOf !== "" && (
        <button type="button" onClick={() => setAsOf("")}>
          Back to now
        </button>
      )}
      <Pane
        state={tree}
        requires="portfolio.view"
        empty={<p className="state">No hierarchy exists at this instant.</p>}
      >
        {(nodes) => <TreeTable nodes={nodes} />}
      </Pane>
    </section>
  );
}

function TreeTable({ nodes }: { nodes: TreeNode[] }): ReactElement {
  if (nodes.length === 0) {
    return <p className="state">No hierarchy exists at this instant.</p>;
  }
  const byParent = new Map<string | null, TreeNode[]>();
  for (const n of nodes) {
    const key = n.parent_portfolio_id ?? null;
    byParent.set(key, [...(byParent.get(key) ?? []), n]);
  }
  const known = new Set(nodes.map((n) => n.portfolio_id));
  // Roots: parentless nodes AND nodes whose parent is outside the as-of view (created later).
  const roots = nodes.filter(
    (n) => n.parent_portfolio_id === null || !known.has(n.parent_portfolio_id ?? ""),
  );
  const rows: { node: TreeNode; depth: number }[] = [];
  const walk = (node: TreeNode, depth: number, seen: Set<string>) => {
    if (seen.has(node.portfolio_id)) return; // cycle-safe, mirroring the binder's guard
    seen.add(node.portfolio_id);
    rows.push({ node, depth });
    for (const child of byParent.get(node.portfolio_id) ?? []) {
      walk(child, depth + 1, seen);
    }
  };
  const seen = new Set<string>();
  for (const root of roots) walk(root, 0, seen);

  return (
    <table>
      <thead>
        <tr>
          <th>Node</th>
          <th>Type</th>
          {/* Wave-18 close (K27): the DP-11 declaration that now governs run refusals —
              blank means INHERIT the parent's (an undeclared ROOT refuses at run time). */}
          <th>Reporting ccy</th>
          <th>Status</th>
          <th>Version</th>
          <th>Effective</th>
        </tr>
      </thead>
      <tbody>
        {rows.map(({ node, depth }) => (
          <tr key={node.portfolio_id}>
            <td style={{ paddingLeft: `${depth * 1.5}rem` }}>{verbatim(node.name)}</td>
            <td>{verbatim(node.node_type)}</td>
            <td className="mono">{verbatim(node.base_currency_code)}</td>
            <td>{verbatim(node.status)}</td>
            <td className="mono">{node.record_version}</td>
            <td className="mono">{node.effective_at}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
