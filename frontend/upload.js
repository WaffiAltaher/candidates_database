if (!requireAuth()) throw new Error('redirect');

document.getElementById('upload-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const fileInput = document.getElementById('pdf-file');
    const file = fileInput.files[0];
    if (!file) return;

    if (!file.name.toLowerCase().endsWith('.pdf')) {
        showFlash('Please select a PDF file.', 'error');
        return;
    }

    const btn = document.getElementById('upload-btn');
    const spinner = document.getElementById('spinner');
    btn.disabled = true;
    spinner.style.display = 'block';

    try {
        const base64 = await new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onload = () => {
                const dataUrl = reader.result;
                resolve(dataUrl.split(',')[1]);
            };
            reader.onerror = reject;
            reader.readAsDataURL(file);
        });

        const data = await api(API.upload + '/upload', {
            method: 'POST',
            body: { filename: file.name, file_data: base64 },
        });

        if (data) {
            if (data.warning) {
                showFlash(data.warning, 'warning');
            } else {
                showFlash(`Successfully ingested CV for: ${data.candidate}`, 'success');
            }
            fileInput.value = '';
        }
    } catch (err) {
        showFlash(err.message, 'error');
    } finally {
        btn.disabled = false;
        spinner.style.display = 'none';
    }
});
document.getElementById('folder-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const folderInput = document.getElementById('pdf-folder');
    const allFiles = Array.from(folderInput.files).filter(f => f.name.toLowerCase().endsWith('.pdf'));

    if (allFiles.length === 0) {
        showFlash('No PDF files found in the selected folder.', 'error');
        return;
    }

    const btn = document.getElementById('folder-btn');
    const progressLabel = document.getElementById('folder-progress-label');
    const progressWrap = document.getElementById('folder-progress-wrap');
    const progressBar = document.getElementById('folder-progress-bar');
    const resultsDiv = document.getElementById('folder-results');
    const resultsBody = document.getElementById('folder-results-body');

    btn.disabled = true;
    progressLabel.style.display = 'block';
    progressWrap.style.display = 'block';
    resultsDiv.style.display = 'block';
    resultsBody.innerHTML = '';

    let succeeded = 0, replaced = 0, failed = 0;

    for (let i = 0; i < allFiles.length; i++) {
        const file = allFiles[i];
        progressLabel.textContent = `Processing ${i + 1} of ${allFiles.length}: ${file.name}`;
        progressBar.style.width = `${((i) / allFiles.length) * 100}%`;

        const tr = document.createElement('tr');
        try {
            const base64 = await new Promise((resolve, reject) => {
                const reader = new FileReader();
                reader.onload = () => resolve(reader.result.split(',')[1]);
                reader.onerror = reject;
                reader.readAsDataURL(file);
            });

            const data = await api(API.upload + '/upload', {
                method: 'POST',
                body: { filename: file.name, file_data: base64 },
            });

            if (data.warning) {
                replaced++;
                tr.innerHTML = `<td>${escapeHtml(file.name)}</td><td class="result-replaced">Replaced: ${escapeHtml(data.candidate)}</td>`;
            } else {
                succeeded++;
                tr.innerHTML = `<td>${escapeHtml(file.name)}</td><td class="result-ok">Added: ${escapeHtml(data.candidate)}</td>`;
            }
        } catch (err) {
            failed++;
            tr.innerHTML = `<td>${escapeHtml(file.name)}</td><td class="result-error">Error: ${escapeHtml(err.message)}</td>`;
        }
        resultsBody.appendChild(tr);
    }

    progressBar.style.width = '100%';
    progressLabel.textContent = `Done — ${succeeded} added, ${replaced} replaced, ${failed} failed.`;
    btn.disabled = false;
    folderInput.value = '';
});
