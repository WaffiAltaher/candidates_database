if (!requireAuth()) throw new Error('redirect');

document.getElementById('search-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const query = document.getElementById('query-input').value.trim();
    if (!query) return;

    const spinner = document.getElementById('spinner');
    const resultsDiv = document.getElementById('results');
    spinner.style.display = 'block';
    resultsDiv.innerHTML = '';

    try {
        const data = await api(API.search + '/search', {
            method: 'POST',
            body: { query },
        });
        if (!data) return;

        let html = `
            <div class="card">
                <h2>Summary</h2>
                <p>${escapeHtml(data.summary)}</p>
            </div>
            <div class="card">
                <h2>SQL Query</h2>
                <pre>${escapeHtml(data.sql)}</pre>
            </div>
        `;

        const rows = data.raw_results || [];
        if (rows.length > 0) {
            const keys = Object.keys(rows[0]);
            const hasId = keys.includes('id');
            const nameKey = keys.find(k => k === 'name' || k === 'candidate_name' || k === 'full_name');
            html += `<div class="card"><h2>Raw Results</h2>${data.truncated ? '<p>Showing the first 200 rows.</p>' : ''}<table>
                <thead><tr>${keys.map(k => `<th>${escapeHtml(k)}</th>`).join('')}</tr></thead>
                <tbody>${rows.map(row =>
                    `<tr>${keys.map(k => {
                        const val = row[k] !== null && row[k] !== undefined ? escapeHtml(String(row[k])) : '-';
                        if (hasId && nameKey && k === nameKey && row.id) {
                            return `<td><a href="/candidate.html?id=${encodeURIComponent(row.id)}">${val}</a></td>`;
                        }
                        return `<td>${val}</td>`;
                    }).join('')}</tr>`
                ).join('')}</tbody>
            </table></div>`;
        } else {
            html += '<div class="card"><p>No results found.</p></div>';
        }

        resultsDiv.innerHTML = html;
    } catch (err) {
        showFlash(err.message, 'error');
    } finally {
        spinner.style.display = 'none';
    }
});
