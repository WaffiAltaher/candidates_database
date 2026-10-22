if (!requireAuth()) throw new Error('redirect');

const params = new URLSearchParams(window.location.search);
const candidateId = params.get('id');
if (!candidateId) { window.location.href = '/index.html'; throw new Error('redirect'); }

let currentCandidate = null;

function closeModal() {
    document.getElementById('interview-modal').classList.remove('active');
}

function openAddInterview() {
    document.getElementById('modal-title').textContent = 'Add Interview';
    document.getElementById('modal-submit-btn').textContent = 'Add';
    document.getElementById('iv-edit-id').value = '';
    const interviews = currentCandidate.interviews || [];
    document.getElementById('iv-number').value = interviews.length + 1;
    document.getElementById('iv-date').value = '';
    document.getElementById('iv-interviewer').value = '';
    document.getElementById('iv-comments').value = '';
    document.getElementById('iv-verdict').value = '';
    document.getElementById('interview-modal').classList.add('active');
}

function openEditInterviewById(id) {
    const iv = (currentCandidate.interviews || []).find(i => i.id === id);
    if (iv) openEditInterview(iv);
}

function openEditInterview(iv) {
    document.getElementById('modal-title').textContent = 'Edit Interview';
    document.getElementById('modal-submit-btn').textContent = 'Update';
    document.getElementById('iv-edit-id').value = iv.id;
    document.getElementById('iv-number').value = iv.interview_number;
    document.getElementById('iv-date').value = iv.interview_date || '';
    document.getElementById('iv-interviewer').value = iv.interviewer_name;
    document.getElementById('iv-comments').value = iv.comments || '';
    document.getElementById('iv-verdict').value = iv.verdict || '';
    document.getElementById('interview-modal').classList.add('active');
}

document.getElementById('interview-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const editId = document.getElementById('iv-edit-id').value;
    const payload = {
        interview_number: parseInt(document.getElementById('iv-number').value),
        interview_date: document.getElementById('iv-date').value || null,
        interviewer_name: document.getElementById('iv-interviewer').value,
        comments: document.getElementById('iv-comments').value,
        verdict: document.getElementById('iv-verdict').value || null,
    };
    try {
        if (editId) {
            await api(API.candidates + `/interviews/${editId}`, { method: 'PUT', body: payload });
        } else {
            await api(API.candidates + `/candidates/${candidateId}/interviews`, { method: 'POST', body: payload });
        }
        closeModal();
        loadCandidate();
    } catch (err) {
        showFlash(err.message, 'error');
    }
});

async function deleteInterview(id) {
    if (!confirm('Delete this interview?')) return;
    try {
        await api(API.candidates + `/interviews/${id}`, { method: 'DELETE' });
        loadCandidate();
    } catch (err) {
        showFlash(err.message, 'error');
    }
}

async function saveVerdict() {
    const verdict = document.getElementById('verdict-input').value;
    try {
        await api(API.candidates + `/candidates/${candidateId}/final-verdict`, {
            method: 'POST', body: { final_verdict: verdict || null },
        });
        showFlash('Final verdict updated.', 'success');
    } catch (err) {
        showFlash(err.message, 'error');
    }
}

async function addCustomer() {
    const input = document.getElementById('customer-input');
    const name = input.value.trim();
    if (!name) return;
    try {
        await api(API.candidates + `/candidates/${candidateId}/proposed-customers`, {
            method: 'POST', body: { customer_name: name },
        });
        input.value = '';
        loadCandidate();
    } catch (err) {
        showFlash(err.message, 'error');
    }
}

async function deleteCustomer(id) {
    try {
        await api(API.candidates + `/proposed-customers/${id}`, { method: 'DELETE' });
        loadCandidate();
    } catch (err) {
        showFlash(err.message, 'error');
    }
}

async function loadCandidate() {
    try {
        const data = await api(API.candidates + `/candidates/${candidateId}`);
        if (!data) return;
        currentCandidate = data.candidate;
        renderCandidate(currentCandidate);
    } catch (err) {
        document.getElementById('content').innerHTML = `<div class="card"><p>Error: ${escapeHtml(err.message)}</p></div>`;
    }
}

