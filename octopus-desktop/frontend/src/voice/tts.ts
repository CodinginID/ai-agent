export async function speak(text: string): Promise<void> {
  const b64 = await window.go.main.App.Speak(text);
  const bytes = Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
  const url = URL.createObjectURL(new Blob([bytes], { type: "audio/wav" }));
  const audio = new Audio(url);
  await audio.play().finally(() => URL.revokeObjectURL(url));
}
