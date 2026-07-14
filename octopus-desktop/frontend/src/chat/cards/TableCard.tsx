import { Tilt } from "../../components/Tilt";

export interface ParsedTable {
  header: string[];
  rows: string[][];
}

export function parseColumns(output: string): ParsedTable | null {
  const lines = output.split("\n").filter((l) => l.trim() !== "");
  if (lines.length < 2) return null;
  const header = lines[0].trim().split(/\s{2,}/);
  if (header.length < 2) return null;
  const rows = lines.slice(1).map((l) => l.trim().split(/\s{2,}/));
  return { header, rows };
}

export function TableCard({ action, output }: { action: string; output: string }) {
  const table = parseColumns(output);
  if (!table) return <pre className="card card-pre">{output}</pre>;
  return (
    <Tilt className="card card-table">
      <div className="card-title">{action}</div>
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              {table.header.map((h, i) => (
                <th key={i}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {table.rows.map((r, i) => (
              <tr key={i}>
                {r.map((c, j) => (
                  <td key={j}>{c}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Tilt>
  );
}
