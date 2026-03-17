/* ════════════════════════════════════════════════════════════
   Trinidad Incident Intelligence Map — Main JavaScript
   Map, Charts, Filters, and Interactivity
   ════════════════════════════════════════════════════════════ */

// ─── Map Initialization ──────────────────────────────────────
function initMap() {
    const mapEl = document.getElementById('incident-map');
    if (!mapEl) return;

    // Center on Trinidad & Tobago
    const map = L.map('incident-map', {
        zoomControl: false,
    }).setView([10.45, -61.25], 9);

    const lightLayer = L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png', {
        attribution: '&copy; <a href="https://carto.com/">CARTO</a> | &copy; <a href="https://osm.org/copyright">OSM</a>',
        subdomains: 'abcd',
        maxZoom: 19,
    });
    const darkLayer = L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
        attribution: '&copy; <a href="https://carto.com/">CARTO</a> | &copy; <a href="https://osm.org/copyright">OSM</a>',
        subdomains: 'abcd',
        maxZoom: 19,
    });
    const satelliteLayer = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', {
        attribution: '&copy; <a href="https://www.esri.com/">Esri</a>',
        maxZoom: 19,
    });

    lightLayer.addTo(map);
    window._activeBaseLayer = lightLayer;

    L.control.layers(
        { 'Light': lightLayer, 'Dark': darkLayer, 'Satellite': satelliteLayer },
        null,
        { position: 'bottomright' }
    ).addTo(map);

    map.on('baselayerchange', function (e) {
        window._activeBaseLayer = e.layer;
    });

    // Zoom control bottom-left
    L.control.zoom({ position: 'bottomleft' }).addTo(map);

    // Load incidents
    loadIncidents(map);

    // Store map reference for filters
    window._incidentMap = map;
    window._incidentLayer = null;
}

