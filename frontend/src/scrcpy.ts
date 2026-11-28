/** Live phone mirror: H.264 from scrcpy-server (relayed by /ws/device/{serial}/stream), decoded with WebCodecs. */

export interface StreamSession {
  /** Stream frame size (scaled down by the server). */
  width: number;
  height: number;
  /** Phone pixels in the same orientation: taps are sent in these. */
  device_width: number;
  device_height: number;
}

export interface StreamFrame {
  key: boolean;
  /** Carries SPS/PPS: (re)configure the decoder from it. */
  config: boolean;
  pts: number;
  data: Uint8Array;
}

/** Binary message: u8 flags (1 = key, 2 = config), u64 PTS (big endian), Annex B H.264. */
export function parseFrame(buf: ArrayBuffer): StreamFrame {
  const view = new DataView(buf);
  const flags = view.getUint8(0);
  const pts = Number(view.getBigUint64(1));
  return { key: (flags & 1) !== 0, config: (flags & 2) !== 0, pts, data: new Uint8Array(buf, 9) };
}

/** WebCodecs codec string ("avc1.PPCCLL") from the SPS in an Annex B buffer; null without one. */
export function avcCodec(data: Uint8Array): string | null {
  for (let i = 0; i + 4 < data.length; i++) {
    if (data[i] !== 0 || data[i + 1] !== 0) continue;
    const start = data[i + 2] === 1 ? i + 3 : data[i + 2] === 0 && data[i + 3] === 1 ? i + 4 : -1;
    if (start < 0 || start + 3 >= data.length) continue;
    if ((data[start] & 0x1f) === 7) {
      const hex = (b: number) => b.toString(16).padStart(2, "0");
      return `avc1.${hex(data[start + 1])}${hex(data[start + 2])}${hex(data[start + 3])}`;
    }
  }
  return null;
}

export const streamSupported = (): boolean => typeof window !== "undefined" && "VideoDecoder" in window;

export interface MirrorHandlers {
  onSession: (s: StreamSession) => void;
  /** First decoded frame: the mirror works. */
  onLive: () => void;
  /** Stream unavailable or ended: switch to screenshots. */
  onFail: (reason: string) => void;
}

/** Start mirroring onto the canvas. Returns a stop function. */
export function startMirror(serial: string, canvas: HTMLCanvasElement, h: MirrorHandlers): () => void {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  const ws = new WebSocket(`${proto}://${location.host}/ws/device/${encodeURIComponent(serial)}/stream`);
  ws.binaryType = "arraybuffer";
  const ctx = canvas.getContext("2d");
  let stopped = false;
  let live = false;
  let waitKey = true;

  const fail = (reason: string) => {
    if (stopped) return;
    stop();
    h.onFail(reason);
  };

  const decoder = new VideoDecoder({
    output: (frame) => {
      if (canvas.width !== frame.displayWidth || canvas.height !== frame.displayHeight) {
        canvas.width = frame.displayWidth;
        canvas.height = frame.displayHeight;
      }
      ctx?.drawImage(frame, 0, 0);
      frame.close();
      if (!live) { live = true; h.onLive(); }
    },
    error: (e) => fail(`Lỗi giải mã: ${e.message}`),
  });

  ws.onmessage = (m) => {
    if (typeof m.data === "string") {
      const msg = JSON.parse(m.data);
      if (msg.type === "session") h.onSession(msg as StreamSession);
      else if (msg.type === "error") fail(msg.message ?? "scrcpy lỗi");
      return;
    }
    const f = parseFrame(m.data as ArrayBuffer);
    if (f.config) {
      const codec = avcCodec(f.data);
      if (!codec) return;
      // Annex B (no description): SPS/PPS travel in-band with the key frame.
      decoder.configure({ codec, optimizeForLatency: true });
      waitKey = true;
    }
    if (decoder.state !== "configured") return;
    if (waitKey && !f.key) return;
    waitKey = false;
    try {
      decoder.decode(new EncodedVideoChunk({ type: f.key ? "key" : "delta", timestamp: f.pts, data: f.data }));
    } catch (e) {
      fail(`Lỗi giải mã: ${e instanceof Error ? e.message : e}`);
    }
  };
  ws.onclose = () => fail("Mất luồng scrcpy");

  const stop = () => {
    if (stopped) return;
    stopped = true;
    ws.onclose = null;
    ws.close();
    if (decoder.state !== "closed") decoder.close();
  };
  return stop;
}
