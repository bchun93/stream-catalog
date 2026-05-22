/** Use a small TMDB size for list/table thumbnails. */
export function posterThumbUrl(url: string): string {
  if (url.includes("image.tmdb.org/t/p/")) {
    return url.replace(/\/t\/p\/w\d+/, "/t/p/w92");
  }
  return url;
}
