import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const h = vi.hoisted(() => ({
  startMock: vi.fn(),
  stopMock: vi.fn(),
  cancelSpeechMock: vi.fn(),
  capturedOnSpeechEnd: undefined as (() => void) | undefined,
}));
vi.mock("./recorder", () => ({
  MicRecorder: class {
    start = (opts: { onSpeechEnd?: () => void; vad?: { silenceMs: number } }) => {
      h.capturedOnSpeechEnd = opts?.onSpeechEnd;
      return h.startMock(opts);
    };
    stop = h.stopMock;
  },
  MicRecorderError: class extends Error {},
}));

vi.mock("./tts", () => ({ cancelSpeech: h.cancelSpeechMock }));

const { startMock, stopMock, cancelSpeechMock } = h;

import { VoiceBar } from "./VoiceBar";

beforeEach(() => {
  startMock.mockReset().mockResolvedValue(undefined);
  stopMock.mockReset().mockResolvedValue("wav-b64");
  cancelSpeechMock.mockReset();
  h.capturedOnSpeechEnd = undefined;
  (window as any).go = { main: { App: { Transcribe: vi.fn().mockResolvedValue("halo dunia") } } };
});

const noop = () => {};

describe("VoiceBar hands-free", () => {
  it("klik mic memicu barge-in (cancelSpeech) dan start dengan silenceMs dari prop", async () => {
    render(<VoiceBar onTranscript={noop} jarvis onToggleJarvis={noop} vadSilenceMs={900} />);
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /mulai merekam/i }));
    });
    expect(cancelSpeechMock).toHaveBeenCalled();
    expect(startMock).toHaveBeenCalledWith(
      expect.objectContaining({ vad: expect.objectContaining({ silenceMs: 900 }) }),
    );
  });

  it("VAD onSpeechEnd mentranskripsi dan mengirim teks", async () => {
    const onTranscript = vi.fn();
    render(<VoiceBar onTranscript={onTranscript} jarvis onToggleJarvis={noop} />);
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /mulai merekam/i }));
    });
    expect(h.capturedOnSpeechEnd).toBeTypeOf("function");
    await act(async () => {
      h.capturedOnSpeechEnd?.();
    });
    await waitFor(() => expect(onTranscript).toHaveBeenCalledWith("halo dunia"));
    expect(stopMock).toHaveBeenCalled();
  });
});
