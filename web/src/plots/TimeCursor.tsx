import { useEffect, useState } from "react";
import { Field, formatNumber } from "../app/components";
export default function TimeCursor({
  time,
  duration,
  onChange,
  ready,
}: {
  time: number;
  duration: number;
  onChange: (t: number) => void;
  ready: boolean;
}) {
  const [playing, setPlaying] = useState(false),
    [speed, setSpeed] = useState(1),
    [fps, setFps] = useState(15);
  useEffect(() => {
    if (!playing || !ready) return;
    let old = performance.now();
    const timer = setInterval(() => {
      const now = performance.now(),
        next = time + ((now - old) / 1000) * speed;
      old = now;
      if (next >= duration) {
        onChange(duration);
        setPlaying(false);
      } else onChange(next);
    }, 1000 / fps);
    return () => clearInterval(timer);
  }, [playing, ready, time, duration, onChange, speed, fps]);
  return (
    <div className="time-cursor">
      <div className="playback-controls">
        <button
          disabled={!ready}
          className="primary"
          onClick={() => {
            if (time >= duration) onChange(0);
            setPlaying(!playing);
          }}
        >
          {playing ? "Ⅱ 暂停" : "▶ 回放"}
        </button>
        <button
          disabled={!ready}
          onClick={() => {
            onChange(0);
            setPlaying(false);
          }}
        >
          回到起点
        </button>
        <span className="current-time">t = {formatNumber(time, 2)} s</span>
        <Field label="速度">
          <select
            value={speed}
            onChange={(e) => setSpeed(Number(e.target.value))}
          >
            {[0.25, 0.5, 1, 2, 4].map((v) => (
              <option key={v} value={v}>
                {v}×
              </option>
            ))}
          </select>
        </Field>
        <Field label="回放帧率">
          <select value={fps} onChange={(e) => setFps(Number(e.target.value))}>
            {[5, 15, 30].map((v) => (
              <option key={v} value={v}>
                {v} fps
              </option>
            ))}
          </select>
        </Field>
      </div>
      <div className="timeline">
        <span>0 s</span>
        <input
          aria-label="时间游标"
          type="range"
          min={0}
          max={duration}
          step={0.001}
          value={Math.min(time, duration)}
          disabled={!ready}
          onChange={(e) => {
            setPlaying(false);
            onChange(Number(e.target.value));
          }}
        />
        <span>{formatNumber(duration, 1)} s</span>
      </div>
    </div>
  );
}
