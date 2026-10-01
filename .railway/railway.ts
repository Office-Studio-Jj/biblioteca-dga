import { defineRailway, project, service, volume } from "railway/iac";

// This repository manages only its own resources in the environment. Other
// repositories export their own partial name.
// See https://docs.railway.com/infrastructure-as-code#multi-repo-projects
export const partial = "biblioteca-dga";

// Generado con `railway config migrate --apply` (01-10-2026) y completado con lo que
// railway.toml declaraba y la migración no trajo: builder Dockerfile, reinicio ON_FAILURE x3
// y el volumen /data (usuarios, contraseñas bcrypt, solicitudes, historial: Ley 172-13).
// Revisar siempre con `railway config plan` antes de `railway config apply`.
export default defineRailway(() => {
  const biblioteca_dga = service("biblioteca-dga", {
    start: "sh -c 'PYTHONIOENCODING=utf-8 PYTHONUTF8=1 gunicorn --bind 0.0.0.0:${PORT:-8080} --timeout 60 --workers 1 --worker-class gthread --threads 4 --preload server:app'",
    build: { builder: "DOCKERFILE", dockerfilePath: "Dockerfile" },
    deploy: { restartPolicyType: "ON_FAILURE", restartPolicyMaxRetries: 3 },
    volumeMounts: { "/data": volume("biblioteca-dga-volume") },
  });
  return project("invigorating-optimism", {
    resources: [biblioteca_dga],
  });
});
