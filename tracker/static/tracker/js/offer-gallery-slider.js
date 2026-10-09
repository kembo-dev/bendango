/* Native scrolling keeps swipe and no-JavaScript navigation available. */
(() => {
  document.querySelectorAll('[data-offer-gallery]').forEach(gallery => {
    const track = gallery.querySelector('[data-gallery-track]');
    const slides = [...track.children];
    if (slides.length < 2) return;
    const thumbs = [...gallery.querySelectorAll('[data-gallery-thumb]')];
    const counter = gallery.querySelector('[data-gallery-counter]');
    const status = gallery.querySelector('[data-gallery-status]');
    const play = gallery.querySelector('[data-gallery-play]');
    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)');
    let index = 0, timer = null, playing = false, hovered = false, inView = true, frame = null, target = null;
    const update = announce => {
      thumbs.forEach((thumb, i) => {
        if (i === index) thumb.setAttribute('aria-current', 'true'); else thumb.removeAttribute('aria-current');
      });
      counter.textContent = `${index + 1} / ${slides.length}`;
      if (announce) status.textContent = `Photo ${index + 1} sur ${slides.length}`;
    };
    const schedule = () => {
      clearTimeout(timer); timer = null;
      if (playing && !reduced.matches && !hovered && inView && !document.hidden && (!gallery.contains(document.activeElement) || document.activeElement === play)) {
        timer = setTimeout(() => { go(index + 1, false); schedule(); }, 5000);
      }
    };
    const setPlaying = value => {
      playing = value;
      play.textContent = playing ? 'Ⅱ Pause' : '▶ Diaporama';
      play.setAttribute('aria-label', playing ? 'Mettre le diaporama en pause' : 'Démarrer le diaporama');
      play.setAttribute('aria-pressed', String(playing));
      schedule();
    };
    const go = (next, manual = true) => {
      if (manual) setPlaying(false);
      index = (next + slides.length) % slides.length;
      target = index;
      track.scrollTo({left: index * track.clientWidth, behavior: reduced.matches ? 'instant' : 'smooth'});
      update(manual);
    };
    gallery.querySelector('[data-gallery-prev]').addEventListener('click', () => go(index - 1));
    gallery.querySelector('[data-gallery-next]').addEventListener('click', () => go(index + 1));
    thumbs.forEach((thumb, i) => thumb.addEventListener('click', event => { event.preventDefault(); go(i); }));
    track.addEventListener('keydown', event => {
      if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') {
        event.preventDefault(); go(index + (event.key === 'ArrowRight' ? 1 : -1));
      } else if (event.key === 'Home' || event.key === 'End') {
        event.preventDefault(); go(event.key === 'Home' ? 0 : slides.length - 1);
      }
    });
    track.addEventListener('pointerdown', () => { target = null; setPlaying(false); }, {passive: true});
    track.addEventListener('scroll', () => {
      if (frame !== null) return;
      frame = requestAnimationFrame(() => {
        frame = null;
        if (!track.clientWidth) return;
        if (target !== null) {
          if (Math.abs(track.scrollLeft - target * track.clientWidth) > 2) return;
          target = null;
        }
        index = Math.max(0, Math.min(slides.length - 1, Math.round(track.scrollLeft / track.clientWidth)));
        update(false);
      });
    }, {passive: true});
    play.addEventListener('click', () => { hovered = false; setPlaying(!playing); });
    track.addEventListener('wheel', () => { target = null; setPlaying(false); }, {passive: true});
    gallery.addEventListener('mouseenter', () => { hovered = true; schedule(); });
    gallery.addEventListener('mouseleave', () => { hovered = false; schedule(); });
    gallery.addEventListener('focusin', schedule);
    gallery.addEventListener('focusout', () => setTimeout(schedule, 0));
    document.addEventListener('visibilitychange', schedule);
    reduced.addEventListener('change', () => {
      play.disabled = reduced.matches;
      if (reduced.matches) setPlaying(false);
    });
    if ('IntersectionObserver' in window) {
      new IntersectionObserver(entries => { inView = entries[0].isIntersecting; schedule(); }, {threshold: 0.25}).observe(gallery);
    }
    if ('ResizeObserver' in window) {
      new ResizeObserver(() => {
        if (track.clientWidth) track.scrollTo({left: index * track.clientWidth, behavior: 'instant'});
      }).observe(track);
    }
    window.addEventListener('pagehide', () => { clearTimeout(timer); });
    window.addEventListener('pageshow', schedule);
    gallery.querySelector('[data-gallery-controls]').hidden = false;
    play.hidden = false;
    play.disabled = reduced.matches;
    update(false);
    // Automatic motion is opt-in; reduced-motion users retain manual controls.
    setPlaying(false);
  });
})();
