import { defineRailway, github, preserve, project, service, volume } from "railway/iac";

// This repository manages only its own resources in the environment. Other
// repositories export their own partial name.
// See https://docs.railway.com/infrastructure-as-code#multi-repo-projects
export const partial = "biblioteca-dga";

// Generado con `railway config migrate --apply` (01-10-2026) y completado con lo que el
// servicio ya tiene en producción, para que `railway config plan` no borre nada:
// - source: repo de GitHub (sin él se pierde el auto-deploy al hacer push a main)
// - variables: preserve() conserva el valor que Railway ya guarda (las claves nunca van aquí)
// - volumen /data en us-west2, 5000 MB (usuarios y contraseñas: Ley 172-13)
// Revisar siempre con `railway config plan` antes de `railway config apply`.
export default defineRailway(() => {
  const biblioteca_dga = service("biblioteca-dga", {
    source: github("Office-Studio-Jj/biblioteca-dga", { branch: "main" }),
    start: "sh -c 'PYTHONIOENCODING=utf-8 PYTHONUTF8=1 gunicorn --bind 0.0.0.0:${PORT:-8080} --timeout 60 --workers 1 --worker-class gthread --threads 4 --preload server:app'",
    build: { builder: "DOCKERFILE", dockerfilePath: "Dockerfile" },
    deploy: { restartPolicyType: "ON_FAILURE", restartPolicyMaxRetries: 3 },
    env: {
      ANTHROPIC_API_KEY: preserve(),
      NOTION_DB_CLOPAS: preserve(),
    },
    volumeMounts: {
      "/data": volume("biblioteca-dga-volume", { region: "us-west2", sizeMB: 5000 }),
    },
  });
  return project("invigorating-optimism", {
    resources: [biblioteca_dga],
  });
});
