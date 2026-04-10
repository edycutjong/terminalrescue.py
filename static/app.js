const DRONE_PALETTE = {};

function getDroneStyle(did) {
    if (DRONE_PALETTE[did]) return DRONE_PALETTE[did];
    
    // Extract numerical designation from "drone_X"
    const parts = did.split('_');
    const num = parseInt(parts[1]) || 1;
    
    // Group drones into tactical squadrons (e.g. 3 drones per squadron)
    const SQUADRON_SIZE = 3; 
    let squadronIndex = Math.floor((num - 1) / SQUADRON_SIZE); // 0, 1, 2...
    const droneNumber = ((num - 1) % SQUADRON_SIZE) + 1; // 1, 2, 3...
    
    // Hard cap at max 26 different tactical colors mapping A-Z phonetics 
    squadronIndex = squadronIndex % 26;
    
    // Generate organic distinct hex color utilizing golden ratio conjugate PER SQUADRON
    const hue = ((squadronIndex + 1) * 137.508) % 360;
    
    // Map NATO phonetics for readability
    const phonetic = ["ALPHA", "BRAVO", "CHARLIE", "DELTA", "ECHO", "FOXTROT", "GOLF", "HOTEL", "INDIA", "JULIET", "KILO", "LIMA", "MIKE", "NOVEMBER", "OSCAR", "PAPA", "QUEBEC", "ROMEO", "SIERRA", "TANGO", "UNIFORM", "VICTOR", "WHISKEY", "XRAY", "YANKEE", "ZULU"];
    const squadName = phonetic[squadronIndex];
    
    const label = `${squadName}-${droneNumber}`;
    
    DRONE_PALETTE[did] = {
        color: `hsl(${hue}, 80%, 65%)`,
        label: label
    };
    return DRONE_PALETTE[did];
}

let ws;
let grid_x = 10;
let grid_y = 10;
let total_sectors = 100;
let mission_start_time = null;

// Global State
let drone_status = {};
let all_claims = {};
let searched_sectors = [];
let known_hazards = [];
let searchedSet = new Set();
let hazardSet = new Set();

// DOM Elements
const elGrid = document.getElementById('search-grid');
const elDroneList = document.getElementById('drone-list');
const elEventLog = document.getElementById('event-log');
const elTimer = document.getElementById('timer');
const elActiveDrones = document.getElementById('active-drones');
const elProgress = document.getElementById('mission-progress');
const appContainer = document.getElementById('app');

// ==========================================
// 💥 JUICE ENGINE (Game Feel Effects)
// ==========================================
let shakeIntensity = 0;
let shakeDuration = 0;

function screenShake(intensity = 5, duration = 300) {
    shakeIntensity = intensity;
    shakeDuration = duration;
}

function updateShake() {
    if (shakeDuration > 0) {
        const offsetX = (Math.random() - 0.5) * shakeIntensity * 2;
        const offsetY = (Math.random() - 0.5) * shakeIntensity * 2;
        appContainer.style.transform = `translate(${offsetX}px, ${offsetY}px)`;
        shakeDuration -= 16;
        if (shakeDuration <= 0) {
            appContainer.style.transform = 'translate(0, 0)';
        }
    }
}

function flashScreen(color = '#FFFFFF', duration = 100) {
    const flash = document.createElement('div');
    flash.style.cssText = `
    position: fixed; top: 0; left: 0; width: 100vw; height: 100vh;
    background: ${color}; opacity: 0.3; pointer-events: none; z-index: 9999;
    transition: opacity ${duration}ms ease-out;
  `;
    document.body.appendChild(flash);
    requestAnimationFrame(() => { flash.style.opacity = '0'; });
    setTimeout(() => flash.remove(), duration);
}

function scaleBounce(element, scale = 1.1, duration = 200) {
    element.style.transition = `transform ${duration / 2}ms ease-out`;
    element.style.transform = `scale(${scale})`;
    setTimeout(() => {
        element.style.transform = 'scale(1)';
    }, duration / 2);
}

