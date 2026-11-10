// Small input rules for the question box. Pure, so node can test them.
export function enterAction(e, isTouch) {
  if (e.key !== "Enter" || e.isComposing) return "default";
  if (e.ctrlKey || e.metaKey) return "send";
  if (e.shiftKey || isTouch) return "default";
  return "send";
}

export function growHeight(scrollHeight, minPx, maxPx) {
  return Math.min(maxPx, Math.max(minPx, scrollHeight));
}

export function scrollBehavior(prefersReducedMotion) {
  return prefersReducedMotion ? "auto" : "smooth";
}

export function isTouchDevice(matchMedia) {
  try {
    return typeof matchMedia === "function" && matchMedia("(pointer: coarse)").matches === true;
  } catch {
    return false;
  }
}
