"use client";

import { useRef, useState } from "react";
import { uploadLeads } from "@/lib/api";
import type { UploadResponse } from "@/lib/types";
import { Upload } from "lucide-react";
import clsx from "clsx";

interface Props {
  onUploaded: (res: UploadResponse) => void;
}

export function UploadForm({ onUploaded }: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleFile(file: File) {
    if (!file.name.match(/\.(csv|json)$/i)) {
      setError("Only .csv and .json files are supported.");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const res = await uploadLeads(file);
      onUploaded(res);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Upload failed");
    } finally {
      setLoading(false);
    }
  }

  function onDrop(e: React.DragEvent) {
    e.preventDefault();
    setDragging(false);
    const file = e.dataTransfer.files[0];
    if (file) handleFile(file);
  }

  function onInputChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (file) handleFile(file);
  }

  return (
    <div
      className={clsx(
        "relative rounded-xl border-2 border-dashed p-8 text-center transition-colors cursor-pointer",
        dragging ? "border-brand-500 bg-brand-50" : "border-gray-300 bg-white hover:border-brand-400"
      )}
      onClick={() => inputRef.current?.click()}
      onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
      onDragLeave={() => setDragging(false)}
      onDrop={onDrop}
    >
      <input
        ref={inputRef}
        type="file"
        accept=".csv,.json"
        className="hidden"
        onChange={onInputChange}
      />

      {loading ? (
        <div className="flex flex-col items-center gap-2">
          <div className="h-8 w-8 rounded-full border-2 border-brand-500 border-t-transparent animate-spin" />
          <p className="text-sm text-gray-500">Uploading…</p>
        </div>
      ) : (
        <div className="flex flex-col items-center gap-2">
          <Upload className="h-8 w-8 text-gray-400" />
          <p className="text-sm font-medium text-gray-700">
            Drop a <span className="text-brand-600">.csv</span> or{" "}
            <span className="text-brand-600">.json</span> file here
          </p>
          <p className="text-xs text-gray-400">or click to browse</p>
        </div>
      )}

      {error && (
        <p className="mt-3 text-xs text-red-600">{error}</p>
      )}
    </div>
  );
}