// ==========================================
// ✨ PARTICLE ENGINE (Canvas 2D API)
// ==========================================
const canvas = document.getElementById('particle-canvas');
const ctx = canvas.getContext('2d');
let particles = [];

function resizeCanvas() {
    canvas.width = window.innerWidth;
    canvas.height = window.innerHeight;
    if (typeof updateDronePositions === 'function') {
        updateDronePositions();
    }
}
window.addEventListener('resize', resizeCanvas);
resizeCanvas();

class Particle {
    constructor(x, y, options = {}) {
        this.x = x;
        this.y = y;
        this.vx = options.vx ?? (Math.random() - 0.5) * 6;
        this.vy = options.vy ?? (Math.random() - 0.5) * 6;
        this.life = options.life ?? 1.0;
        this.decay = options.decay ?? 0.02 + Math.random() * 0.02;
        this.size = options.size ?? 2 + Math.random() * 3;
        this.color = options.color ?? '#FFD700';
        this.gravity = options.gravity ?? 0.0;
        this.shrink = options.shrink ?? true;
    }
    update() {
        this.x += this.vx;
        this.y += this.vy;
        this.vy += this.gravity;
        this.life -= this.decay;
    }
    draw(c) {
        if (this.life <= 0) return;
        c.save();
        // Neon additive blending for laser/plasma trails
        c.globalCompositeOperation = 'lighter';
        
        const s = this.shrink ? this.size * this.life : this.size;
        
        // Emissive fake-shadow bloom (virtually zero GPU cost compared to true shadowBlur)
        c.globalAlpha = this.life * 0.3;
        c.fillStyle = this.color;
        c.fillRect(this.x - s * 1.5, this.y - s * 1.5, s * 3, s * 3);
        
        // Core particle
        c.globalAlpha = this.life;
        c.fillRect(this.x - s / 2, this.y - s / 2, s, s);
        c.restore();
    }
}

function emitExplosion(x, y, count = 30) {
    const colors = ['#FF4444', '#FF8800', '#FFDD00', '#FFFFFF'];
    for (let i = 0; i < count; i++) {
        const angle = (Math.PI * 2 * i) / count;
        const speed = 2 + Math.random() * 10;
        particles.push(new Particle(x, y, {
            vx: Math.cos(angle) * speed,
            vy: Math.sin(angle) * speed,
            color: colors[Math.floor(Math.random() * colors.length)],
            size: 3 + Math.random() * 5,
            decay: 0.015 + Math.random() * 0.02,
        }));
    }
}

function emitSparkle(x, y, count = 15, color = '#00d4ff') {
    for (let i = 0; i < count; i++) {
        particles.push(new Particle(x, y, {
            vx: (Math.random() - 0.5) * 4,
            vy: (Math.random() - 0.5) * 4,
            color: color,
            size: 2 + Math.random() * 3,
            decay: 0.03 + Math.random() * 0.02,
        }));
    }
}

// Background data mesh particles
function spawnAmbientParticle() {
    if (Math.random() > 0.3) return;
    particles.push(new Particle(Math.random() * canvas.width, Math.random() * canvas.height, {
        vx: (Math.random() - 0.5) * 0.5,
        vy: -0.5 - Math.random() * 1,
        color: 'rgba(0, 212, 255, 0.4)',
        size: 1 + Math.random() * 2,
        decay: 0.005,
        gravity: 0
    }));
}

function emitDroneTrails() {
    const drones = document.querySelectorAll('.absolute-drone:not(.dead)');
    drones.forEach(d_el => {
        // High frequency micro-particles for speed lines
        if (Math.random() > 0.6) return;
        
        const rect = d_el.getBoundingClientRect();
        
        // Optimize: avoid getComputedStyle which causes layout thrashing
        // Extract original drone_id from DOM ID and pull from internal palette
        const did = d_el.id.replace('drone-dot-', '');
        const color = getDroneStyle(did).color;
        
        const x = rect.left + rect.width / 2;
        const y = rect.top + rect.height / 2;
        
        particles.push(new Particle(x, y, {
            vx: (Math.random() - 0.5) * 1.0,
            vy: (Math.random() - 0.5) * 1.0,
            color: color,
            size: Math.random() * 3 + 1.5,
            decay: 0.03 + Math.random() * 0.03,
            gravity: 0,
            life: 0.7 
        }));
    });
}

