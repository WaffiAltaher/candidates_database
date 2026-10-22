if (!requireAuth()) throw new Error('redirect');

(async () => {
    try {
        const data = await api(API.candidates + '/candidates');
        if (!data) return;
        const tbody = document.getElementById('candidates-body');
        const candidates = data.candidates || [];
        document.getElementById('page-title').textContent = `Candidates (${candidates.length})`;

        if (candidates.length === 0) {
            tbody.innerHTML = '<tr><td colspan="5">No candidates yet. <a href="/upload.html">Upload a CV</a> to get started.</td></tr>';
            return;
        }

        tbody.innerHTML = candidates.map(c => {
            const techs = (c.technologies || []).slice(0, 5).map(t =>
                `<span class="tag">${escapeHtml(t)}</span>`
            ).join('');
            const extra = (c.technologies || []).length > 5
                ? `<span class="tag">+${c.technologies.length - 5} more</span>` : '';
            const exp = c.years_experience ? `${escapeHtml(c.years_experience)} yrs` : '-';
            return `<tr>
                <td><a href="/candidate.html?id=${encodeURIComponent(c.id)}">${escapeHtml(c.name)}</a></td>
                <td>${escapeHtml(c.job_title) || '-'}</td>
                <td>${escapeHtml(c.university) || '-'}</td>
                <td>${exp}</td>
                <td>${techs}${extra}</td>
            </tr>`;
        }).join('');
    } catch (err) {
        showFlash(err.message, 'error');
    }
})();
