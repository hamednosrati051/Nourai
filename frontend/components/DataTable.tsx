interface Column<T> {
  /** Column header label. */
  header: string;
  /** Desktop cell renderer. */
  render: (row: T) => React.ReactNode;
  /** Mobile card renderer for this column; defaults to header + render. */
  cardRender?: (row: T) => React.ReactNode;
  /** Hide this column's card line on mobile when true. */
  hideOnCard?: boolean;
}

interface ResponsiveTableProps<T> {
  columns: Column<T>[];
  rows: T[];
  keyOf: (row: T) => string;
  /** Accessible name for the table. */
  ariaLabel: string;
  /** Mobile card header renderer (e.g. title row). */
  cardHeader?: (row: T) => React.ReactNode;
  /** Click handler for a row (admin user detail navigation). */
  onRowClick?: (row: T) => void;
}

/**
 * Data table that becomes a card list on mobile.
 * Wide admin tables stay readable without horizontal scrolling.
 */
export function ResponsiveTable<T>({
  columns,
  rows,
  keyOf,
  ariaLabel,
  cardHeader,
  onRowClick,
}: ResponsiveTableProps<T>) {
  return (
    <>
      {/* Desktop / tablet: real table */}
      <div className="table-wrap hidden md:block">
        <table className="table" aria-label={ariaLabel}>
          <thead>
            <tr>
              {columns.map((col) => (
                <th key={col.header} scope="col">
                  {col.header}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr
                key={keyOf(row)}
                onClick={onRowClick ? () => onRowClick(row) : undefined}
                className={onRowClick ? 'cursor-pointer' : undefined}
              >
                {columns.map((col) => (
                  <td key={col.header}>{col.render(row)}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Mobile: cards */}
      <div className="flex flex-col gap-3 md:hidden" role="list" aria-label={ariaLabel}>
        {rows.map((row) => (
          <div
            key={keyOf(row)}
            role="listitem"
            onClick={onRowClick ? () => onRowClick(row) : undefined}
            className={`card !p-4 ${onRowClick ? 'cursor-pointer active:bg-neutral-50 dark:active:bg-neutral-800' : ''}`}
          >
            {cardHeader && <div className="mb-2 font-bold">{cardHeader(row)}</div>}
            <dl className="flex flex-col gap-1.5 text-sm">
              {columns
                .filter((col) => !col.hideOnCard)
                .map((col) => (
                  <div key={col.header} className="flex items-start justify-between gap-3">
                    <dt className="shrink-0 text-neutral-500 dark:text-slate-400">{col.header}</dt>
                    <dd className="text-start text-neutral-800 dark:text-slate-200">
                      {col.cardRender ? col.cardRender(row) : col.render(row)}
                    </dd>
                  </div>
                ))}
            </dl>
          </div>
        ))}
      </div>
    </>
  );
}