function loadIncidents(map) {
    const params = new URLSearchParams();

    const catFilter = document.getElementById('filter-category');
    const sevFilter = document.getElementById('filter-severity');
    const regFilter = document.getElementById('filter-region');
    const timeFilter = document.getElementById('filter-time');
    const dateFrom = document.getElementById('filter-date-from');
    const dateTo = document.getElementById('filter-date-to');

    if (catFilter && catFilter.value) params.set('category', catFilter.value);
    if (sevFilter && sevFilter.value) params.set('severity', sevFilter.value);
    if (regFilter && regFilter.value) params.set('region', regFilter.value);
    if (timeFilter && timeFilter.value) params.set('time_range', timeFilter.value);
    if (dateFrom && dateFrom.value) params.set('date_from', dateFrom.value);
    if (dateTo && dateTo.value) params.set('date_to', dateTo.value);

    const url = `/api/incidents/geojson/?${params.toString()}`;

    fetch(url)
        .then(response => response.json())
        .then(data => {
            // Remove old layers
            if (window._incidentLayer) map.removeLayer(window._incidentLayer);
            if (window._heatLayer) map.removeLayer(window._heatLayer);

            if (window._currentMapView === 'heatmap') {
                // Prepare heatmap data: [lat, lng, intensity]
                const heatData = data.features.map(f => {
                    const lat = f.geometry.coordinates[1];
                    const lng = f.geometry.coordinates[0];
                    // Intensity based on severity
                    const sev = f.properties.severity;
                    const intensity = sev === 'critical' ? 1.0 : (sev === 'high' ? 0.8 : (sev === 'medium' ? 0.5 : 0.3));
                    return [lat, lng, intensity];
                });

                window._heatLayer = L.heatLayer(heatData, {
                    radius: 25,
                    blur: 15,
                    maxZoom: 14,
                    gradient: {0.4: 'blue', 0.6: 'cyan', 0.7: 'lime', 0.8: 'yellow', 1.0: 'red'}
                }).addTo(map);
            } else {
                // Category → color mapping
                const colorMap = {
                    'shooting': '#dc2626',
                    'murder': '#991b1b',
                    'violent_crime': '#ef4444',
                    'robbery': '#f97316',
                    'assault': '#ea580c',
                    'kidnapping': '#b91c1c',
                    'traffic_accident': '#eab308',
                    'vehicle_collision': '#ca8a04',
                    'pedestrian_accident': '#a16207',
                    'fire': '#3b82f6',
                    'flood': '#6366f1',
                    'natural_disaster': '#8b5cf6',
                    'police_activity': '#06b6d4',
                    'drug_related': '#d946ef',
                    'domestic_violence': '#e11d48',
                    'fraud': '#14b8a6',
                    'other': '#6b7280',
                };

                const geoJsonLayer = L.geoJSON(data, {
                    pointToLayer: function (feature, latlng) {
                        const color = feature.properties.category_color || colorMap[feature.properties.category] || '#6b7280';
                        return L.circleMarker(latlng, {
                            radius: feature.properties.severity === 'critical' ? 10 :
                                    feature.properties.severity === 'high' ? 8 : 6,
                            fillColor: color,
                            color: color,
                            weight: 2,
                            opacity: 0.9,
                            fillOpacity: 0.6,
                        });
                    },
                    onEachFeature: function (feature, layer) {
                        const p = feature.properties;
                        layer.bindTooltip(p.incident_type || 'Incident', { direction: 'top', offset: [0, -8] });
                        const dateStr = p.incident_date ? new Date(p.incident_date).toLocaleDateString('en-TT', {
                            year: 'numeric', month: 'short', day: 'numeric'
                        }) : 'Unknown date';
                        const imgHtml = p.image_url
                            ? `<div class="popup-thumb" style="margin-bottom:8px;"><img src="${escapeHtml(p.image_url)}" alt="" style="max-width:100%;max-height:120px;border-radius:4px;display:block;" loading="lazy" /></div>`
                            : '';

                        let enrichHtml = '';
                        const parts = [];
                        if (p.victim_count > 0) parts.push(`Victims: ${p.victim_count}`);
                        if (p.fatality_count > 0) parts.push(`Fatalities: ${p.fatality_count}`);
                        if (p.weapon) parts.push(`Weapon: ${escapeHtml(p.weapon)}`);
                        if (p.incident_time) parts.push(`Time: ${escapeHtml(p.incident_time)}`);
                        if (parts.length) {
                            enrichHtml = `<div style="font-size:11px;color:#f59e0b;margin-top:4px;padding:4px 6px;background:rgba(245,158,11,.08);border-radius:4px;">${parts.join(' &middot; ')}</div>`;
                        }

                        const popup = `
                            ${imgHtml}
                            <div class="popup-title">${escapeHtml(p.incident_type)}</div>
                            <div class="popup-location">📍 ${escapeHtml(p.location_name || 'Unknown')} — ${escapeHtml(p.region_display)}</div>
                            <div class="popup-desc">${escapeHtml(p.description)}</div>
                            ${enrichHtml}
                            <div class="popup-meta">
                                <span class="badge badge-${p.severity}">${p.severity}</span>
                                <span class="badge badge-category">${escapeHtml(p.category_display)}</span>
                            </div>
                            <div style="font-size:11px;color:#94a3b8;margin-top:6px;">${dateStr} ${p.source_name ? '&middot; ' + escapeHtml(p.source_name) : ''}</div>
                            <div style="display:flex;gap:8px;margin-top:6px;">
                                <a href="/incidents/${p.id}/" class="popup-link" style="flex:1;">Incident Details</a>
                                ${p.article_id ? `<a href="/articles/${p.article_id}/" class="popup-link" style="flex:1;text-align:right;color:#94a3b8;">Article</a>` : ''}
                            </div>
                        `;
                        layer.bindPopup(popup, { maxWidth: 320 });
                    }
                });

                if (typeof L.markerClusterGroup === 'function') {
                    window._incidentLayer = L.markerClusterGroup({
                        chunkedLoading: true,
                        maxClusterRadius: 50,
                        spiderfyOnMaxZoom: true,
                    });
                    geoJsonLayer.eachLayer(function (layer) {
                        window._incidentLayer.addLayer(layer);
                    });
                    window._incidentLayer.addTo(map);
                } else {
                    window._incidentLayer = geoJsonLayer.addTo(map);
                }
            }

            // Update counter badge
            const countBadge = document.getElementById('map-incident-count-badge');
            if (countBadge) {
                const n = data.features.length;
                countBadge.textContent = n === 1 ? '1 Incident Mapped' : `${n} Incidents Mapped`;
            }
        })
        .catch(err => console.error('Error loading incidents:', err));
}

