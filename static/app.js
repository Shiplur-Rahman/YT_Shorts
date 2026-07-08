const $ = (sel) => document.querySelector(sel);

const sections = {
  upload: $("#upload-section"),
  job: $("#job-section"),
  error: $("#error-section"),
  results: $("#results-section"),
};

function show(name) {
  for (const [key, el] of Object.entries(sections)) {
    el.classList.toggle("hidden", key !== name);
  }
}

// --- Upload ---

const dropzone = $("#dropzone");
const fileInput = $("#file-input");

dropzone.addEventListener("click", () => fileInput.click());
fileInput.addEventListener("change", () => {
  if (fileInput.files.length) uploadFile(fileInput.files[0]);
});
dropzone.addEventListener("dragover", (e) => {
  e.preventDefault();
  dropzone.classList.add("dragging");
});
dropzone.addEventListener("dragleave", () => dropzone.classList.remove("dragging"));
dropzone.addEventListener("drop", (e) => {
  e.preventDefault();
  dropzone.classList.remove("dragging");
  if (e.dataTransfer.files.length) uploadFile(e.dataTransfer.files[0]);
});

function uploadFile(file) {
  dropzone.classList.add("hidden");
  $("#upload-progress").classList.remove("hidden");

  const xhr = new XMLHttpRequest();
  xhr.open("POST", "/api/upload");
  xhr.upload.addEventListener("progress", (e) => {
    if (e.lengthComputable) {
      const pct = Math.round((e.loaded / e.total) * 100);
      $("#upload-bar-fill").style.width = pct + "%";
      $("#upload-label").textContent = `Uploading... ${pct}%`;
    }
  });
  xhr.addEventListener("load", () => {
    if (xhr.status === 200) {
      const { job_id } = JSON.parse(xhr.responseText);
      show("job");
      pollJob(job_id);
    } else {
      let detail = xhr.responseText;
      try { detail = JSON.parse(xhr.responseText).detail; } catch {}
      showError(detail || `Upload failed (${xhr.status})`);
    }
  });
  xhr.addEventListener("error", () => showError("Upload failed - is the server running?"));

  const form = new FormData();
  form.append("file", file);
  form.append("captions", $("#captions-checkbox").checked);
  xhr.send(form);
}

// --- Job polling ---

const STAGE_LABELS = {
  queued: "Waiting to start...",
  transcribing: "Transcribing audio (this is the slow part)...",
  selecting: "Asking Claude to pick the best moments...",
  rendering: "Cutting and cropping clips...",
  done: "Done!",
};

function pollJob(jobId) {
  const timer = setInterval(async () => {
    let job;
    try {
      const res = await fetch(`/api/jobs/${jobId}`);
      job = await res.json();
    } catch {
      return; // transient network error, keep polling
    }

    document.querySelectorAll(".stage").forEach((el) => {
      el.classList.toggle("active", el.dataset.stage === job.stage);
      const order = ["transcribing", "selecting", "rendering"];
      el.classList.toggle(
        "complete",
        order.indexOf(el.dataset.stage) < order.indexOf(job.stage) || job.status === "done"
      );
    });
    $("#job-bar-fill").style.width = Math.round(job.progress * 100) + "%";
    $("#job-label").textContent = STAGE_LABELS[job.stage] || job.stage;

    if (job.status === "done") {
      clearInterval(timer);
      renderResults(jobId, job.metadata);
    } else if (job.status === "error") {
      clearInterval(timer);
      showError(job.error || "Unknown error");
    }
  }, 1500);
}

// --- Results ---

function renderResults(jobId, metadata) {
  show("results");
  $("#download-all").href = `/api/jobs/${jobId}/download-all`;
  const container = $("#clips");
  container.innerHTML = "";

  for (const clip of metadata.clips) {
    const card = document.createElement("div");
    card.className = "clip-card";
    card.innerHTML = `
      <video controls preload="metadata" src="/api/jobs/${jobId}/clips/${clip.filename}"></video>
      <div class="clip-info">
        <div class="clip-top">
          <span class="hook-score" title="Hook strength">Hook ${clip.hook_score}/10</span>
          <span class="clip-time">${fmt(clip.start_s)}-${fmt(clip.end_s)} - ${Math.round(clip.duration_s)}s</span>
        </div>
        <h3></h3>
        <p class="desc"></p>
        <p class="hashtags"></p>
        <p class="reason"></p>
        <div class="clip-actions">
          <button class="copy-btn">Copy title + tags</button>
          <a class="button" href="/api/jobs/${jobId}/clips/${clip.filename}" download>Download</a>
        </div>
      </div>`;
    card.querySelector("h3").textContent = clip.title;
    card.querySelector(".desc").textContent = clip.description;
    card.querySelector(".hashtags").textContent = clip.hashtags.map((h) => "#" + h).join(" ");
    card.querySelector(".reason").textContent = "Why: " + clip.reason;
    card.querySelector(".copy-btn").addEventListener("click", (e) => {
      const text = `${clip.title}\n\n${clip.description}\n\n${clip.hashtags.map((h) => "#" + h).join(" ")}`;
      navigator.clipboard.writeText(text);
      e.target.textContent = "Copied!";
      setTimeout(() => (e.target.textContent = "Copy title + tags"), 1500);
    });
    container.appendChild(card);
  }
}

function fmt(s) {
  const m = Math.floor(s / 60);
  const sec = Math.floor(s % 60);
  return `${m}:${String(sec).padStart(2, "0")}`;
}

// --- Error / reset ---

function showError(message) {
  show("error");
  $("#error-text").textContent = message;
}

function reset() {
  show("upload");
  dropzone.classList.remove("hidden");
  $("#upload-progress").classList.add("hidden");
  $("#upload-bar-fill").style.width = "0";
  fileInput.value = "";
}

$("#retry-btn").addEventListener("click", reset);
$("#new-video-btn").addEventListener("click", reset);
