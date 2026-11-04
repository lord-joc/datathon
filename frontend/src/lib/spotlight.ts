/**
 * Red border light that follows the pointer on interactive cards (class "spot").
 * One delegated listener for the whole page writes --mx / --my on the card under the pointer;
 * the drawing is pure CSS (index.css). Touch and pen get the plain hover border instead.
 */
let installed = false;

export function initSpotlight() {
  if (installed || typeof window === "undefined") return;
  installed = true;
  let frame = 0;
  let last: PointerEvent | null = null;

  const paint = () => {
    frame = 0;
    const e = last;
    if (!e || !(e.target instanceof Element)) return;
    const card = e.target.closest<HTMLElement>(".spot");
    if (!card) return;
    const r = card.getBoundingClientRect();
    card.style.setProperty("--mx", `${e.clientX - r.left}px`);
    card.style.setProperty("--my", `${e.clientY - r.top}px`);
  };

  document.addEventListener(
    "pointermove",
    (e) => {
      if (e.pointerType !== "mouse") return;
      last = e;
      if (!frame) frame = window.requestAnimationFrame(paint);
    },
    { passive: true },
  );
}
