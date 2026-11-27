import type { AppRun, DeviceInfo } from "../api";

interface Props {
  /** The two runs of one job (one per phone). */
  runs: [AppRun, AppRun];
  /** Connected phones: tell an Android from an iPhone (a run only knows its serial). */
  devices: DeviceInfo[];
  current: number;
  onSelect: (runId: number) => void;
}

const PLATFORM = { android: "Android", ios: "iPhone" } as const;

function tabLabel(run: AppRun, devices: DeviceInfo[]): string {
  const name = run.device_model ?? run.serial;
  const platform = run.platform ?? devices.find((d) => d.serial === run.serial)?.platform;
  return platform ? `${PLATFORM[platform]} · ${name}` : name;
}

/** Switches the Step 2 view between the two phones of a paired run. */
export function PairTabs({ runs, devices, current, onSelect }: Props) {
  return (
    <span className="pair-tabs" role="group" aria-label="Chọn máy">
      {runs.map((r) => (
        <button key={r.id} type="button" className={`btn ${r.id === current ? "primary" : ""}`}
          aria-pressed={r.id === current} onClick={() => onSelect(r.id)}>
          {tabLabel(r, devices)}
        </button>
      ))}
    </span>
  );
}
