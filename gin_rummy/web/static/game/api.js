// The game API client.
import { elements } from './dom.js';

export const API_BASE = '/api/game';

// API calls
export async function apiCall(endpoint, method = 'GET', body = null) {
    const options = {
        method,
        headers: { 'Content-Type': 'application/json' },
    };

    if (body) {
        options.body = JSON.stringify(body);
    }

    const response = await fetch(`${API_BASE}${endpoint}`, options);
    const data = await response.json();

    if (!response.ok) {
        console.error('API error:', data);
        // FastAPI puts error messages in 'detail'; session errors use 'error'
        elements.playerStatus.textContent = data.detail || data.error || 'An error occurred';
        return null;
    }

    return data;
}
