// Windows(Git Bash)에서 plan이 CLI 버전 검사로 실패하면 exe를 직접 실행하고 그 경로를 _로 넘긴다: R="$(npm root -g)/@railway/cli/bin/railway.exe"; _="$(cygpath -w "$R")" "$R" config plan
import { defineRailway, github, project, service, volume } from "railway/iac";
// This repository manages only its own resources in the environment. Other
// repositories export their own partial name.
// See https://docs.railway.com/infrastructure-as-code#multi-repo-projects
export const partial = "campus-books";
export default defineRailway(() => {
  // 사진 저장용 기존 볼륨. 선언하지 않으면 plan이 /data 마운트를 떼어 버린다.
  // region·크기는 현재 Railway 값과 같게 둔다. 비우면 plan이 값을 지우려 한다.
  const photos = volume("campus-books-volume", { region: "sfo", sizeMB: 500 });

  const campusBooks = service("campus-books", {
    source: github("kim123-dev/campus-books", { branch: "main", checkSuites: false }),
    build: { buildEnvironment: "V3", builder: "DOCKERFILE", dockerfilePath: "Dockerfile" },
    healthcheck: "/health",
    healthcheckTimeout: 100,
    // railway.json과 같은 값. 나중에 railway.json을 지워도 유지되도록 명시한다.
    deploy: { restartPolicyType: "ON_FAILURE", restartPolicyMaxRetries: 10 },
    replicas: { "sfo": 1 },
    volumeMounts: { "/data": photos },
  });

  return project("helpful-victory", {
    variables: { managed: false },
    resources: [campusBooks],
  });
});
