/** Use a small TMDB size for list/table thumbnails. */
export function posterThumbUrl(url: string): string {
  if (!url.includes("image.tmdb.org/t/p/")) {
    return url;
  }
  return url.replace(/\/t\/p\/[^/]+/, "/t/p/w92");
}
