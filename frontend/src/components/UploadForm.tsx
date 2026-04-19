"use client";

import { useRef, useState } from "react";
import { uploadLeads } from "@/lib/api";
import type { UploadResponse } from "@/lib/types";
import { CheckCircle, Upload } from "lucide-react";
import clsx from "clsx";

interface Props {
  onUploaded: (res: UploadResponse) => void;
  isProcessing?: boolean;
  processingCount?: number;
}

export function UploadForm({ onUploaded, isProcessing = false, processingCount }: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadDone, setUploadDone] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleFile(file: File) {
    if (!file.name.match(/\.(csv|json)$/i)) {
      setError("Only .csv and .json files are supported.");
      return;
    }
    setUploading(true);
    setUploadDone(false);
    setError(null);
    try {
      const res = await uploadLeads(file);
      setUploadDone(true);
      onUploaded(res);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Upload failed");
    } finally {
      setUploading(false);
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
    // reset so the same file can be re-uploaded
    e.target.value = "";
  }

  const busy = uploading || isProcessing;

  return (
    <div
      className={clsx(
        "relative rounded-xl border-2 border-dashed p-8 text-center transition-colors",
        busy ? "cursor-default" : "cursor-pointer",
        dragging
          ? "border-brand-500 bg-brand-50"
          : busy
          ? "border-gray-200 bg-gray-50"
          : "border-gray-300 bg-white hover:border-brand-400"
      )}
      onClick={() => { if (!busy) inputRef.current?.click(); }}
      onDragOver={(e) => { e.preventDefault(); if (!busy) setDragging(true); }}
      onDragLeave={() => setDragging(false)}
      onDrop={(e) => { if (!busy) onDrop(e); }}
    >
      <input
        ref={inputRef}
        type="file"
        accept=".csv,.json"
        className="hidden"
        onChange={onInputChange}
      />

      {/* ── State 1: Uploading ── */}
      {uploading && (
        <div className="flex flex-col items-center gap-3">
          <div className="relative h-10 w-10">
            <div className="absolute inset-0 rounded-full border-2 border-brand-100" />
            <div className="absolute inset-0 rounded-full border-2 border-brand-500 border-t-transparent animate-spin" />
          </div>
          <div>
            <p className="text-sm font-medium text-gray-700">Uploading file…</p>
            <p className="text-xs text-gray-400 mt-0.5">Sending to the agent pipeline</p>
          </div>
        </div>
      )}

      {/* ── State 2: Processing ── */}
      {!uploading && isProcessing && (
        <div className="flex flex-col items-center gap-3">
          <div className="relative h-10 w-10">
            <div className="absolute inset-0 rounded-full border-2 border-brand-100" />
            <div className="absolute inset-0 rounded-full border-2 border-brand-500 border-t-transparent animate-spin" />
            {/* Inner pulsing dot */}
            <div className="absolute inset-2 rounded-full bg-brand-500/20 animate-pulse" />
          </div>
          <div>
            <p className="text-sm font-medium text-gray-700">
              Processing{processingCount ? ` ${processingCount} lead${processingCount !== 1 ? "s" : ""}` : ""}…
            </p>
            <p className="text-xs text-gray-400 mt-0.5">
              AI agent is enriching and scoring — check Processing Jobs below
            </p>
          </div>
        </div>
      )}

      {/* ── State 3: Idle (default) ── */}
      {!uploading && !isProcessing && (
        <div className="flex flex-col items-center gap-2">
          {uploadDone
            ? <CheckCircle className="h-8 w-8 text-green-500" />
            : <Upload className="h-8 w-8 text-gray-400" />
          }
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
