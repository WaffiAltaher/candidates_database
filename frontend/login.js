// If already logged in, redirect
if (getToken()) {
    window.location.href = '/index.html';
}

document.getElementById('login-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const errorEl = document.getElementById('error-msg');
    errorEl.style.display = 'none';
    const username = document.getElementById('username').value;
    const password = document.getElementById('password').value;
    try {
        const data = await api(API.auth + '/login', {
            method: 'POST',
            body: { username, password },
            redirectOn401: false,
        });
        if (data && data.token) {
            setToken(data.token);
            window.location.href = '/index.html';
        }
    } catch (err) {
        errorEl.textContent = err.message;
        errorEl.style.display = 'block';
    }
});
