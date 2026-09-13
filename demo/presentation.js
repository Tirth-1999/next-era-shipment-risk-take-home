"use strict";

const slides = [...document.querySelectorAll(".slide")];
const notes = [...document.querySelectorAll(".speaker-note")];
const picker = document.querySelector("#slide-picker");
const previous = document.querySelector("#previous");
const next = document.querySelector("#next");
const notesButton = document.querySelector("#toggle-notes");
let current = 0;

/** Show a bounded slide index and keep its notes, controls, and URL in sync. */
function show(index) {
  current = Math.max(0, Math.min(slides.length - 1, index));
  slides.forEach((slide, i) => { slide.hidden = i !== current; });
  notes.forEach((note, i) => { note.hidden = i !== current; });
  picker.value = String(current + 1);
  previous.disabled = current === 0;
  next.disabled = current === slides.length - 1;
  history.replaceState(null, "", `#slide-${current + 1}`);
  document.title = `Slide ${current + 1} · Shipment Risk`;
}

/** Open or close notes without changing the selected slide. */
function toggleNotes() {
  const panel = document.querySelector("#notes");
  panel.hidden = !panel.hidden;
  notesButton.setAttribute("aria-expanded", String(!panel.hidden));
}

/** Toggle browser fullscreen; report failure without breaking slide controls. */
async function fullscreen() {
  try {
    if (document.fullscreenElement) await document.exitFullscreen();
    else await document.body.requestFullscreen();
  } catch {
    document.querySelector("#status").textContent = "Fullscreen is unavailable. Use Chrome’s View menu to enter fullscreen.";
  }
}

/** Restore a bookmarked slide; malformed fragments return to the cover. */
function fromHash() {
  const match = location.hash.match(/^#slide-(\d+)$/);
  show(match ? Number(match[1]) - 1 : 0);
}

previous.addEventListener("click", () => show(current - 1));
next.addEventListener("click", () => show(current + 1));
picker.addEventListener("change", () => show(Number(picker.value) - 1));
notesButton.addEventListener("click", toggleNotes);
document.querySelector("#fullscreen").addEventListener("click", fullscreen);
document.addEventListener("fullscreenchange", () => {
  document.querySelector("#fullscreen").textContent = document.fullscreenElement ? "Exit fullscreen" : "Fullscreen";
});
window.addEventListener("hashchange", fromHash);
document.addEventListener("keydown", (event) => {
  if (event.altKey || event.ctrlKey || event.metaKey || event.target.closest("select, input, textarea")) return;
  // Space still activates a focused button or link using native browser behavior.
  if (event.key === " " && event.target.closest("button, a")) return;
  if (["ArrowRight", "PageDown", " "].includes(event.key)) { event.preventDefault(); show(current + 1); }
  if (["ArrowLeft", "PageUp"].includes(event.key)) { event.preventDefault(); show(current - 1); }
  if (event.key === "Home") { event.preventDefault(); show(0); }
  if (event.key === "End") { event.preventDefault(); show(slides.length - 1); }
  if (event.key.toLowerCase() === "n") toggleNotes();
  if (event.key.toLowerCase() === "f") fullscreen();
});
fromHash();