function applyMapFilters() {
    if (window._incidentMap) {
        loadIncidents(window._incidentMap);
    }
}

function focusMapOnHotspot(event, region) {
    if (event) event.preventDefault();
    const regionSelect = document.getElementById('filter-region');
    if (regionSelect) {
        regionSelect.value = region || '';
        applyMapFilters();
    }
}

function clearMapFilters() {
    const selects = document.querySelectorAll('.map-filter-panel select');
    const inputs = document.querySelectorAll('.map-filter-panel input[type="date"]');
    selects.forEach(s => s.value = '');
    inputs.forEach(i => i.value = '');
    applyMapFilters();
}

function toggleMapFullscreen() {
    const container = document.querySelector('.map-container');
    if (!container) return;
    if (!document.fullscreenElement) {
        container.requestFullscreen().then(() => {
            container.classList.add('fullscreen');
            if (window._incidentMap) window._incidentMap.invalidateSize();
        }).catch(() => {});
    } else {
        document.exitFullscreen().then(() => {
            container.classList.remove('fullscreen');
            if (window._incidentMap) window._incidentMap.invalidateSize();
        }).catch(() => {});
    }
}

document.addEventListener('fullscreenchange', function () {
    const container = document.querySelector('.map-container');
    if (container && !document.fullscreenElement) {
        container.classList.remove('fullscreen');
        if (window._incidentMap) window._incidentMap.invalidateSize();
    }
});

function exportCSV(e) {
    if (e) e.preventDefault();
    const params = new URLSearchParams();
    
    const catFilter = document.getElementById('filter-category');
    const sevFilter = document.getElementById('filter-severity');
    const regFilter = document.getElementById('filter-region');
    const timeFilter = document.getElementById('filter-time');
    const dateFrom = document.getElementById('filter-date-from');
    const dateTo = document.getElementById('filter-date-to');

    if (catFilter && catFilter.value) params.set('category', catFilter.value);
    if (sevFilter && sevFilter.value) params.set('severity', sevFilter.value);
    if (regFilter && regFilter.value) params.set('region', regFilter.value);
    if (timeFilter && timeFilter.value) params.set('time_range', timeFilter.value);
    if (dateFrom && dateFrom.value) params.set('date_from', dateFrom.value);
    if (dateTo && dateTo.value) params.set('date_to', dateTo.value);

    window.location.href = `/api/incidents/export/?${params.toString()}`;
}

// ─── Dashboard Operations Widgets ───────────────────────────

function dashTriggerScrape() {
    const btn = document.getElementById('btn-dash-scrape');
    if (!btn) return;
    
    const srcSelect = document.getElementById('target-source-select');
    const sourceId = srcSelect ? srcSelect.value : '';
    
    btn.disabled = true;
    btn.textContent = '⏱️ Scraping...';
    
    const payload = sourceId ? JSON.stringify({ source_id: sourceId }) : '{}';
    
    fetch('/api/pipeline/scrape/', { 
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: payload
    })
    .then(r => r.json())
    .then(data => {
        showToast(data.message, data.status === 'started' ? 'success' : 'info');
        setTimeout(() => {
            btn.disabled = false;
            btn.textContent = '📡 Scrape';
        }, 3000);
    })
    .catch(e => {
        showToast('Scrape request failed.', 'error');
        btn.disabled = false;
        btn.textContent = '📡 Scrape';
    });
}

function dashTriggerExtract() {
    const btn = document.getElementById('btn-dash-extract');
    if (!btn) return;
    
    btn.disabled = true;
    btn.textContent = '⏱️ Extracting...';
    fetch('/api/pipeline/extract/', { method: 'POST' })
    .then(r => r.json())
    .then(data => {
        showToast(data.message, data.status === 'started' ? 'success' : 'info');
        setTimeout(() => {
            btn.disabled = false;
            btn.textContent = '🤖 Trigger AI Extract';
        }, 3000);
    })
    .catch(e => {
        showToast('Extract request failed.', 'error');
        btn.disabled = false;
        btn.textContent = '🤖 Trigger AI Extract';
    });
}

