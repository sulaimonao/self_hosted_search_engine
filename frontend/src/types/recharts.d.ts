import * as React from "react";

declare module "recharts" {
  export const ResponsiveContainer: React.ComponentType<Record<string, unknown>>;
  export const AreaChart: React.ComponentType<Record<string, unknown>>;
  export const Area: React.ComponentType<Record<string, unknown>>;
  export const CartesianGrid: React.ComponentType<Record<string, unknown>>;
  export const Legend: React.ComponentType<Record<string, unknown>>;
  export const Tooltip: React.ComponentType<Record<string, unknown>>;
  export const XAxis: React.ComponentType<Record<string, unknown>>;
  export const YAxis: React.ComponentType<Record<string, unknown>>;
}
