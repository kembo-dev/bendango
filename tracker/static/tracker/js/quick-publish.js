/* Progressive enhancement: the complete form remains usable without JavaScript. */
(() => {
  const form = document.getElementById('quick-publish');
  if (!form) return;
  const panels = [...form.querySelectorAll('[data-step]')];
  const next = document.getElementById('publish-next');
  const back = document.getElementById('publish-back');
  const submit = document.getElementById('publish-submit');
  const progress = document.getElementById('publish-progress');
  const label = document.getElementById('publish-step-label');
  const photos = document.getElementById('id_photos');
  const camera = document.getElementById('phone-camera');
  const status = document.getElementById('photo-status');
  const previews = document.getElementById('photo-previews');
  const cover = document.getElementById('preview-cover');
  const placeholder = document.getElementById('preview-placeholder');
  let step = 0, selected = [], urls = [], pending = false;
  const supportsFiles = (() => { try { return Boolean(new DataTransfer().items); } catch { return false; } })();
  const show = (index, focus = true) => {
    step = index;
    panels.forEach((panel, i) => { panel.hidden = i !== index; });
    [...progress.children].forEach((item, i) => {
      if (i === index) item.setAttribute('aria-current', 'step'); else item.removeAttribute('aria-current');
    });
    back.hidden = index === 0; next.hidden = index === 2; submit.hidden = index !== 2;
    label.textContent = `Étape ${index + 1} sur 3`;
    if (focus) panels[index].querySelector('h2').focus();
  };
  const check = index => {
    const fields = [...panels[index].querySelectorAll('input, select, textarea')];
    for (const field of fields) {
      if (!field.checkValidity()) {
        show(index, false);
        // Optional fields inside details still need an accessible error.
        const details = field.closest('details'); if (details) details.open = true;
        field.reportValidity(); return false;
      }
    }
    return true;
  };
  const updatePreview = () => {
    document.getElementById('preview-title').textContent = document.getElementById('id_title').value.trim() || 'Le titre de votre annonce';
    const price = document.getElementById('id_price').value;
    document.getElementById('preview-price').textContent = price ? `${price} ${document.getElementById('id_currency').value.toUpperCase()}` : 'Prix sur demande';
    const city = document.getElementById('id_city');
    if (city) document.getElementById('preview-city').textContent = city.value;
  };
  const syncPhotos = () => {
    const transfer = new DataTransfer(); selected.forEach(file => transfer.items.add(file)); photos.files = transfer.files;
    urls.forEach(url => URL.revokeObjectURL(url)); urls = []; previews.replaceChildren();
    selected.forEach((file, index) => {
      const url = URL.createObjectURL(file); urls.push(url);
      const tile = document.createElement('div'); tile.className = 'relative';
      const image = document.createElement('img'); image.src = url; image.alt = `Photo ${index + 1}`;
      image.className = 'aspect-square w-full object-cover rounded-xl'; tile.append(image);
      const remove = document.createElement('button'); remove.type = 'button'; remove.textContent = '×';
      remove.className = 'absolute top-1 right-1 bg-slate-950 text-white rounded-full size-9 text-xl';
      remove.setAttribute('aria-label', `Retirer la photo ${index + 1}`);
      remove.addEventListener('click', () => { selected.splice(index, 1); syncPhotos(); }); tile.append(remove);
      if (index === 0 && !cover.dataset.existingSrc) {
        const badge = document.createElement('span'); badge.textContent = 'Couverture'; badge.className = 'tag tag-success mt-1 text-xs'; tile.append(badge);
      } else if (!cover.dataset.existingSrc) {
        const first = document.createElement('button'); first.type = 'button'; first.textContent = 'En couverture';
        first.className = 'text-xs text-emerald-700 dark:text-emerald-300 min-h-11';
        first.addEventListener('click', () => { selected.unshift(selected.splice(index, 1)[0]); syncPhotos(); }); tile.append(first);
      }
      previews.append(tile);
    });
    if (urls.length || cover.dataset.existingSrc) { cover.src = cover.dataset.existingSrc || urls[0]; cover.hidden = false; placeholder.hidden = true; }
    else { cover.removeAttribute('src'); cover.hidden = true; placeholder.hidden = false; }
    status.textContent = `${selected.length} / 8 photos sélectionnées`;
    photos.setCustomValidity('');
  };
  const addPhotos = files => {
    const incoming = [...files];
    if (selected.length + incoming.length > 8) { status.textContent = '8 photos maximum. Retirez une photo pour en ajouter une autre.'; syncInput(); return; }
    if (incoming.some(file => file.size > 8 * 1024 * 1024)) { status.textContent = 'Chaque photo doit faire au maximum 8 Mo.'; syncInput(); return; }
    selected.push(...incoming); syncPhotos();
  };
  const syncInput = () => { const transfer = new DataTransfer(); selected.forEach(file => transfer.items.add(file)); photos.files = transfer.files; };
  if (supportsFiles) {
    document.getElementById('camera-actions').hidden = false;
    document.getElementById('take-photo').addEventListener('click', () => camera.click());
    document.getElementById('choose-photos').addEventListener('click', () => photos.click());
    photos.addEventListener('change', () => addPhotos(photos.files));
    camera.addEventListener('change', () => { addPhotos(camera.files); camera.value = ''; });
  } else {
    photos.addEventListener('change', () => { status.textContent = `${photos.files.length} photo(s) sélectionnée(s)`; });
  }
  next.addEventListener('click', () => { if (check(step)) show(step + 1); });
  back.addEventListener('click', () => show(step - 1));
  form.addEventListener('input', updatePreview);
  form.addEventListener('submit', event => {
    if (step !== 2) { event.preventDefault(); if (check(step)) show(step + 1); return; }
    for (let i = 0; i < panels.length; i++) { if (!check(i)) { event.preventDefault(); return; } }
    if (pending) { event.preventDefault(); return; }
    pending = true; submit.disabled = true; submit.textContent = 'Publication en cours…';
  });
  // Return from a restored page must not leave the submit action disabled.
  window.addEventListener('pageshow', () => { pending = false; submit.disabled = false; submit.textContent = submit.dataset.label; });
  window.addEventListener('pagehide', () => urls.forEach(url => URL.revokeObjectURL(url)));
  submit.dataset.label = submit.textContent;
  form.noValidate = true; progress.hidden = false; label.hidden = false;
  document.getElementById('publish-preview').hidden = false;
  const errorPanel = panels.findIndex(panel => panel.querySelector('[data-field-error]'));
  show(errorPanel >= 0 ? errorPanel : 0, false); updatePreview();
  if (cover.dataset.existingSrc) { cover.src = cover.dataset.existingSrc; cover.hidden = false; placeholder.hidden = true; }
})();