function updateParticles() {
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    spawnAmbientParticle();
    emitDroneTrails();
    for (let i = particles.length - 1; i >= 0; i--) {
        particles[i].update();
        particles[i].draw(ctx);
        if (particles[i].life <= 0) particles.splice(i, 1);
    }
    if (particles.length > 500) particles.splice(0, particles.length - 500);
}

let isGridDirty = false;
let isPositionsDirty = false;
let isTelemetryDirty = false;
let isListDirty = false;

// Global Animation Loop
function engineLoop() {
    updateShake();
    updateParticles();
    
    // Batch DOM repaints natively into browser display cycles
    if (isGridDirty) { updateGrid(); isGridDirty = false; }
    if (isPositionsDirty) { updateDronePositions(); isPositionsDirty = false; }
    if (isTelemetryDirty) { updateTelemetry(); isTelemetryDirty = false; }
    if (isListDirty) { renderDrones(); isListDirty = false; }
    
    requestAnimationFrame(engineLoop);
}

// ==========================================
// WebSocket & Logic
// ==========================================
function initWebSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    ws = new WebSocket(`${protocol}//${window.location.host}/ws`);
    ws.onmessage = (event) => handleMessage(JSON.parse(event.data));
    ws.onclose = () => setTimeout(initWebSocket, 1000);
}

function handleMessage(msg) {
    if (msg.type === "INIT_STATE") {
        grid_x = msg.grid_x;
        grid_y = msg.grid_y;
        total_sectors = msg.total_sectors;
        drone_status = msg.drone_status;
        all_claims = msg.all_claims;
        searched_sectors = msg.searched_sectors;
        known_hazards = msg.known_hazards;
        searchedSet = new Set(searched_sectors);
        hazardSet = new Set(known_hazards);
        initGrid();
        isGridDirty = true;
        isPositionsDirty = true;
        isTelemetryDirty = true;
        isListDirty = true;
    } else if (msg.type === "DRONE_STATE") {
        drone_status[msg.drone_id] = msg.data;
        isGridDirty = true;
        isPositionsDirty = true;
        isTelemetryDirty = true;
        isListDirty = true;
    } else if (msg.type === "CLAIMS") {
        all_claims = msg.data;
        isGridDirty = true;
    } else if (msg.type === "SEARCHED_SECTORS") {
        searched_sectors = msg.data;
        searchedSet = new Set(searched_sectors);
        isGridDirty = true;
        isPositionsDirty = true;
        isTelemetryDirty = true;
    } else if (msg.type === "HAZARDS") {
        known_hazards = msg.data;
        hazardSet = new Set(known_hazards);
        isGridDirty = true;
    } else if (msg.type === "EVENT") {
        appendLog(msg.data);
    }
}

// Actions
function killDrone(drone_id) {
    if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ action: "KILL", drone_id: drone_id }));
    }
}

function addHazard(sector) {
    if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ action: "HAZARD", sector: sector }));
    }
    const cellId = `cell-${sector}`;
    const cell = document.getElementById(cellId);
    if (cell) {
        scaleBounce(cell, 1.2, 300);
        const rect = cell.getBoundingClientRect();
        emitSparkle(rect.left + rect.width / 2, rect.top + rect.height / 2, 20, '#ff3333');
    }
}

