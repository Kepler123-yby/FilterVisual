import { test, expect } from "@playwright/test";
test("runs an immutable three-filter experiment and compares post-update forecasts", async ({
  page,
  request,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  const historyConfig = await (await request.get("/api/default-config")).json();
  historyConfig.name = "历史基线 B";
  historyConfig.scene.duration_s = 0.1;
  historyConfig.instances = [historyConfig.instances[0]];
  const historyJob = await (
    await request.post("/api/runs", { data: historyConfig })
  ).json();
  await expect
    .poll(
      async () =>
        (await (await request.get(`/api/runs/${historyJob.id}`)).json()).status,
    )
    .toBe("completed");
  await page.goto("/");
  await expect(page.getByLabel("A 组半径（m）")).toBeVisible();
  await page.getByLabel("A 组半径（m）").fill("0.30");
  await page.getByLabel("正弦项 1 A", { exact: true }).fill("0.8");
  await page.getByText("仿真与复现", { exact: false }).click();
  await page.getByLabel("仿真时长（s）").fill("1.2");
  await page.getByLabel("共同评估频率（Hz）").fill("20");
  await page.getByLabel("EKF 01 更新频率（Hz）").fill("25");
  await page.getByLabel("提前量 1（秒）").fill("0.1");
  await page.getByLabel("提前量 2（秒）").fill("0.3");
  await page.getByRole("button", { name: "运行实验", exact: true }).click();
  await expect(page.getByText("实验已完成", { exact: true })).toBeVisible({
    timeout: 90_000,
  });
  await expect(page.getByTestId("target-scene")).toBeVisible();
  await expect(page.getByTestId("state-plot")).toBeVisible();
  await expect(page.getByTestId("error-plot")).toBeVisible();
  await expect(page.getByTestId("forecast-plot")).toBeVisible();
  await expect(page.getByText("配置与结果一致")).toBeVisible();
  await page.getByRole("button", { name: "▶ 回放", exact: true }).click();
  await page.waitForTimeout(500);
  await page.getByRole("button", { name: "Ⅱ 暂停", exact: true }).click();
  await expect(
    page.getByTestId("state-plot").locator(".plot .main-svg").first(),
  ).toBeVisible();
  await page.screenshot({
    path: "test-results/desktop-real-run.png",
    fullPage: true,
  });
  await page.getByLabel("时间游标").press("End");
  await page.getByRole("button", { name: "当前更新的未来状态" }).click();
  await expect(page.getByText(/起点.*目标时刻/)).toBeVisible();
  await page.getByRole("button", { name: "并排比较" }).click();
  await expect(page.getByTestId("state-plot")).toHaveCount(3);
  await page.getByRole("button", { name: "叠加比较" }).click();
  await page.getByRole("button", { name: "NEES", exact: true }).click();
  await expect(page.getByText("IMM 模式概率", { exact: true })).toBeVisible();
  const exportLink = page.getByRole("link", { name: "JSON 配置与结果" });
  const href = await exportLink.getAttribute("href");
  expect(href).toBeTruthy();
  const exported = await request.get(href!);
  expect(exported.ok()).toBeTruthy();
  const json = await exported.json();
  const payload = json.result ?? json.payload ?? json;
  expect(payload.config.scene.geometry.radius_a).toBe(0.3);
  expect(payload.instances).toHaveLength(3);
  expect(payload.instances[0].forecasts.length).toBeGreaterThan(0);
  const frozen = JSON.stringify(payload.config);
  const csvHref = await page
    .getByRole("link", { name: "CSV 数值序列" })
    .getAttribute("href");
  const csvText = await (await request.get(csvHref!)).text();
  const firstCsv = csvText.split("\n")[1].split(",");
  expect(Number(firstCsv[8])).toBe(payload.instances[0].samples[0].x[0]);
  expect(Number(firstCsv[9])).toBe(payload.instances[0].samples[0].truth[0]);
  await page.getByLabel("A 组半径（m）").fill("0.31");
  await expect(page.getByText(/结果待更新/)).toBeVisible();
  const exportedAgain = await (await request.get(href!)).json();
  expect(
    JSON.stringify(
      (exportedAgain.result ?? exportedAgain.payload ?? exportedAgain).config,
    ),
  ).toBe(frozen);
  await page.getByLabel("倍率列表").fill("0.3, 1, 3");
  await page.getByRole("button", { name: "扫描 Q / R", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "复制候选到草稿" }).first(),
  ).toBeVisible({ timeout: 90_000 });
  await page.getByRole("button", { name: "复制候选到草稿" }).first().click();
  await expect(page.getByText("4 个实例", { exact: true })).toBeVisible();
  await expect(page.getByTestId("target-scene")).toBeVisible();
  await page.getByLabel("独立试验次数").fill("2");
  await page
    .getByRole("button", { name: "运行 Monte Carlo", exact: true })
    .click();
  await expect(page.getByLabel("平均统计量")).toBeVisible({ timeout: 90_000 });
  await page.getByText("实验记录", { exact: false }).click();
  await page.getByRole("button", { name: /历史基线 B/ }).first().click();
  await expect(
    page.getByRole("button", { name: "复制候选到草稿" }),
  ).toHaveCount(0);
  await expect(page.getByLabel("平均统计量")).toHaveCount(0);
  expect(errors).toEqual([]);
});
test("keeps the numerical plots available on a narrow screen", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await expect(page.getByLabel("A 组半径（m）")).toBeVisible();
  await expect(page.getByTestId("target-scene")).toBeAttached();
  await expect(page.getByTestId("state-plot")).toBeAttached();
  await expect(page.getByTestId("error-plot")).toBeAttached();
  await page.screenshot({ path: "test-results/mobile.png", fullPage: true });
});

