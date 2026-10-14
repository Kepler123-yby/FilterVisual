import { useRef } from "react";
import type { ExperimentConfig } from "../api/types";
import { fromWireConfig, toWireConfig } from "../api/adapter";
import type { WireConfig } from "../api/adapter";
import { validateDraft } from "./validation";
export function readExperimentJson(text: string): ExperimentConfig {
  const parsed = JSON.parse(text);
  const data = parsed.config ?? parsed.payload?.config ?? parsed;
  if (
    data.schema_version !== 1 ||
    !data.scene ||
    !Array.isArray(data.instances)
  )
    throw new Error("需要 schema_version=1 的实验配置或结果导出 JSON。");
  const config = fromWireConfig(data as WireConfig),
    issues = validateDraft(config);
  if (issues.length) throw new Error(issues.join("；"));
  return config;
}
export default function ConfigFiles({
  config,
  onChange,
  onError,
}: {
  config: ExperimentConfig;
  onChange: (c: ExperimentConfig) => void;
  onError: (message: string) => void;
}) {
  const input = useRef<HTMLInputElement>(null);
  async function upload(file?: File) {
    if (!file) return;
    try {
      onChange(readExperimentJson(await file.text()));
      onError("");
    } catch (e) {
      onError(`配置未导入：${(e as Error).message}`);
    }
    if (input.current) input.current.value = "";
  }
  function download() {
    const url = URL.createObjectURL(
      new Blob([JSON.stringify(toWireConfig(config), null, 2)], {
        type: "application/json",
      }),
    );
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = "filtervisual-experiment.json";
    anchor.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  return (
    <div className="config-files">
      <input
        ref={input}
        type="file"
        accept=".json,application/json"
        className="visually-hidden"
        aria-label="导入实验配置 JSON"
        onChange={(e) => void upload(e.target.files?.[0])}
      />
      <button onClick={() => input.current?.click()}>导入配置</button>
      <button onClick={download}>保存配置</button>
    </div>
  );
}