function initGrid() {
    elGrid.style.gridTemplateColumns = `repeat(${grid_x}, 1fr)`;
    elGrid.style.gridTemplateRows = `repeat(${grid_y}, 1fr)`;
    
    // Maintain aspect ratio natively
    elGrid.style.aspectRatio = `${grid_x} / ${grid_y}`;

    elGrid.innerHTML = '';
    for (let y = 0; y < grid_y; y++) {
        for (let x = 0; x < grid_x; x++) {
            const cell = document.createElement('div');
            cell.className = 'grid-cell';
            cell.id = `cell-${x}_${y}`;
            cell.onclick = () => addHazard(`${x}_${y}`);
            elGrid.appendChild(cell);
        }
    }
}

function updateGrid() {
    for (let y = 0; y < grid_y; y++) {
        for (let x = 0; x < grid_x; x++) {
            const cellId = `cell-${x}_${y}`;
            const cell = document.getElementById(cellId);
            if (!cell) continue;

            const sector = `${x}_${y}`;
            const isHazard = hazardSet.has(sector);
            const isSearched = searchedSet.has(sector);
            const owner = all_claims[sector];

            let nextClass = 'grid-cell';
            let bg = '', bc = '', bs = '';
            let hexColor = '#66ff99';

            if (isHazard) {
                nextClass += ' hazard';
            } else {
                if (owner) {
                    const dinfo = drone_status[owner];
                    if (dinfo && !dinfo.status.includes('OFFLINE')) {
                        nextClass += ' claimed';
                        hexColor = getDroneStyle(owner).color;
                        bc = hexColor;
                        bs = `inset 0 0 10px color-mix(in srgb, ${hexColor} 50%, transparent)`;
                    }
                }

                if (isSearched) {
                    nextClass += ' searched';
                    bg = `color-mix(in srgb, ${hexColor} 25%, transparent)`;

                    // Sparkle animation triggered once when cell flips to searched
                    if (!cell.dataset.wasSearched) {
                        cell.dataset.wasSearched = "true";
                        scaleBounce(cell, 1.1, 200);
                        const rect = cell.getBoundingClientRect();
                        emitSparkle(rect.left + rect.width / 2, rect.top + rect.height / 2, 10, hexColor);
                    }
                }
            }
            
            // Fast cache check: only touch the physical DOM if the underlying properties mutated
            if (cell.className !== nextClass) cell.className = nextClass;
            if (cell.dataset.bg !== bg) { cell.style.background = bg; cell.dataset.bg = bg; }
            if (cell.dataset.bc !== bc) { cell.style.borderColor = bc; cell.dataset.bc = bc; }
            if (cell.dataset.bs !== bs) { cell.style.boxShadow = bs; cell.dataset.bs = bs; }
        }
    }
}

function updateDronePositions() {
    for (const [did, dinfo] of Object.entries(drone_status)) {
        let d_el = document.getElementById(`drone-dot-${did}`);

        if (!d_el) {
            d_el = document.createElement('div');
            d_el.id = `drone-dot-${did}`;
            d_el.className = 'absolute-drone';
            const color = getDroneStyle(did).color;
            d_el.style.backgroundColor = color;
            elGrid.appendChild(d_el);
        }

        const isOffline = dinfo.status.includes('OFFLINE');

        if (isOffline) {
            if (!d_el.classList.contains('dead')) {
                d_el.classList.add('dead');
                // Trigger WOW explosion right at its last known coordinates
                const color = getDroneStyle(did).color;
                const x = parseFloat(d_el.style.left) + (parseFloat(d_el.style.width) / 2);
                const y = parseFloat(d_el.style.top) + (parseFloat(d_el.style.height) / 2);
                if (!isNaN(x) && !isNaN(y)) {
                    triggerExplosion(x, y, color);
                }

                // Add a permanent burnt crater to the specific tile!
                if (dinfo.pos) {
                    const deadCell = document.getElementById(`cell-${dinfo.pos.x}_${dinfo.pos.y}`);
                    if (deadCell) {
                        deadCell.classList.add('crater');
                    }
                }
            }
        } else if (dinfo.pos) {
            d_el.classList.remove('dead');
            const cell = document.getElementById(`cell-${dinfo.pos.x}_${dinfo.pos.y}`);
            if (cell) {
                const currentLeft = parseFloat(d_el.style.left);
                const currentTop = parseFloat(d_el.style.top);
                const targetLeft = cell.offsetLeft;
                const targetTop = cell.offsetTop;

                if (!isNaN(currentLeft) && !isNaN(currentTop)) {
                    // Constant physical velocity implementation
                    const dist = Math.sqrt(Math.pow(targetLeft - currentLeft, 2) + Math.pow(targetTop - currentTop, 2));
                    if (dist > 1) {
                        // Simulate drone top speed at 350px/sec 
                        const velocityPxPerSec = 350;
                        const durationSec = Math.max(0.15, dist / velocityPxPerSec);

                        // S-Curve Physics Easing (Start slow -> Fast middle -> Slow down at target)
                        const easing = 'cubic-bezier(0.65, 0, 0.35, 1)';
                        d_el.style.transition = `left ${durationSec}s ${easing}, top ${durationSec}s ${easing}, opacity 0.4s`;
                    }
                } else {
                    // Very first spawn cycle, don't transition
                    d_el.style.transition = `opacity 0.4s`;
                }

                d_el.style.left = targetLeft + 'px';
                d_el.style.top = targetTop + 'px';
                d_el.style.width = cell.offsetWidth + 'px';
                d_el.style.height = cell.offsetHeight + 'px';
            }
        }
    }
}

