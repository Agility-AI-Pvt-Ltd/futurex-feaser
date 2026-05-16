"use client";

import { useCallback, useEffect, useState } from "react";
import { useAuthStore } from "@/app/stores/authStore";
import {
  FileText,
  UploadCloud,
  CheckCircle2,
  Loader2,
  X,
  File,
  Settings,
  Plus,
} from "lucide-react";

interface TranscriptMetadata {
  course_name: string;
  instructor_name: string;
  session_date: string;
  description: string;
  tags: string;
}

interface TranscriptAsset {
  id: number;
  session_name: string;
  source_name: string;
  file_name: string;
  chunks_indexed: number;
  created_at: string;
  metadata_entry?: TranscriptMetadata;
}

export default function AdminLecturebotPage() {
  const getToken = useAuthStore((s) => s.getToken);
  const [transcripts, setTranscripts] = useState<TranscriptAsset[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  // Form state
  const [editingId, setEditingId] = useState<number | null>(null);
  const [sessionName, setSessionName] = useState("");
  const [sourceName, setSourceName] = useState("");
  const [courseName, setCourseName] = useState("");
  const [instructorName, setInstructorName] = useState("");
  const [sessionDate, setSessionDate] = useState("");
  const [description, setDescription] = useState("");
  const [tags, setTags] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const authHeaders = useCallback((): HeadersInit => {
    const token = getToken();
    return token ? { Authorization: `Bearer ${token}` } : {};
  }, [getToken]);

  const loadTranscripts = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch("/api/classcatchup/transcripts", {
        headers: authHeaders(),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "Failed to load transcripts");
      setTranscripts(Array.isArray(data) ? data : []);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }, [authHeaders]);

  useEffect(() => {
    const timeoutId = window.setTimeout(() => {
      void loadTranscripts();
    }, 0);
    return () => window.clearTimeout(timeoutId);
  }, [loadTranscripts]);

  function handleSelect(t: TranscriptAsset) {
    setError(null);
    setSuccess(null);
    setEditingId(t.id);
    setSessionName(t.session_name || "");
    setSourceName(t.source_name || "");
    setCourseName(t.metadata_entry?.course_name || "");
    setInstructorName(t.metadata_entry?.instructor_name || "");
    setSessionDate(t.metadata_entry?.session_date || "");
    setDescription(t.metadata_entry?.description || "");
    setTags(t.metadata_entry?.tags || "");
    setFile(null);
  }

  function handleNew(options: { preserveStatus?: boolean } = {}) {
    if (!options.preserveStatus) {
      setError(null);
      setSuccess(null);
    }
    setEditingId(null);
    setSessionName("");
    setSourceName("");
    setCourseName("");
    setInstructorName("");
    setSessionDate("");
    setDescription("");
    setTags("");
    setFile(null);
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    setSuccess(null);

    try {
      if (editingId) {
        // PATCH update
        const payload = {
          session_name: sessionName,
          source_name: sourceName,
          course_name: courseName,
          instructor_name: instructorName,
          session_date: sessionDate,
          description,
          tags,
        };
        const res = await fetch(`/api/classcatchup/transcripts/${editingId}`, {
          method: "PATCH",
          headers: {
            "Content-Type": "application/json",
            ...authHeaders(),
          },
          body: JSON.stringify(payload),
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || "Failed to update metadata");
        setSuccess("Metadata updated successfully (no re-indexing).");
      } else {
        // POST upload
        if (!file) throw new Error("A transcript file (.txt or .vtt) is required.");
        const fd = new FormData();
        fd.append("file", file);
        fd.append("session_name", sessionName);
        if (sourceName) fd.append("source_name", sourceName);
        if (courseName) fd.append("course_name", courseName);
        if (instructorName) fd.append("instructor_name", instructorName);
        if (sessionDate) fd.append("session_date", sessionDate);
        if (description) fd.append("description", description);
        if (tags) fd.append("tags", tags);

        const res = await fetch("/api/classcatchup/upload", {
          method: "POST",
          headers: authHeaders(), // do not set Content-Type, browser will set boundary automatically
          body: fd,
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || "Failed to upload and index");
        setSuccess("Transcript uploaded and indexed successfully!");
        handleNew({ preserveStatus: true }); // Reset form without hiding success.
      }
      await loadTranscripts();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="flex h-[calc(100vh-80px)] gap-6 p-6 font-sans">
      {/* ── Left List ── */}
      <div className="flex w-1/3 min-w-[320px] flex-col overflow-hidden rounded-lg border border-[rgba(212,180,104,0.4)] bg-white dark:bg-[rgba(5,18,11,0.95)] shadow-sm dark:shadow-[0_18px_40px_rgba(0,0,0,0.7)]">
        <div className="border-b border-[rgba(212,180,104,0.15)] p-4 flex items-center justify-between">
          <h2 className="text-xs font-semibold uppercase tracking-[0.22em] text-[#e3c777]">Uploaded Transcripts</h2>
          <button
            type="button"
            onClick={handleNew}
            className="rounded border border-[rgba(212,180,104,0.4)] bg-[rgba(18,55,36,0.7)] p-1.5 text-[#e3c777] transition hover:border-[rgba(227,199,119,0.8)]"
          >
            <Plus size={14} />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto p-2">
          {loading ? (
            <div className="flex justify-center p-8 text-[#e3c777]"><Loader2 className="animate-spin" /></div>
          ) : transcripts.length === 0 ? (
            <div className="p-8 text-center text-xs text-stone-600 dark:text-white/40">No transcripts found.</div>
          ) : (
            <div className="space-y-1">
              {transcripts.map((t) => (
                <button
                  key={t.id}
                  onClick={() => handleSelect(t)}
                  className={`w-full rounded-lg border px-3 py-3 text-left transition ${
                    editingId === t.id
                      ? "border-[rgba(212,180,104,0.4)] bg-[rgba(212,180,104,0.1)]"
                      : "border-transparent hover:bg-stone-50 dark:hover:bg-white/5"
                  }`}
                >
                  <p className="text-[13px] font-medium text-stone-900 dark:text-white/90">{t.session_name}</p>
                  <p className="mt-1 truncate text-[11px] text-stone-600 dark:text-white/50">{t.source_name || t.file_name}</p>
                  <div className="mt-1.5 flex gap-2 text-[10px] text-stone-500 dark:text-white/30">
                    <span>{t.chunks_indexed} chunks</span>
                    <span>·</span>
                    <span>{new Date(t.created_at).toLocaleDateString()}</span>
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* ── Right Form ── */}
      <div className="flex-1 overflow-y-auto rounded-lg border border-[rgba(212,180,104,0.4)] bg-white dark:bg-[rgba(5,18,11,0.95)] p-6 shadow-sm dark:shadow-[0_18px_40px_rgba(0,0,0,0.7)]">
        <div className="flex items-center gap-2 text-[#e3c777]">
          <FileText size={18} />
          <h2 className="text-lg font-semibold">
            {editingId ? "Edit Transcript Metadata" : "Upload New Transcript"}
          </h2>
        </div>

        {error && (
          <div className="mt-4 flex items-center justify-between rounded border border-red-500/30 bg-red-900/20 p-3 text-[11px] text-red-300">
            <span>{error}</span>
            <button onClick={() => setError(null)}><X size={14} /></button>
          </div>
        )}

        {success && (
          <div className="mt-4 flex items-center justify-between rounded border border-green-500/30 bg-green-900/20 p-3 text-[11px] text-green-300">
            <div className="flex items-center gap-2">
              <CheckCircle2 size={14} />
              <span>{success}</span>
            </div>
            <button onClick={() => setSuccess(null)}><X size={14} /></button>
          </div>
        )}

        <form onSubmit={handleSubmit} className="mt-6 max-w-xl space-y-4">
          <div>
            <label className="mb-1 block text-[10px] font-semibold uppercase tracking-[0.2em] text-stone-600 dark:text-white/50">
              Session folder, e.g. session1
            </label>
            <input
              required
              value={sessionName}
              onChange={(e) => setSessionName(e.target.value)}
              placeholder="Session 1"
              className="w-full rounded border border-[rgba(212,180,104,0.25)] bg-white dark:bg-[rgba(5,18,11,0.9)] px-3 py-2 text-xs text-stone-900 outline-none dark:text-white focus:border-[rgba(227,199,119,0.7)]"
            />
          </div>

          <div>
            <label className="mb-1 block text-[10px] font-semibold uppercase tracking-[0.2em] text-stone-600 dark:text-white/50">
              Transcript title
            </label>
            <input
              value={sourceName}
              onChange={(e) => setSourceName(e.target.value)}
              placeholder="Introduction to Calculus"
              className="w-full rounded border border-[rgba(212,180,104,0.25)] bg-white dark:bg-[rgba(5,18,11,0.9)] px-3 py-2 text-xs text-stone-900 outline-none dark:text-white focus:border-[rgba(227,199,119,0.7)]"
            />
          </div>

          <div>
            <label className="mb-1 block text-[10px] font-semibold uppercase tracking-[0.2em] text-stone-600 dark:text-white/50">
              Course or module name
            </label>
            <input
              value={courseName}
              onChange={(e) => setCourseName(e.target.value)}
              placeholder="Math 101"
              className="w-full rounded border border-[rgba(212,180,104,0.25)] bg-white dark:bg-[rgba(5,18,11,0.9)] px-3 py-2 text-xs text-stone-900 outline-none dark:text-white focus:border-[rgba(227,199,119,0.7)]"
            />
          </div>

          <div>
            <label className="mb-1 block text-[10px] font-semibold uppercase tracking-[0.2em] text-stone-600 dark:text-white/50">
              Instructor or speaker
            </label>
            <input
              value={instructorName}
              onChange={(e) => setInstructorName(e.target.value)}
              placeholder="Dr. Smith"
              className="w-full rounded border border-[rgba(212,180,104,0.25)] bg-white dark:bg-[rgba(5,18,11,0.9)] px-3 py-2 text-xs text-stone-900 outline-none dark:text-white focus:border-[rgba(227,199,119,0.7)]"
            />
          </div>

          <div>
            <label className="mb-1 block text-[10px] font-semibold uppercase tracking-[0.2em] text-stone-600 dark:text-white/50">
              Session Date
            </label>
            <div className="relative">
              <input
                type="date"
                value={sessionDate}
                onChange={(e) => setSessionDate(e.target.value)}
                className="w-full rounded border border-[rgba(212,180,104,0.25)] bg-white dark:bg-[rgba(5,18,11,0.9)] px-3 py-2 text-xs text-stone-900 outline-none dark:text-white focus:border-[rgba(227,199,119,0.7)] [&::-webkit-calendar-picker-indicator]:opacity-50"
              />
            </div>
          </div>

          <div>
            <label className="mb-1 block text-[10px] font-semibold uppercase tracking-[0.2em] text-stone-600 dark:text-white/50">
              Short description
            </label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Overview of derivatives..."
              rows={3}
              className="w-full rounded border border-[rgba(212,180,104,0.25)] bg-white dark:bg-[rgba(5,18,11,0.9)] px-3 py-2 text-xs text-stone-900 outline-none resize-none dark:text-white focus:border-[rgba(227,199,119,0.7)]"
            />
          </div>

          <div>
            <label className="mb-1 block text-[10px] font-semibold uppercase tracking-[0.2em] text-stone-600 dark:text-white/50">
              Tags (comma separated)
            </label>
            <input
              value={tags}
              onChange={(e) => setTags(e.target.value)}
              placeholder="calculus, math, intro"
              className="w-full rounded border border-[rgba(212,180,104,0.25)] bg-white dark:bg-[rgba(5,18,11,0.9)] px-3 py-2 text-xs text-stone-900 outline-none dark:text-white focus:border-[rgba(227,199,119,0.7)]"
            />
          </div>

          {/* File Upload (Hidden when editing) */}
          {!editingId && (
            <div className="mt-6">
              <label className="mb-1 block text-[10px] font-semibold uppercase tracking-[0.2em] text-stone-600 dark:text-white/50">
                Transcript File
              </label>
              <div className="relative mt-2 flex cursor-pointer flex-col items-center justify-center rounded border border-dashed border-[rgba(212,180,104,0.4)] bg-white dark:bg-[rgba(5,18,11,0.5)] py-8 text-center transition hover:border-[rgba(227,199,119,0.8)] dark:hover:bg-[rgba(212,180,104,0.05)]">
                <UploadCloud size={24} className="mb-3 text-[#e3c777]/60" />
                <p className="text-[12px] font-medium text-stone-700 dark:text-white/80">
                  {file ? file.name : "Drop .txt or .vtt, or click to browse"}
                </p>
                <input
                  type="file"
                  accept=".txt,.vtt"
                  required
                  onChange={(e) => setFile(e.target.files?.[0] || null)}
                  className="absolute inset-0 cursor-pointer opacity-0"
                />
              </div>
            </div>
          )}

          <div className="pt-4">
            <button
              type="submit"
              disabled={submitting || (!editingId && !file)}
              className="flex w-full items-center justify-center gap-2 rounded border border-[rgba(212,180,104,0.6)] bg-emerald-50 dark:bg-[rgba(18,55,36,0.95)] px-4 py-2.5 text-[11px] font-semibold uppercase tracking-[0.2em] text-[#e3c777] shadow-[0_0_14px_rgba(227,199,119,0.3)] transition hover:border-[rgba(227,199,119,0.95)] disabled:cursor-not-allowed disabled:opacity-50"
            >
              {submitting ? (
                <Loader2 size={16} className="animate-spin" />
              ) : editingId ? (
                <Settings size={14} />
              ) : (
                <UploadCloud size={14} />
              )}
              {editingId ? "Update Metadata" : "Upload & Index"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
