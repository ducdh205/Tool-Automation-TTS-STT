import { avcCodec, parseFrame } from "./scrcpy";

describe("scrcpy stream", () => {
  it("parses the binary frame header", () => {
    const buf = new Uint8Array([3, 0, 0, 0, 0, 0, 0, 0x04, 0xd2, 0, 0, 0, 1, 0x65]).buffer;
    const f = parseFrame(buf);
    expect(f).toMatchObject({ key: true, config: true, pts: 1234 });
    expect(Array.from(f.data)).toEqual([0, 0, 0, 1, 0x65]);
    expect(parseFrame(new Uint8Array([0, 0, 0, 0, 0, 0, 0, 0, 1, 9]).buffer)).toMatchObject({ key: false, config: false });
  });

  it("reads the codec string from the SPS", () => {
    // SPS (type 7) High profile 0x64, constraints 0x00, level 4.0 (0x28), then a PPS
    const data = new Uint8Array([0, 0, 0, 1, 0x67, 0x64, 0x00, 0x28, 0xac, 0, 0, 1, 0x68, 0xee]);
    expect(avcCodec(data)).toBe("avc1.640028");
    expect(avcCodec(new Uint8Array([0, 0, 1, 0x65, 1, 2, 3]))).toBeNull();
  });
});
