import { useEffect, useState } from "react";
import Editor, { loader } from "@monaco-editor/react";
import * as monaco from "monaco-editor/esm/vs/editor/editor.api";
import "monaco-editor/esm/vs/basic-languages/python/python.contribution";
import EditorWorker from "monaco-editor/esm/vs/editor/editor.worker?worker";
import type { FilterConfig, ModelValidation, Geometry } from "../api/types";
import { api } from "../api/client";
import { JsonField } from "./ParameterEditor";
(self as unknown as { MonacoEnvironment: unknown }).MonacoEnvironment = {
  getWorker: () => new EditorWorker(),
};
loader.config({ monaco });
export default function ModelEditor({
  filter,
  onChange,
  geometry,
}: {
  filter: FilterConfig;
  geometry: Geometry;
  onChange: (filter: FilterConfig) => void;
}) {
  const [validation, setValidation] = useState<ModelValidation | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    if (!filter.model.source)
      void api
        .template()
        .then((t) =>
          onChange({ ...filter, model: { ...filter.model, source: t.source } }),
        )
        .catch((e) => setError((e as Error).message));
  }, []);
  async function validate() {
    setBusy(true);
    setError("");
    try {
      setValidation(
        await api.validateModel({
          definition: {
            id: `model-${filter.id}`,
            kind: "python",
            builtin_name: null,
            source: filter.model.source,
            params: filter.model.params,
          },
          geometry: {
            radius_a: geometry.rA,
            radius_b: geometry.rB,
            height_a: geometry.zA,
            height_diff: geometry.dh,
            reference_id: geometry.reference_id,
          },
          x0: filter.x0,
          p0: filter.P0,
        }),
      );
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="model-editor">
      <p className="help">
        高级 Python 方式：build_model(params, geometry)
        位于下方完整源码中，默认模板在末尾。
        此处修改随当前模型保存，不会改动磁盘上的示例文件。使用可信的本地代码。
      </p>
      <div className="code-editor">
        <Editor
          height="360px"
          language="python"
          value={filter.model.source ?? ""}
          onChange={(source) => {
            onChange({ ...filter, model: { ...filter.model, source } });
            setValidation(null);
          }}
          options={{
            minimap: { enabled: false },
            fontSize: 12,
            wordWrap: "on",
            scrollBeyondLastLine: false,
            automaticLayout: true,
            tabSize: 4,
            autoIndent: "none",
            formatOnPaste: false,
          }}
          onMount={(editor) => {
            editor.onDidChangeModelContent(() => {
              const model = editor.getModel();
              if (model) monaco.editor.setModelMarkers(model, "validation", []);
            });
          }}
        />
      </div>
      <JsonField
        label="模型参数（JSON）"
        value={filter.model.params}
        rows={4}
        onChange={(params) => {
          if (params && typeof params === "object" && !Array.isArray(params))
            onChange({
              ...filter,
              model: {
                ...filter.model,
                params: params as Record<string, unknown>,
              },
            });
        }}
      />
      <button
        onClick={() => void validate()}
        disabled={busy || !filter.model.source}
      >
        {busy ? "检查模型中…" : "验证方程与维数"}
      </button>
      {validation && (
        <div
          role="status"
          className={validation.valid ? "validation-good" : "field-error"}
        >
          {validation.valid
            ? `验证通过${validation.metadata?.state_names ? ` · ${validation.metadata.state_names.length} 维状态` : ""}`
            : validation.issues.map((issue, i) => (
                <p key={i}>
                  {issue.line ? `第 ${issue.line} 行：` : ""}
                  {issue.field ? `${issue.field}：` : ""}
                  {issue.message}
                </p>
              ))}
        </div>
      )}
      {error && (
        <p className="field-error" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}
