"use client";

type FacetEntry = [string, number];

type FacetRecord = Record<string, FacetEntry[]>;

interface FacetRailProps {
  facets: FacetRecord | undefined;
}

export default function FacetRail({ facets }: FacetRailProps): JSX.Element {
  return (
    <aside className="w-64 p-3 border rounded-2xl space-y-3">
      {Object.entries(facets ?? {}).map(([key, values]) => (
        <div key={key}>
          <div className="font-medium text-sm mb-1">{key}</div>
          <div className="space-y-1">
            {values.slice(0, 10).map(([value, count]) => (
              <div key={value} className="flex justify-between text-sm">
                <span className="truncate" title={value}>
                  {value}
                </span>
                <span>{count}</span>
              </div>
            ))}
          </div>
        </div>
      ))}
    </aside>
  );
}