function renderCandidate(c) {
    const techs = (c.technologies || []).map(t => `<span class="tag">${escapeHtml(t)}</span>`).join('');

    const experiences = (c.experiences || []).map(exp => `
        <div style="margin-bottom: 1rem; padding-bottom: 1rem; border-bottom: 1px solid #eee;">
            <strong>${escapeHtml(exp.role) || 'Role not specified'}</strong> at <strong>${escapeHtml(exp.company) || 'Company not specified'}</strong>
            <br><small style="color: #666;">${escapeHtml(exp.start_date) || '?'} - ${escapeHtml(exp.end_date) || '?'}</small>
            ${exp.description ? `<p style="margin-top: 0.5rem;">${escapeHtml(exp.description)}</p>` : ''}
        </div>
    `).join('');

    const customers = (c.proposed_customers || []).map(pc => `
        <span class="tag tag-removable">
            ${escapeHtml(pc.customer_name)}
            <button data-action="delete-customer" data-id="${Number(pc.id)}" title="Remove">&times;</button>
        </span>
    `).join('');

    const interviewRows = (c.interviews || []).map(iv => `
        <tr>
            <td>${escapeHtml(iv.interview_number)}</td>
            <td>${escapeHtml(iv.interview_date) || '-'}</td>
            <td>${escapeHtml(iv.interviewer_name)}</td>
            <td>${escapeHtml(iv.verdict) || '-'}</td>
            <td>${escapeHtml(iv.comments) || '-'}</td>
            <td class="actions">
                <button class="btn btn-primary btn-sm" data-action="edit-interview" data-id="${Number(iv.id)}">Edit</button>
                <button class="btn btn-danger btn-sm" data-action="delete-interview" data-id="${Number(iv.id)}">Delete</button>
            </td>
        </tr>
    `).join('');

    document.getElementById('content').innerHTML = `
        <h1>${escapeHtml(c.name)}</h1>

        <div class="card">
            <h2>Profile</h2>
            <dl class="detail-grid">
                <dt>Job Title</dt><dd>${escapeHtml(c.job_title) || '-'}</dd>
                <dt>Years Experience</dt><dd>${escapeHtml(c.years_experience) || '-'}</dd>
                <dt>University</dt><dd>${escapeHtml(c.university) || '-'}</dd>
                <dt>Degree Field</dt><dd>${escapeHtml(c.degree_field) || '-'}</dd>
                <dt>Date of Birth</dt><dd>${escapeHtml(c.date_of_birth) || '-'}</dd>
            </dl>
        </div>

        <div class="card">
            <h2>Final Verdict</h2>
            <div class="inline-form">
                <input type="text" id="verdict-input" value="${escapeHtml(c.final_verdict) || ''}" placeholder="Enter final verdict">
                <button class="btn btn-primary" data-action="save-verdict">Save</button>
            </div>
        </div>

        <div class="card">
            <div class="section-header">
                <h2>Proposed to Customers</h2>
            </div>
            <div style="margin-bottom: 1rem;">
                ${customers || '<p>No customers yet.</p>'}
            </div>
            <div class="inline-form">
                <input type="text" id="customer-input" placeholder="Customer name">
                <button class="btn btn-success" data-action="add-customer">Add</button>
            </div>
        </div>

        <div class="card">
            <h2>Technologies</h2>
            ${techs || '<p>No technologies listed.</p>'}
        </div>

        <div class="card">
            <h2>Work Experience</h2>
            ${experiences || '<p>No work experience listed.</p>'}
        </div>

        <div class="card">
            <div class="section-header">
                <h2>Interviews</h2>
                <button class="btn btn-primary" data-action="add-interview">Add Interview</button>
            </div>
            ${(c.interviews || []).length > 0 ? `
            <table>
                <thead>
                    <tr><th>#</th><th>Date</th><th>Interviewer</th><th>Verdict</th><th>Comments</th><th>Actions</th></tr>
                </thead>
                <tbody>${interviewRows}</tbody>
            </table>` : '<p>No interviews recorded yet.</p>'}
        </div>

        <a href="/index.html">&larr; Back to candidates</a>
    `;
}

loadCandidate();

document.getElementById('modal-cancel-btn').addEventListener('click', closeModal);

document.getElementById('content').addEventListener('click', (e) => {
    const btn = e.target.closest('[data-action]');
    if (!btn) return;
    const id = Number(btn.dataset.id);
    switch (btn.dataset.action) {
        case 'delete-customer': deleteCustomer(id); break;
        case 'edit-interview': openEditInterviewById(id); break;
        case 'delete-interview': deleteInterview(id); break;
        case 'save-verdict': saveVerdict(); break;
        case 'add-customer': addCustomer(); break;
        case 'add-interview': openAddInterview(); break;
    }
});
