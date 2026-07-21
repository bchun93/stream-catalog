import { StorageObjectPicker } from "./StorageObjectPicker";

interface Props {
  onPick: (key: string) => void;
  onCancel: () => void;
}

/** Minimal S3 browser scoped to MP4/MOV objects, for choosing a proxy to analyze. */
export function RekognitionVideoPicker({ onPick, onCancel }: Props) {
  return (
    <StorageObjectPicker
      acceptExtensions={["mp4", "mov"]}
      emptyMessage="No folders or MP4/MOV files in this folder."
      onPick={(object) => onPick(object.key)}
      onCancel={onCancel}
    />
  );
}
