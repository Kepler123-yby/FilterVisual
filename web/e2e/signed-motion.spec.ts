import { test, expect, type Page } from "@playwright/test";

async function typeSigned(page: Page, label: string, value: string) {
  const field = page.getByLabel(label, { exact: true });
  await field.fill("");
  await field.pressSequentially(value);
  await expect(field).toHaveValue(value);
  await expect(field).toHaveAttribute("aria-invalid", "false");
}

test("typed negative translation and clockwise spin reach real simulation", async ({
  page,
  request,
}) => {
  const config = await (await request.get("/api/default-config")).json();
  config.name = "负向平移与顺时针自旋验收";
  config.scene.duration_s = 0.3;
  config.scene.simulation_dt = 0.01;
  config.scene.translation.mode = "constant";
  config.scene.rotation.terms = config.scene.rotation.terms.slice(0, 1);
  config.forecast.enabled = false;
  await page.goto("/");
  await expect(page.getByLabel("A 组半径（m）")).toBeVisible();
  await page.getByLabel("导入实验配置 JSON").setInputFiles({
    name: "signed-motion.json",
    mimeType: "application/json",
    buffer: Buffer.from(JSON.stringify(config)),
  });
  const vx = page.getByLabel("速度 vx（m/s）", { exact: true });
  await vx.fill("");
  await vx.pressSequentially("-");
  await expect(vx).toHaveValue("-");
  await page.getByRole("button", { name: "运行实验", exact: true }).click();
  await expect(
    page.getByText("修正参数编辑器中的错误后再运行。"),
  ).toBeVisible();
  // Importing even the same values must discard unfinished local edits.
  await page.getByLabel("导入实验配置 JSON").setInputFiles({
    name: "signed-motion.json",
    mimeType: "application/json",
    buffer: Buffer.from(JSON.stringify(config)),
  });
  await expect(vx).toHaveValue(String(config.scene.translation.velocity_xy[0]));
  await expect(vx).toHaveAttribute("aria-invalid", "false");
  for (const [label, value] of [
    ["速度 vx（m/s）", "-1.5"],
    ["速度 vy（m/s）", "-0.25"],
    ["正弦项 1 A", "-0.2"],
    ["正弦项 1 Ω", "-1"],
    ["正弦项 1 a", "-0.3"],
    ["正弦项 1 C", "-1"],
    ["初始参考角（°）", "-115"],
  ])
    await typeSigned(page, label, value);
  await page.getByRole("button", { name: "运行实验", exact: true }).click();
  await expect(page.getByText("实验已完成", { exact: true })).toBeVisible({
    timeout: 60_000,
  });
  const href = await page
    .getByRole("link", { name: "JSON 配置与结果" })
    .getAttribute("href");
  const exported = await (await request.get(href!)).json();
  expect(exported.config.scene.translation.velocity_xy).toEqual([-1.5, -0.25]);
  expect(exported.config.scene.rotation.terms[0]).toEqual({
    amplitude: -0.2,
    frequency_rad_s: -1,
    phase_rad: -0.3,
    offset: -1,
  });
  const last = exported.result.truth.at(-1);
  expect(last.center_xy[0]).toBeCloseTo(-0.45, 8);
  expect(last.center_xy[1]).toBeCloseTo(-0.075, 8);
  expect(last.reference_yaw).toBeLessThan(
    exported.result.truth[0].reference_yaw,
  );
  expect(exported.config.scene.rotation.initial_yaw).toBeCloseTo(
    (-115 * Math.PI) / 180,
    10,
  );
  expect(
    exported.result.instances.every(
      (i: { status: string }) => i.status === "completed",
    ),
  ).toBe(true);
  await expect(
    page.getByTestId("state-plot").locator(".main-svg").first(),
  ).toBeVisible();
  await page.screenshot({
    path: "test-results/signed-motion.png",
    fullPage: true,
  });
});

for (const mode of ["random_smooth", "waypoints"] as const) {
  test(`negative ${mode} speed passes the real API`, async ({
    page,
    request,
  }) => {
    const config = await (await request.get("/api/default-config")).json();
    config.name = `负速度范围验收 ${mode}`;
    config.scene.duration_s = 0.2;
    config.scene.simulation_dt = 0.01;
    config.scene.translation.mode = mode;
    config.scene.translation.waypoints =
      mode === "waypoints" ? [{ time_s: 0, speed: 1, heading_rad: 0 }] : [];
    config.instances = config.instances.slice(0, 1);
    config.forecast.enabled = false;
    await page.goto("/");
    await expect(page.getByLabel("A 组半径（m）")).toBeVisible();
    await page.getByLabel("导入实验配置 JSON").setInputFiles({
      name: "reverse.json",
      mimeType: "application/json",
      buffer: Buffer.from(JSON.stringify(config)),
    });
    if (mode === "random_smooth") {
      await typeSigned(page, "速度下限（m/s）", "-2");
      await typeSigned(page, "速度上限（m/s）", "-0.5");
    } else await typeSigned(page, "速度（m/s）", "-2");
    await page.getByRole("button", { name: "运行实验", exact: true }).click();
    await expect(page.getByText("实验已完成", { exact: true })).toBeVisible({
      timeout: 60_000,
    });
    const href = await page
      .getByRole("link", { name: "JSON 配置与结果" })
      .getAttribute("href");
    const exported = await (await request.get(href!)).json();
    if (mode === "random_smooth") {
      expect(exported.config.scene.translation.speed_min).toBe(-2);
      expect(exported.config.scene.translation.speed_max).toBe(-0.5);
    } else {
      expect(exported.config.scene.translation.waypoints[0].speed).toBe(-2);
      expect(exported.result.truth.at(-1).center_xy[0]).toBeCloseTo(-0.4, 8);
    }
  });
}
