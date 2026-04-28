import { type RouteConfig, route, index } from "@react-router/dev/routes";

export default [
  index("routes/dashboard.tsx"),
  route("telemetry", "routes/telemetry.tsx"),
  route("logs", "routes/logs.tsx"),
  route("settings", "routes/settings.tsx"),
] satisfies RouteConfig;
