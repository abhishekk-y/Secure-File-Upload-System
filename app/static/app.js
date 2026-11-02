'use strict';
document.querySelectorAll('[data-open]').forEach(button => button.addEventListener('click', () => {
  document.getElementById(button.dataset.open)?.showModal();
}));
document.querySelectorAll('[data-close]').forEach(button => button.addEventListener('click', () => button.closest('dialog').close()));
document.querySelectorAll('dialog').forEach(dialog => dialog.addEventListener('click', event => {
  if (event.target === dialog) {
    const box = dialog.getBoundingClientRect();
    if (event.clientX < box.left || event.clientX > box.right || event.clientY < box.top || event.clientY > box.bottom) dialog.close();
  }
}));
const fileInput = document.querySelector('#file');
const feedback = document.querySelector('#file-feedback');
const dropzone = document.querySelector('#dropzone');
function selectedFile() {
  const file = fileInput?.files[0];
  const invalid = file && (file.size === 0 || file.size > 50 * 1024 * 1024);
  fileInput?.setCustomValidity(invalid ? 'Choose a nonempty file no larger than 50 MiB.' : '');
  if (feedback) feedback.textContent = file ? `${file.name} · ${(file.size / 1024 / 1024).toFixed(2)} MiB${invalid ? ' — exceeds the 50 MiB limit' : ''}` : 'No file selected';
}
fileInput?.addEventListener('change', selectedFile);
for (const name of ['dragenter', 'dragover']) dropzone?.addEventListener(name, event => { event.preventDefault(); dropzone.classList.add('dragging'); });
for (const name of ['dragleave', 'drop']) dropzone?.addEventListener(name, event => { event.preventDefault(); dropzone.classList.remove('dragging'); });
dropzone?.addEventListener('drop', event => {
  if (event.dataTransfer.files.length !== 1) { feedback.textContent = 'Choose one file at a time.'; return; }
  fileInput.files = event.dataTransfer.files;
  selectedFile();
});
document.querySelectorAll('.delete-form').forEach(form => form.addEventListener('submit', event => {
  if (!window.confirm('Permanently delete this file and revoke its share codes?')) event.preventDefault();
}));
const uploadForm = document.querySelector('#upload-form');
uploadForm?.addEventListener('submit', event => {
  if (!uploadForm.reportValidity()) return;
  event.preventDefault();
  const button = document.querySelector('#upload-button');
  const status = document.querySelector('#transfer-status');
  const progress = document.querySelector('#upload-progress');
  const message = document.querySelector('#progress-text');
  const scanProgress = document.querySelector('#scan-progress');
  const scanMessage = document.querySelector('#scan-progress-text');
  const progressId = [...crypto.getRandomValues(new Uint8Array(16))].map(value => value.toString(16).padStart(2, '0')).join('');
  const progressInput = document.querySelector('#progress-id');
  progressInput.value = progressId;
  const statusUrl = uploadForm.dataset.progressUrl.replace('0'.repeat(32), progressId);
  button.disabled = true;
  status.hidden = false;
  let pollTimer;
  let polling = true;
  const pollStatus = async () => {
    if (!polling) return;
    try {
      const response = await fetch(statusUrl, {credentials: 'same-origin', cache: 'no-store'});
      if (response.ok) {
        const stage = await response.json();
        if (stage.state !== 'waiting') {
          scanProgress.value = stage.percent;
          scanMessage.textContent = `${stage.label} ${stage.percent}%`;
          if (stage.state === 'complete' || stage.state === 'rejected') polling = false;
        }
      }
    } catch { /* A temporary polling failure does not interrupt the upload. */ }
    if (polling) pollTimer = setTimeout(pollStatus, 1000);
  };
  pollStatus();
  const xhr = new XMLHttpRequest();
  xhr.open('POST', uploadForm.action);
  xhr.timeout = 180000;
  xhr.upload.addEventListener('progress', event => {
    if (event.lengthComputable) {
      const percent = Math.round(event.loaded / event.total * 100);
      progress.value = percent;
      message.textContent = percent < 100 ? `Transferring file ${percent}%` : 'Transfer complete · server checks are starting…';
    }
  });
  const stopPolling = () => { polling = false; clearTimeout(pollTimer); };
  const fail = text => { stopPolling(); message.textContent = text; button.disabled = false; };
  xhr.onload = () => {
    stopPolling();
    if (xhr.status >= 200 && xhr.status < 400) {
      // Flash messages survive the followed redirect only in its HTML response.
      // Preserve notices before navigating back to the workspace.
      const parsed = new DOMParser().parseFromString(xhr.responseText, 'text/html');
      const notices = [...parsed.querySelectorAll('.notice')].map(item => ({text:item.textContent, error:item.classList.contains('error')}));
      try { sessionStorage.setItem('upload-notices', JSON.stringify(notices)); }
      catch { /* Navigation still works when browser storage is unavailable. */ }
      window.location.assign(new URL(xhr.responseURL).pathname);
    } else fail(xhr.status === 413 ? 'Upload exceeds the request size limit.' : xhr.status === 429 ? 'Too many uploads. Please wait before trying again.' : 'The upload could not be completed. Refresh the page and try again.');
  };
  xhr.onerror = () => fail('Connection interrupted. Check your file list before retrying.');
  xhr.ontimeout = () => fail('The request timed out. Check your file list before retrying.');
  xhr.send(new FormData(uploadForm));
});
let savedNotices;
try {
  savedNotices = sessionStorage.getItem('upload-notices');
  sessionStorage.removeItem('upload-notices');
} catch { /* Optional UI state must not disable file controls. */ }
if (savedNotices) {
  try { JSON.parse(savedNotices).forEach(notice => {
    const element = document.createElement('div');
    element.className = `notice ${notice.error ? 'error' : 'success'}`;
    element.setAttribute('role', 'status'); element.textContent = notice.text;
    document.querySelector('#main').prepend(element);
  }); } catch { /* Ignore invalid temporary UI state. */ }
}
let currentFilter = 'all';
function filterFiles() {
  const query = document.querySelector('#file-search')?.value.trim().toLowerCase() || '';
  let count = 0;
  document.querySelectorAll('[data-file-row]').forEach(row => {
    const visible = (currentFilter === 'all' || row.dataset.type === currentFilter) && row.dataset.name.includes(query);
    row.hidden = !visible; if (visible) count++;
  });
  const counter = document.querySelector('#result-count');
  if (counter) counter.textContent = `${count} ${count === 1 ? 'file' : 'files'}`;
  const empty = document.querySelector('#no-results'); if (empty) empty.hidden = count !== 0;
  document.querySelectorAll('.filter-tabs [data-filter]').forEach(button => {
    button.classList.toggle('selected', button.dataset.filter === currentFilter);
    button.setAttribute('aria-pressed', String(button.dataset.filter === currentFilter));
  });
}
document.querySelector('#file-search')?.addEventListener('input', filterFiles);
document.querySelectorAll('[data-filter]').forEach(button => button.addEventListener('click', () => { currentFilter = button.dataset.filter; filterFiles(); }));
document.querySelector('#copy-code')?.addEventListener('click', async event => {
  const message = document.querySelector('#copy-feedback');
  try { await navigator.clipboard.writeText(event.currentTarget.dataset.code); message.textContent = 'Code copied. Share it through a trusted channel.'; }
  catch { message.textContent = 'Clipboard access is unavailable. Select and copy the code above.'; }
});
