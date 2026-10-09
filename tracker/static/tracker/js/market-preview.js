/* Card previews only load additional photos when the user explores them. */
(() => {
  const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
  document.querySelectorAll('[data-market-preview]').forEach((preview) => {
    const frames = [...preview.querySelectorAll('[data-photo-frame]')];
    if (frames.length < 2) return;
    const controls = preview.querySelector('.market-preview-controls');
    const dots = [...preview.querySelectorAll('.market-photo-dots span')];
    const count = preview.querySelector('[data-photo-count]');
    let current = 0;
    let timer;
    let hovered = false;
    let visible = true;
    let revision = 0;
    const stop = () => { clearTimeout(timer); timer = undefined; };
    const canPlay = () => hovered && visible && !document.hidden && !reducedMotion.matches
      && !controls.contains(document.activeElement);
    const schedule = () => {
      stop();
      if (canPlay()) timer = setTimeout(async () => {
        await show(current + 1, false);
        schedule();
      }, 3200);
    };
    const show = async (index, manual) => {
      const ticket = ++revision;
      const next = (index + frames.length) % frames.length;
      const photo = frames[next].querySelector('img');
      if (photo.dataset.src) {
        photo.src = photo.dataset.src;
        delete photo.dataset.src;
      }
      try { await photo.decode(); } catch { return; }
      if (ticket !== revision || (!manual && !canPlay())) return;
      frames[current].classList.remove('is-current');
      frames[current].setAttribute('aria-hidden', 'true');
      frames[next].classList.add('is-current');
      frames[next].setAttribute('aria-hidden', 'false');
      dots[current].classList.remove('is-current');
      dots[next].classList.add('is-current');
      current = next;
      // Hover playback remains quiet for screen readers.
      count.setAttribute('aria-live', manual ? 'polite' : 'off');
      count.textContent = `${current + 1} / ${frames.length}`;
    };
    controls.hidden = false;
    preview.querySelector('.market-photo-dots').hidden = false;
    preview.querySelector('[data-photo-prev]').addEventListener('click', () => {
      stop(); show(current - 1, true);
    });
    preview.querySelector('[data-photo-next]').addEventListener('click', () => {
      stop(); show(current + 1, true);
    });
    preview.addEventListener('pointerenter', (event) => {
      if (event.pointerType === 'mouse') { hovered = true; schedule(); }
    });
    preview.addEventListener('pointerleave', () => { hovered = false; stop(); });
    controls.addEventListener('focusin', stop);
    controls.addEventListener('focusout', schedule);
    document.addEventListener('visibilitychange', schedule);
    reducedMotion.addEventListener('change', schedule);
    if ('IntersectionObserver' in window) new IntersectionObserver(([entry]) => {
      visible = entry.isIntersecting;
      schedule();
    }).observe(preview);
  });
})();
