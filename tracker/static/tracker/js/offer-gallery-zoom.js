/* Zoom is independent of the slider, including galleries with a single photo. */
(() => {
  document.querySelectorAll('[data-offer-gallery]').forEach(gallery => {
    const dialog = gallery.querySelector('[data-gallery-zoom]');
    if (!dialog || typeof dialog.showModal !== 'function') return;
    const track = gallery.querySelector('[data-gallery-track]');
    const photos = [...gallery.querySelectorAll('[data-gallery-open-photo]')];
    const openButton = gallery.querySelector('[data-gallery-zoom-open]');
    const stage = dialog.querySelector('[data-zoom-stage]');
    const canvas = dialog.querySelector('[data-zoom-canvas]');
    const image = dialog.querySelector('[data-zoom-image]');
    const reset = dialog.querySelector('[data-zoom-reset]');
    const zoomIn = dialog.querySelector('[data-zoom-in]');
    const zoomOut = dialog.querySelector('[data-zoom-out]');
    const error = dialog.querySelector('[data-zoom-error]');
    const pointers = new Map();
    let index = 0, zoom = 1, width = 0, height = 0, pinch = null, opener = null;
    let previousOverflow = '', swipeStart = null;

    const render = () => {
      image.style.width = `${width * zoom}px`;
      image.style.height = `${height * zoom}px`;
      canvas.style.width = `${Math.max(stage.clientWidth, width * zoom)}px`;
      canvas.style.height = `${Math.max(stage.clientHeight, height * zoom)}px`;
      stage.dataset.magnified = String(zoom > 1);
      reset.textContent = `${Math.round(zoom * 100)} %`;
      zoomIn.disabled = !width || zoom >= 4;
      zoomOut.disabled = !width || zoom <= 1;
    };
    const fit = () => {
      if (!dialog.open || !image.naturalWidth) return;
      const ratio = Math.min(1, stage.clientWidth / image.naturalWidth, stage.clientHeight / image.naturalHeight);
      width = image.naturalWidth * ratio;
      height = image.naturalHeight * ratio;
      render();
    };
    const setZoom = value => {
      if (!width) return;
      const x = (stage.scrollLeft + stage.clientWidth / 2) / canvas.clientWidth;
      const y = (stage.scrollTop + stage.clientHeight / 2) / canvas.clientHeight;
      zoom = Math.max(1, Math.min(4, value));
      render();
      stage.scrollLeft = x * canvas.clientWidth - stage.clientWidth / 2;
      stage.scrollTop = y * canvas.clientHeight - stage.clientHeight / 2;
    };
    const select = next => {
      index = (next + photos.length) % photos.length;
      zoom = 1; width = height = 0; pointers.clear(); pinch = null;
      stage.dataset.dragging = 'false';
      error.hidden = true;
      image.alt = photos[index].querySelector('img').alt;
      image.style.visibility = 'hidden';
      render();
      image.src = photos[index].href;
      dialog.querySelector('[data-zoom-counter]').textContent = `Photo ${index + 1} sur ${photos.length}`;
      gallery.dispatchEvent(new CustomEvent('gallery:select', {detail: {index}}));
      stage.scrollLeft = stage.scrollTop = 0;
      if (image.complete && image.naturalWidth) { image.style.visibility = ''; fit(); }
    };
    const open = (next, trigger) => {
      if (dialog.open) return;
      opener = trigger;
      previousOverflow = document.body.style.overflow;
      document.body.style.overflow = 'hidden';
      gallery.dispatchEvent(new CustomEvent('gallery:zoom-open'));
      dialog.showModal();
      select(next);
    };
    image.addEventListener('load', () => { image.style.visibility = ''; fit(); });
    image.addEventListener('error', () => { width = height = 0; render(); error.hidden = false; });
    openButton.hidden = false;
    openButton.addEventListener('click', () => open(track.clientWidth ? Math.round(track.scrollLeft / track.clientWidth) : 0, openButton));
    track.addEventListener('pointerdown', event => { swipeStart = {x: event.clientX, y: event.clientY}; }, {passive: true});
    photos.forEach((photo, i) => photo.addEventListener('click', event => {
      event.preventDefault();
      // A swipe must not open the modal when the finger leaves the image.
      if (event.detail && swipeStart && Math.hypot(event.clientX - swipeStart.x, event.clientY - swipeStart.y) > 12) return;
      open(i, photo);
    }));
    dialog.querySelector('[data-zoom-close]').addEventListener('click', () => dialog.close());
    dialog.addEventListener('close', () => {
      pointers.clear(); pinch = null;
      document.body.style.overflow = previousOverflow;
      if (opener && opener.isConnected) opener.focus({preventScroll: true});
    });
    zoomIn.addEventListener('click', () => setZoom(zoom + 0.5));
    zoomOut.addEventListener('click', () => setZoom(zoom - 0.5));
    reset.addEventListener('click', () => setZoom(1));
    dialog.querySelector('[data-zoom-prev]')?.addEventListener('click', () => select(index - 1));
    dialog.querySelector('[data-zoom-next]')?.addEventListener('click', () => select(index + 1));
    dialog.addEventListener('keydown', event => {
      if (event.key === '+' || event.key === '=') { event.preventDefault(); setZoom(zoom + 0.5); }
      else if (event.key === '-') { event.preventDefault(); setZoom(zoom - 0.5); }
      else if (event.key === '0') { event.preventDefault(); setZoom(1); }
      else if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') {
        event.preventDefault(); select(index + (event.key === 'ArrowRight' ? 1 : -1));
      }
    });
    stage.addEventListener('wheel', event => {
      event.preventDefault(); setZoom(zoom + (event.deltaY < 0 ? 0.25 : -0.25));
    }, {passive: false});
    const distance = () => {
      const [a, b] = [...pointers.values()];
      return Math.hypot(a.x - b.x, a.y - b.y);
    };
    stage.addEventListener('pointerdown', event => {
      if (event.pointerType === 'mouse' && event.button !== 0) return;
      stage.setPointerCapture(event.pointerId);
      pointers.set(event.pointerId, {x: event.clientX, y: event.clientY});
      stage.dataset.dragging = 'true';
      if (pointers.size === 2) pinch = {distance: distance(), zoom};
    });
    stage.addEventListener('pointermove', event => {
      const previous = pointers.get(event.pointerId);
      if (!previous) return;
      pointers.set(event.pointerId, {x: event.clientX, y: event.clientY});
      if (pointers.size === 2 && pinch?.distance) setZoom(pinch.zoom * distance() / pinch.distance);
      else if (pointers.size === 1 && zoom > 1) {
        stage.scrollLeft -= event.clientX - previous.x;
        stage.scrollTop -= event.clientY - previous.y;
      }
    });
    const release = event => {
      pointers.delete(event.pointerId); pinch = null;
      stage.dataset.dragging = String(pointers.size > 0);
    };
    ['pointerup', 'pointercancel', 'lostpointercapture'].forEach(type => stage.addEventListener(type, release));
    if ('ResizeObserver' in window) new ResizeObserver(fit).observe(stage);
  });
})();