// ─── Analytics Charts ────────────────────────────────────────
function destroyChart(canvas) {
    if (typeof Chart === 'undefined' || !Chart.getChart) return;
    var existing = Chart.getChart(canvas);
    if (existing) existing.destroy();
}

function initCharts() {
    initSparklineChart();
    initHomeCategoryChart();
    initCategoryChart();
    initRegionChart();
    initTrendChart();
    initSeverityChart();
    initVolumeChart();
    initTopSourcesChart();
}

function initSparklineChart() {
    const el = document.getElementById('chart-sparkline');
    if (!el) return;
    destroyChart(el);

    const values = JSON.parse(el.dataset.values || '[]');
    const labels = ['D-6', 'D-5', 'D-4', 'D-3', 'D-2', 'Yesterday', 'Today'];

    new Chart(el, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [{
                data: values,
                borderColor: '#374151',
                backgroundColor: 'rgba(55, 65, 81, 0.05)',
                fill: true,
                tension: 0.4,
                pointRadius: 0,
                pointHoverRadius: 4,
                borderWidth: 2,
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { display: false }, tooltip: { enabled: true } },
            scales: {
                x: { display: false },
                y: { display: false, min: 0 }
            },
            layout: { padding: 0 }
        }
    });
}

function initHomeCategoryChart() {
    const el = document.getElementById('chart-home-category');
    if (!el) return;
    destroyChart(el);

    const labels = JSON.parse(el.dataset.labels || '[]');
    const values = JSON.parse(el.dataset.values || '[]');

    new Chart(el, {
        type: 'doughnut',
        data: {
            labels: labels,
            datasets: [{
                data: values,
                backgroundColor: [
                    '#ef4444', '#f97316', '#eab308', '#3b82f6',
                    '#8b5cf6', '#06b6d4', '#10b981', '#ec4899',
                    '#d946ef', '#14b8a6', '#6366f1', '#f43f5e',
                    '#a855f7', '#0ea5e9', '#84cc16', '#64748b'
                ],
                borderColor: '#ffffff',
                borderWidth: 1,
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'bottom',
                    labels: { font: { size: 10 }, boxWidth: 10, padding: 6 }
                }
            },
            cutout: '60%',
        }
    });
}

function initCategoryChart() {
    const el = document.getElementById('chart-category');
    if (!el) return;
    destroyChart(el);

    const labels = JSON.parse(el.dataset.labels || '[]');
    const values = JSON.parse(el.dataset.values || '[]');

    new Chart(el, {
        type: 'doughnut',
        data: {
            labels: labels,
            datasets: [{
                data: values,
                backgroundColor: [
                    '#ef4444', '#f97316', '#eab308', '#3b82f6',
                    '#8b5cf6', '#06b6d4', '#10b981', '#ec4899',
                    '#d946ef', '#14b8a6', '#6366f1', '#f43f5e',
                    '#a855f7', '#0ea5e9', '#84cc16', '#64748b'
                ],
                borderColor: '#ffffff',
                borderWidth: 2,
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'right',
                    labels: {
                        color: '#94a3b8',
                        font: { family: 'Inter', size: 11 },
                        padding: 10,
                        boxWidth: 12,
                        boxHeight: 12,
                        borderRadius: 3,
                    }
                }
            },
            cutout: '65%',
        }
    });
}

