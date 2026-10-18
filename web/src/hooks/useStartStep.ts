import { useEffect, useRef, useState } from "react";
import { get, post, upload, type DocView, type Pack, type Role } from "../api";

type Pay = { label: string; amount: string; day: number; paid: boolean };

/** State and server calls for "Add documents" (moved out of StartStep.tsx unchanged). */
export function useStartStep(onLoaded: (v: DocView) => void, aiOn: boolean) {
  const [packs, setPacks] = useState<Pack[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [files, setFiles] = useState<File[]>([]);
  const [pasted, setPasted] = useState("");
  const [manual, setManual] = useState(false);
  const input = useRef<HTMLInputElement>(null);

  useEffect(() => { get<Pack[]>("/api/samples").then(setPacks).catch(() => setPacks([])); }, []);

  async function run(label: string, fn: () => Promise<DocView>) {
    setBusy(label); setError(null);
    try { onLoaded(await fn()); } catch (e) { setError((e as Error).message); } finally { setBusy(null); }
  }

  const addFiles = (more: File[]) => setFiles((f) => [...f, ...more].slice(0, 6));
  const removeFile = (i: number) => setFiles(files.filter((_, j) => j !== i));
  const pickSample = (id: string) => run(id, () => post<DocView>("/api/documents/sample", { pack: id }));
  const readUploads = () => run("upload", () => upload(files, pasted));
  const submitManual = (facts: Record<string, string>, pays: Pay[], role: Role) =>
    run("manual", () => post<DocView>("/api/documents/manual", { facts, supplier_payments: pays, role }));

  const steps = busy === "manual"
    ? ["Checking the facts you entered", "Preparing them for review"]
    : aiOn
      ? ["Opening the documents", "Gemini is reading each document", "Checking every quoted value against the source text",
         "Running fraud and consistency checks", "Preparing the facts for your review"]
      : ["Opening the documents", "Reading them with the built-in parser", "Running fraud and consistency checks",
         "Preparing the facts for your review"];

  return { packs, busy, error, files, pasted, setPasted, manual, setManual, input, addFiles, removeFile, pickSample, readUploads, submitManual, steps };
}