function renderDrones() {
    const sortedIds = Object.keys(drone_status).sort();

    sortedIds.forEach(did => {
        const dinfo = drone_status[did];
        const pal = getDroneStyle(did);
        const isOffline = dinfo.status.includes('OFFLINE');

        let claimedCount = 0;
        for (const owner of Object.values(all_claims)) if (owner === did) claimedCount++;
        const searchedCount = dinfo.searched ? dinfo.searched.length : 0;

        let el = document.getElementById(`drone-card-${did}`);
        const wasOffline = el ? el.classList.contains('offline') : false;

        if (!el) {
            el = document.createElement('div');
            el.id = `drone-card-${did}`;
            elDroneList.appendChild(el);
            el.innerHTML = `
                <div class="drone-header">
                    <span class="drone-name" style="color: ${pal.color}">◆ ${pal.label}</span>
                    <button class="btn-kill" id="btn-kill-${did}" onclick="killDrone('${did}')">KILL</button>
                </div>
                <div class="drone-status" id="status-${did}"></div>
                <div class="drone-stats">
                    <span id="claims-${did}"></span>
                    <span id="searched-${did}"></span>
                </div>
            `;
        }

        el.className = `drone-card ${isOffline ? 'offline' : ''}`;

        const btn = document.getElementById(`btn-kill-${did}`);
        if (btn) {
            btn.disabled = isOffline;
            btn.innerText = isOffline ? 'DEAD' : 'KILL';
        }

        const statusEl = document.getElementById(`status-${did}`);
        if (statusEl) {
            statusEl.innerText = dinfo.status;
            statusEl.style.color = isOffline ? '#ff3333' : '#e2e8f0';
        }

        const claimsEl = document.getElementById(`claims-${did}`);
        if (claimsEl) claimsEl.innerText = `Claims: ${claimedCount}`;

        const searchedEl = document.getElementById(`searched-${did}`);
        if (searchedEl) searchedEl.innerText = `Searched: ${searchedCount}`;

        if (isOffline && !wasOffline) {
            screenShake(15, 350);
            flashScreen('#ff3333', 200);
            const rect = el.getBoundingClientRect();
            emitExplosion(rect.left + rect.width / 2, rect.top + rect.height / 2, 40);
        }
    });
}

function updateTelemetry() {
    let active = 0;
    for (const dinfo of Object.values(drone_status)) if (!dinfo.status.includes('OFFLINE')) active++;

    elActiveDrones.innerText = `${active}/${Object.keys(drone_status).length}`;
    elActiveDrones.style.color = active === 0 ? 'var(--color-red)' : 'var(--color-green)';

    const pct = total_sectors ? (searched_sectors.length / total_sectors) * 100 : 0;
    elProgress.innerText = `${Math.floor(pct)}%`;
    if (pct >= 100) elProgress.style.color = 'var(--color-green)';
    if (searched_sectors.length > 0 && mission_start_time === null) mission_start_time = Date.now();
}

