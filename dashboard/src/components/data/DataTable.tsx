"use client";

import { memo } from "react";

interface Column<T> {
  key: string;
  header: string;
  render?: (item: T) => React.ReactNode;
  align?: "left" | "center" | "right";
  width?: string;
}

interface DataTableProps<T> {
  columns: Column<T>[];
  data: T[];
  keyExtractor: (item: T) => string | number;
  emptyMessage?: string;
  loading?: boolean;
}

function DataTableInner<T>({
  columns,
  data,
  keyExtractor,
  emptyMessage = "No data",
  loading,
}: DataTableProps<T>) {
  const alignClass = (align?: string) => {
    if (align === "right") return "text-right";
    if (align === "center") return "text-center";
    return "text-left";
  };

  return (
    <div className="overflow-x-auto rounded-lg border border-[var(--color-border)]">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-[var(--color-border)] bg-[var(--color-bg-secondary)]">
            {columns.map((col) => (
              <th
                key={col.key}
                className={`px-3 py-2 text-xs font-medium text-[var(--color-text-secondary)] ${alignClass(col.align)}`}
                style={col.width ? { width: col.width } : undefined}
                scope="col"
              >
                {col.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {loading ? (
            <tr>
              <td colSpan={columns.length} className="px-3 py-8 text-center text-[var(--color-text-tertiary)]">
                <div className="flex items-center justify-center gap-2">
                  <div className="h-4 w-4 animate-spin rounded-full border-2 border-[var(--color-accent)] border-t-transparent" />
                  Loading...
                </div>
              </td>
            </tr>
          ) : data.length === 0 ? (
            <tr>
              <td colSpan={columns.length} className="px-3 py-8 text-center text-[var(--color-text-tertiary)]">
                {emptyMessage}
              </td>
            </tr>
          ) : (
            data.map((item) => (
              <tr
                key={keyExtractor(item)}
                className="border-b border-[var(--color-border)] last:border-b-0 hover:bg-[var(--color-bg-secondary)]/50"
              >
                {columns.map((col) => (
                  <td
                    key={col.key}
                    className={`px-3 py-2 text-[var(--color-text-primary)] ${alignClass(col.align)}`}
                  >
                    {col.render ? col.render(item) : String((item as Record<string, unknown>)[col.key] ?? "")}
                  </td>
                ))}
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}

const DataTable = memo(DataTableInner) as typeof DataTableInner;
export default DataTable;
