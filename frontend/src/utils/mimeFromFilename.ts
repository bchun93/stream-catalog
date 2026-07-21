/** Best-effort MIME guess from filename extension for asset registration. */
export function mimeFromFilename(filename: string): string {
  const ext = filename.split(".").pop()?.toLowerCase() ?? "";
  const map: Record<string, string> = {
    jpg: "image/jpeg",
    jpeg: "image/jpeg",
    png: "image/png",
    gif: "image/gif",
    webp: "image/webp",
    svg: "image/svg+xml",
    bmp: "image/bmp",
    mp4: "video/mp4",
    mov: "video/quicktime",
    m4v: "video/x-m4v",
    mkv: "video/x-matroska",
    webm: "video/webm",
    mp3: "audio/mpeg",
    wav: "audio/wav",
    aac: "audio/aac",
    m4a: "audio/mp4",
    srt: "application/x-subrip",
    vtt: "text/vtt",
    ass: "text/x-ssa",
  };
  return map[ext] ?? "";
}
