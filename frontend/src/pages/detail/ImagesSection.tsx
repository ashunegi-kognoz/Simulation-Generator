import { useEffect, useState } from "react";
import { ApiError, api } from "../../api/client";
import type { SimulationImage } from "../../api/types";
import { Banner, Panel, Spinner } from "../../components/ui";

const MAX_BYTES = 5 * 1024 * 1024; // 5 MB

function readAsDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => resolve(String(r.result ?? ""));
    r.onerror = () => reject(new Error("Couldn't read the file."));
    r.readAsDataURL(file);
  });
}

export function ImagesSection({
  simulationId,
  token,
}: {
  simulationId: string;
  token: string;
}) {
  const [images, setImages] = useState<SimulationImage[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [name, setName] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [formErr, setFormErr] = useState<string | null>(null);
  const [busyName, setBusyName] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const res = await api.listImages(simulationId, token);
      setImages(res.images);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Couldn't load images.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [simulationId, token]);

  async function upload() {
    setFormErr(null);
    if (!name.trim()) return setFormErr("Give the image a name (e.g. welcome, role_brief).");
    if (!file) return setFormErr("Choose an image file.");
    if (!file.type.startsWith("image/")) return setFormErr("That file isn't an image.");
    if (file.size > MAX_BYTES) return setFormErr("Image is larger than 5 MB.");
    setUploading(true);
    try {
      const dataUrl = await readAsDataUrl(file);
      await api.addImage(simulationId, token, name.trim(), dataUrl);
      setName("");
      setFile(null);
      await load();
    } catch (e) {
      setFormErr(e instanceof ApiError ? e.message : "Upload failed.");
    } finally {
      setUploading(false);
    }
  }

  async function remove(imgName: string) {
    setBusyName(imgName);
    try {
      await api.deleteImage(simulationId, token, imgName);
      await load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Couldn't delete image.");
    } finally {
      setBusyName(null);
    }
  }

  const existingNames = new Set((images ?? []).map((i) => i.name));
  const willReplace = name.trim() !== "" && existingNames.has(name.trim());

  return (
    <div className="space-y-6">
      <Panel
        eyebrow="Simulation images"
        title="Named image slots"
        right={
          <button className="btn-ghost h-8 px-3 text-xs" onClick={() => void load()} disabled={loading}>
            Refresh
          </button>
        }
      >
        <p className="mb-4 text-sm text-muted">
          Upload background images for this simulation and give each one a name. They're stored on
          Cloudinary and served to your front-end via the images API. Add as many as you need.
        </p>

        {/* add form */}
        <div className="rounded-xl border border-line bg-canvas p-4">
          <div className="grid gap-3 sm:grid-cols-[1fr_1.4fr_auto] sm:items-end">
            <div>
              <label className="label">Image name</label>
              <input
                className="input w-full"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="welcome"
              />
            </div>
            <div>
              <label className="label">File (PNG/JPG/WebP/GIF, ≤ 5 MB)</label>
              <input
                type="file"
                accept="image/*"
                className="block w-full text-sm text-muted file:mr-3 file:rounded-lg file:border-0 file:bg-ink file:px-3 file:py-1.5 file:text-xs file:font-medium file:text-white hover:file:opacity-90"
                onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              />
            </div>
            <button className="btn-primary h-9" onClick={() => void upload()} disabled={uploading}>
              {uploading ? "Uploading…" : willReplace ? "Replace" : "Upload"}
            </button>
          </div>
          {willReplace && (
            <p className="mt-2 text-xs text-amber">
              A slot named "{name.trim()}" already exists — uploading will replace it.
            </p>
          )}
          {formErr && (
            <div className="mt-3">
              <Banner tone="error">{formErr}</Banner>
            </div>
          )}
        </div>

        {/* list */}
        <div className="mt-5">
          {loading ? (
            <Spinner label="Loading images…" />
          ) : error ? (
            <Banner tone="error" title="Couldn't load images">{error}</Banner>
          ) : !images || images.length === 0 ? (
            <Banner tone="empty">No images yet. Add one above.</Banner>
          ) : (
            <div className="grid gap-3 sm:grid-cols-2">
              {images.map((img) => (
                <div key={img.name} className="flex gap-3 rounded-xl border border-line p-3">
                  <div className="h-16 w-24 shrink-0 overflow-hidden rounded-lg border border-line bg-canvas">
                    <img src={img.url} alt={img.name} className="h-full w-full object-cover" />
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="font-medium text-ink">{img.name}</div>
                    <a
                      href={img.url}
                      target="_blank"
                      rel="noreferrer"
                      className="num block truncate text-xs text-petrol hover:underline"
                      title={img.url}
                    >
                      {img.url}
                    </a>
                    <button
                      className="mt-1.5 text-xs font-medium text-coral hover:underline disabled:opacity-50"
                      onClick={() => void remove(img.name)}
                      disabled={busyName === img.name}
                    >
                      {busyName === img.name ? "Removing…" : "Remove"}
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </Panel>
    </div>
  );
}