function initRegionChart() {
    const el = document.getElementById('chart-region');
    if (!el) return;
    destroyChart(el);

    const labels = JSON.parse(el.dataset.labels || '[]');
    const values = JSON.parse(el.dataset.values || '[]');

    new Chart(el, {
        type: 'bar',
        data: {
            labels: labels,
            datasets: [{
                label: 'Incidents',
                data: values,
                backgroundColor: 'rgba(59, 130, 246, 0.6)',
                borderColor: '#3b82f6',
                borderWidth: 1,
                borderRadius: 4,
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            indexAxis: 'y',
            plugins: {
                legend: { display: false },
            },
            scales: {
                x: {
                    grid: { color: 'rgba(148,163,184,0.06)' },
                    ticks: { color: '#64748b', font: { family: 'Inter', size: 10 } },
                },
                y: {
                    grid: { display: false },
                    ticks: { color: '#94a3b8', font: { family: 'Inter', size: 11 } },
                }
            }
        }
    });
}

function initTrendChart() {
    const el = document.getElementById('chart-trend');
    if (!el) return;
    destroyChart(el);

    const labels = JSON.parse(el.dataset.labels || '[]');
    const values = JSON.parse(el.dataset.values || '[]');

    new Chart(el, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [{
                label: 'Daily Incidents',
                data: values,
                borderColor: '#3b82f6',
                backgroundColor: 'rgba(59, 130, 246, 0.08)',
                fill: true,
                tension: 0.4,
                pointRadius: 2,
                pointHoverRadius: 5,
                pointBackgroundColor: '#3b82f6',
                borderWidth: 2,
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false },
            },
            scales: {
                x: {
                    grid: { color: 'rgba(148,163,184,0.06)' },
                    ticks: {
                        color: '#64748b',
                        font: { family: 'Inter', size: 10 },
                        maxRotation: 45,
                        maxTicksLimit: 15,
                    },
                },
                y: {
                    beginAtZero: true,
                    grid: { color: 'rgba(148,163,184,0.06)' },
                    ticks: {
                        color: '#64748b',
                        font: { family: 'Inter', size: 10 },
                        stepSize: 1,
                    },
                }
            }
        }
    });
}

function initSeverityChart() {
    const el = document.getElementById('chart-severity');
    if (!el) return;
    destroyChart(el);

    const labels = JSON.parse(el.dataset.labels || '[]');
    const values = JSON.parse(el.dataset.values || '[]');

    new Chart(el, {
        type: 'polarArea',
        data: {
            labels: labels,
            datasets: [{
                data: values,
                backgroundColor: [
                    'rgba(59, 130, 246, 0.5)',
                    'rgba(245, 158, 11, 0.5)',
                    'rgba(249, 115, 22, 0.5)',
                    'rgba(239, 68, 68, 0.5)',
                ],
                borderColor: [
                    '#3b82f6', '#f59e0b', '#f97316', '#ef4444',
                ],
                borderWidth: 1,
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'right',
                    labels: {
                        color: '#94a3b8',
                        font: { family: 'Inter', size: 11 },
                        padding: 10,
                    }
                }
            },
            scales: {
                r: {
                    grid: { color: 'rgba(148,163,184,0.08)' },
                    ticks: { display: false },
                }
            }
        }
    });
}

function initVolumeChart() {
    const el = document.getElementById('chart-volume');
    if (!el) return;
    destroyChart(el);

    const labels = JSON.parse(el.dataset.labels || '[]');
    const values = JSON.parse(el.dataset.values || '[]');

    new Chart(el, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [{
                label: 'Articles Scraped',
                data: values,
                borderColor: '#107c41',
                backgroundColor: 'rgba(16, 124, 65, 0.08)',
                fill: true,
                tension: 0.4,
                pointRadius: 2,
                pointHoverRadius: 5,
                pointBackgroundColor: '#107c41',
                borderWidth: 2,
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { display: false } },
            scales: {
                x: {
                    grid: { color: 'rgba(148,163,184,0.06)' },
                    ticks: { color: '#64748b', font: { family: 'Inter', size: 10 }, maxRotation: 45, maxTicksLimit: 15 },
                },
                y: {
                    beginAtZero: true,
                    grid: { color: 'rgba(148,163,184,0.06)' },
                    ticks: { color: '#64748b', font: { family: 'Inter', size: 10 } },
                }
            }
        }
    });
}

