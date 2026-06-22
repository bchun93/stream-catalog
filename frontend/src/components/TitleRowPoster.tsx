import { useState } from "react";
import { posterThumbUrl } from "../utils/posterThumb";

interface TitleRowPosterProps {
  url: string;
}

export function TitleRowPoster({ url }: TitleRowPosterProps) {
  const [failed, setFailed] = useState(false);

  if (failed) {
    return (
      <div className="title-row-poster title-row-poster-fallback" aria-hidden>
        —
      </div>
    );
  }

  return (
    <img
      src={posterThumbUrl(url)}
      alt=""
      className="title-row-poster"
      loading="lazy"
      onError={() => setFailed(true)}
    />
  );
}