function appendLog(evt) {
    const el = document.createElement('div');
    el.className = 'log-entry';
    let color = '#fff';
    switch (evt.type) {
        case 'HELLO': color = 'var(--color-green)'; break;
        case 'CLAIM': color = 'var(--color-cyan)'; break;
        case 'RELEASE': color = 'var(--color-red)'; break;
        case 'SEARCH': color = 'var(--color-green)'; break;
        case 'KILL': color = 'var(--color-red)'; break;
        case 'HAZARD': color = 'orange'; break;
        case 'SYSTEM': color = 'var(--color-cyan)'; break;
    }
    el.innerHTML = `<span class="log-time">${evt.time}</span> <span style="color: ${color}">[${evt.type}]</span> ${evt.text}`;
    elEventLog.prepend(el);
}

setInterval(() => {
    if (mission_start_time !== null && searched_sectors.length < total_sectors) {
        const elapsed = Math.floor((Date.now() - mission_start_time) / 1000);
        const m = String(Math.floor(elapsed / 60)).padStart(2, '0');
        const s = String(elapsed % 60).padStart(2, '0');
        elTimer.innerText = `${m}:${s}`;

        // Winning confetti
        if (searched_sectors.length === total_sectors) {
            flashScreen('#66ff99', 500);
            for (let i = 0; i < 5; i++) setTimeout(() => emitExplosion(window.innerWidth * Math.random(), window.innerHeight / 2 * Math.random(), 50), i * 200);
        }
    }
}, 1000);

function hideBriefing() {
    const modal = document.getElementById('briefing-modal');
    if (modal) {
        modal.style.opacity = '0';
        setTimeout(() => modal.style.display = 'none', 300);
    }
    // Awaken the swarm!
    if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ action: "START" }));
    }
}
function showBriefing() {
    const modal = document.getElementById('briefing-modal');
    if (modal) {
        modal.style.display = 'flex';
        // force layout
        void modal.offsetWidth;
        modal.style.opacity = '1';
    }
}

// Particle Explosion Factory
function triggerExplosion(x, y, color) {
    const parent = document.querySelector('.search-grid');
    if (!parent) return;

    // 1. Core white flash
    const flash = document.createElement('div');
    flash.className = 'explosion-flash';
    flash.style.left = x + 'px';
    flash.style.top = y + 'px';
    flash.style.boxShadow = `0 0 30px 10px ${color}, inset 0 0 20px #fff`;
    parent.appendChild(flash);
    setTimeout(() => flash.remove(), 500);

    // 2. Shrapnel particles
    for (let i = 0; i < 18; i++) {
        const p = document.createElement('div');
        p.className = 'dom-particle';
        p.style.backgroundColor = color;
        p.style.boxShadow = `0 0 8px ${color}`;
        p.style.left = x + 'px';
        p.style.top = y + 'px';

        const angle = Math.random() * Math.PI * 2;
        // Explosive force between 20px and 120px
        const speed = Math.random() * 100 + 20;
        const tx = Math.cos(angle) * speed;
        const ty = Math.sin(angle) * speed;

        p.style.setProperty('--tx', `${tx}px`);
        p.style.setProperty('--ty', `${ty}px`);

        parent.appendChild(p);
        setTimeout(() => p.remove(), 600);
    }
}

// Start
requestAnimationFrame(engineLoop);
initWebSocket();

// Keyboard shortcuts
window.addEventListener('keydown', (e) => {
    const modal = document.getElementById('briefing-modal');
    // Check if modal is visible (not explicitly hidden)
    if (modal && modal.style.display !== 'none') {
        if (e.code === 'Space' || e.code === 'Enter') {
            e.preventDefault(); // Prevent spacebar scroll
            hideBriefing();
        }
    }
});