function initTopSourcesChart() {
    const el = document.getElementById('chart-sources');
    if (!el) return;
    destroyChart(el);

    const labels = JSON.parse(el.dataset.labels || '[]');
    const values = JSON.parse(el.dataset.values || '[]');

    new Chart(el, {
        type: 'bar',
        data: {
            labels: labels,
            datasets: [{
                label: 'Incidents',
                data: values,
                backgroundColor: 'rgba(107, 114, 128, 0.6)',
                borderColor: '#4b5563',
                borderWidth: 1,
                borderRadius: 4,
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            indexAxis: 'y',
            plugins: { legend: { display: false } },
            scales: {
                x: {
                    grid: { color: 'rgba(148,163,184,0.06)' },
                    ticks: { color: '#64748b', font: { family: 'Inter', size: 10 }, stepSize: 1 },
                },
                y: {
                    grid: { display: false },
                    ticks: { color: '#4b5563', font: { family: 'Inter', size: 11, weight: 500 } },
                }
            }
        }
    });
}

// ─── Detail Map ──────────────────────────────────────────────
function initDetailMap(lat, lng, title) {
    const mapEl = document.getElementById('detail-map');
    if (!mapEl || !lat || !lng) return;

    const map = L.map('detail-map').setView([lat, lng], 14);

    L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png', {
        attribution: '&copy; CARTO | &copy; OSM',
        subdomains: 'abcd',
        maxZoom: 19,
    }).addTo(map);

    L.circleMarker([lat, lng], {
        radius: 10,
        fillColor: '#ef4444',
        color: '#ef4444',
        weight: 3,
        fillOpacity: 0.5,
    }).addTo(map).bindPopup(title).openPopup();
}

// ─── Admin Actions ───────────────────────────────────────────
function moderateIncident(id, action) {
    fetch(`/api/incidents/${id}/moderate/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: action }),
    })
    .then(r => r.json())
    .then(data => {
        if (data.status === 'ok') {
            // Update row visually
            const row = document.getElementById(`incident-row-${id}`);
            if (row) {
                const badge = row.querySelector('.status-badge');
                if (badge) {
                    badge.className = `badge status-badge badge-${data.new_status}`;
                    badge.textContent = data.new_status;
                }
                // Fade out after a moment
                setTimeout(() => {
                    row.style.opacity = '0.4';
                }, 300);
            }
        }
    })
    .catch(err => console.error('Moderation error:', err));
}

// ─── Mobile Sidebar ──────────────────────────────────────────
function toggleSidebar() {
    const sidebar = document.querySelector('.sidebar');
    if (sidebar) sidebar.classList.toggle('open');
}

// ─── Utilities ───────────────────────────────────────────────
function exportTableToCSV(filename) {
    const table = document.querySelector('.data-table');
    if (!table) return;

    let csv = [];
    // Get headers
    const cols = table.querySelectorAll('thead th');
    let row = [];
    for (let i = 0; i < cols.length; i++) {
        if (cols[i].innerText.trim() !== 'Actions' && cols[i].innerText.trim() !== '') {
            row.push('"' + cols[i].innerText.replace(/"/g, '""') + '"');
        }
    }
    csv.push(row.join(','));

    // Get rows
    const trs = table.querySelectorAll('tbody tr');
    for (let i = 0; i < trs.length; i++) {
        const tds = trs[i].querySelectorAll('td');
        if (tds.length === 1 && trs[i].innerText.includes('No incidents')) continue; // Skip empty state row

        let row = [];
        for (let j = 0; j < tds.length; j++) {
            // Skip the actions column (usually the last column or specifically named in headers)
            if (cols[j] && (cols[j].innerText.trim() === 'Actions' || cols[j].innerText.trim() === '')) continue;

            let text = tds[j].innerText.replace(/[\n\r]+/g, ' ').trim(); // Replace newlines with spaces
            row.push('"' + text.replace(/"/g, '""') + '"');
        }
        if (row.length > 0) csv.push(row.join(','));
    }

    // Download
    const csvFile = new Blob([csv.join('\n')], {type: 'text/csv'});
    const downloadLink = document.createElement('a');
    downloadLink.download = filename;
    downloadLink.href = window.URL.createObjectURL(csvFile);
    downloadLink.style.display = 'none';
    document.body.appendChild(downloadLink);
    downloadLink.click();
    document.body.removeChild(downloadLink);
}

function escapeHtml(text) {
    if (!text) return '';
    const map = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;' };
    return text.replace(/[&<>"']/g, m => map[m]);
}

// ─── Init on DOM ready ──────────────────────────────────────
document.addEventListener('DOMContentLoaded', function() {
    initMap();

    // Charts (only if Chart.js is loaded)
    if (typeof Chart !== 'undefined') {
        Chart.defaults.font.family = 'Inter';
        Chart.defaults.color = '#4b5563';
        initCharts();
    }
});