test("validates the Python template, edits f and runs the saved source", async ({
  page,
  request,
}) => {
  const config = await (await request.get("/api/default-config")).json();
  config.name = "自定义方程验收";
  config.scene.duration_s = 0.2;
  config.instances = [config.instances[0]];
  config.scene.translation.mode = "constant";
  config.instances[0].x0[3] = 1;
  await page.goto("/");
  await expect(page.getByLabel("A 组半径（m）")).toBeVisible();
  await page
    .getByLabel("导入实验配置 JSON")
    .setInputFiles({
      name: "custom.json",
      mimeType: "application/json",
      buffer: Buffer.from(JSON.stringify(config)),
    });
  await page.getByText("预测模型与方程", { exact: true }).click();
  await page.getByLabel("模型来源").selectOption("custom");
  await page.getByRole("button", { name: "验证方程与维数" }).click();
  await expect(page.getByText(/验证通过/)).toBeVisible();
  const template = await (await request.get("/api/models/template")).json();
  const source = template.source
    .replace("y[:3] += y[3:6] * dt", "y[:3] += y[3:6] * dt * 1.1")
    .replace(
      "    def f_batch",
      "    exact_linear_prediction = False\n\n    def jacobian_f(self, x, dt, t0):\n        F = super().jacobian_f(x, dt, t0)\n        F[0,3] = F[1,4] = F[2,5] = 1.1 * dt\n        return F\n\n    def f_batch",
    );
  const editor = page.locator(".monaco-editor textarea.inputarea");
  await editor.press("ControlOrMeta+A");
  await page.keyboard.insertText(source);
  await page.getByRole("button", { name: "验证方程与维数" }).click();
  await expect(page.getByText(/验证通过/)).toBeVisible();
  await page.getByRole("button", { name: "运行实验", exact: true }).click();
  await expect(page.getByText("实验已完成", { exact: true })).toBeVisible();
  const href = await page
    .getByRole("link", { name: "JSON 配置与结果" })
    .getAttribute("href");
  const exported = await (await request.get(href!)).json();
  const saved = exported.config.models.find(
    (m: { kind: string }) => m.kind === "python",
  );
  expect(saved.source).toContain("y[:3] += y[3:6] * dt * 1.1");
  expect(saved.source).toContain("F[0,3] = F[1,4] = F[2,5] = 1.1 * dt");
  expect(saved.source).not.toBe(template.source);
  expect(exported.result.instances[0].status).toBe("completed");
  const baseline=structuredClone(exported.config);baseline.name='自定义方程对照';baseline.models.forEach((m:{kind:string;builtin_name:string|null;source:string|null})=>{m.kind='builtin';m.builtin_name='rm_cv';m.source=null;});const baselineJob=await(await request.post('/api/runs',{data:baseline})).json();await expect.poll(async()=> (await(await request.get(`/api/runs/${baselineJob.id}`)).json()).status).toBe('completed');const baselineResult=await(await request.get(`/api/runs/${baselineJob.id}/result`)).json();expect(Math.abs(exported.result.instances[0].samples.at(-1).x[0]-baselineResult.instances[0].samples.at(-1).x[0])).toBeGreaterThan(1e-8);
});

test("imports a reduced XY model and evaluates only its mapped four-state subset", async ({
  page,
  request,
}) => {
  const { readFile } = await import("node:fs/promises");
  const source = await readFile(
    new URL("../../examples/models/reduced_xy.py", import.meta.url),
    "utf8",
  );
  const config = await (await request.get("/api/default-config")).json();
  config.name = "XY 子状态验收";
  config.scene.duration_s = 0.3;
  config.scene.translation.mode = "constant";
  config.scene.rotation.terms = [
    { amplitude: 0, frequency_rad_s: 0, phase_rad: 0, offset: 0 },
  ];
  config.observation.mode = "fixed";
  config.models = [
    { id: "xy", kind: "python", builtin_name: null, source, params: {} },
  ];
  const f = config.instances[0];
  f.model_id = "xy";
  f.x0 = [0, 0, 0, 0];
  f.p0 = [
    [1, 0, 0, 0],
    [0, 1, 0, 0],
    [0, 0, 1, 0],
    [0, 0, 0, 1],
  ];
  f.imm.models.forEach((m: { model_id: string }) => (m.model_id = "xy"));
  config.instances = [f];
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/");
  await expect(page.getByLabel("A 组半径（m）")).toBeVisible();
  await page
    .getByLabel("导入实验配置 JSON")
    .setInputFiles({
      name: "xy.json",
      mimeType: "application/json",
      buffer: Buffer.from(JSON.stringify(config)),
    });
  await expect(page.getByLabel("实验名称")).toHaveValue("XY 子状态验收");
  await page.getByRole("button", { name: "运行实验", exact: true }).click();
  await expect(page.getByText("实验已完成", { exact: true })).toBeVisible();
  const href = await page
    .getByRole("link", { name: "JSON 配置与结果" })
    .getAttribute("href");
  const exported = await (await request.get(href!)).json();
  const instance = exported.result.instances[0];
  expect(instance.state_names).toEqual(["cx", "cy", "vx", "vy"]);
  expect(instance.samples[0].nees.dof).toBe(4);
  expect(instance.samples[0].physical.armor_positions).toBeNull();
  await expect(page.getByText(/部分模型未提供装甲板物理投影/)).toBeVisible();
  await page.screenshot({
    path: "test-results/reduced-xy-real-run.png",
    fullPage: true,
  });
  expect(errors).toEqual([]);
});
