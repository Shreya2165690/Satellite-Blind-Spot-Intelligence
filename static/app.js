
const map = L.map("map").setView([17.68, 74.02], 11);

L.tileLayer(
    "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
    {
        maxZoom: 19,
        attribution: "© OpenStreetMap"
    }
).addTo(map);

// Polygon and rectangle selection
const drawn = new L.FeatureGroup();
map.addLayer(drawn);

map.addControl(
    new L.Control.Draw({
        draw: {
            polygon: {
                allowIntersection: false,
                showArea: true
            },
            rectangle: true,
            polyline: false,
            circle: false,
            circlemarker: false,
            marker: false
        },
        edit: {
            featureGroup: drawn
        }
    })
);

let selected = null;

map.on(L.Draw.Event.CREATED, (event) => {
    drawn.clearLayers();
    drawn.addLayer(event.layer);

    selected = event.layer.toGeoJSON().geometry;

    setStatus(
        "Area selected. Keep the polygon inside Satara Taluka."
    );
});

map.on(L.Draw.Event.EDITED, () => {
    drawn.eachLayer((layer) => {
        selected = layer.toGeoJSON().geometry;
    });
});

map.on(L.Draw.Event.DELETED, () => {
    selected = null;
});

document.getElementById("clear").onclick = () => {
    drawn.clearLayers();
    selected = null;
    setStatus("Selection cleared.");
};

// Year selection: Sentinel-2 L2A starts in 2017.
const year1 = document.getElementById("year1");
const year2 = document.getElementById("year2");

const currentYear = new Date().getFullYear();

for (let year = 2017; year <= currentYear; year++) {
    year1.add(new Option(year, year));
    year2.add(new Option(year, year));
}

year1.value = "2017";
year2.value = currentYear >= 2021 ? "2021" : String(currentYear);

// Cloud slider
const cloud = document.getElementById("cloud");

cloud.oninput = (event) => {
    document.getElementById("cloudLabel").textContent =
        event.target.value + "%";
};

// Helpers
function setStatus(message) {
    document.getElementById("status").textContent = message;
}

function escapeHTML(value) {
    return String(value ?? "").replace(/[&<>"']/g, (character) => {
        const replacements = {
            "&": "&amp;",
            "<": "&lt;",
            ">": "&gt;",
            '"': "&quot;",
            "'": "&#39;"
        };

        return replacements[character];
    });
}

function payload() {
    if (!selected) {
        throw new Error("Please draw a polygon on the map first.");
    }

    return {
        geometry: selected
    };
}

async function post(url, data) {
    const response = await fetch(url, {
        method: "POST",
        headers: {
            "Content-Type": "application/json"
        },
        body: JSON.stringify(data)
    });

    const result = await response.json();

    if (!response.ok) {
        throw new Error(result.error || "Request failed.");
    }

    return result;
}

function setButtonsDisabled(disabled) {
    document.getElementById("scenes").disabled = disabled;
    document.getElementById("analyze").disabled = disabled;
}

// Scene details
function sceneSummary(result) {
    const scenes = result.scenes || [];

    if (!scenes.length) {
        return `<p>No suitable Sentinel-2 scenes found for ${escapeHTML(result.year)}.</p>`;
    }

    return `
        <h3>${escapeHTML(result.year)} — ${result.count} scenes</h3>
        <div class="scene-list">
            ${scenes.slice(0, 10).map(scene => `
                <div class="finding">
                    <b>${escapeHTML(scene.date || "Date unavailable")}</b>
                    <span> · Cloud: ${escapeHTML(scene.cloud_cover ?? "Unknown")}%</span>
                    <small> · ${escapeHTML(scene.platform || "Sentinel-2")}</small>
                </div>
            `).join("")}
        </div>
    `;
}

// Find scenes button
document.getElementById("scenes").onclick = async () => {
    try {
        const p = payload();

        setButtonsDisabled(true);
        setStatus("Searching the Sentinel-2 L2A catalogue...");

        const [earlier, later] = await Promise.all([
            post("/api/scenes", {
                ...p,
                year: Number(year1.value)
            }),
            post("/api/scenes", {
                ...p,
                year: Number(year2.value)
            })
        ]);

        const resultArea = document.getElementById("results");

        resultArea.innerHTML = `
            <div class="panel-head">
                <div>
                    <p class="eyebrow">SCENE DISCOVERY</p>
                    <h2>Available satellite observations</h2>
                </div>
                <span class="tag">SENTINEL-2 L2A</span>
            </div>
            ${sceneSummary(earlier)}
            ${sceneSummary(later)}
        `;

        setStatus(
            `${earlier.year}: ${earlier.count} scenes. ` +
            `${later.year}: ${later.count} scenes.`
        );

    } catch (error) {
        setStatus(error.message);

    } finally {
        setButtonsDisabled(false);
    }
};

// Run comparison button
document.getElementById("analyze").onclick = async () => {
    try {
        const p = payload();

        setButtonsDisabled(true);

        setStatus(
            "Retrieving real satellite imagery and calculating spectral indices. Please wait..."
        );

        const result = await post("/api/analyze", {
            ...p,
            year1: Number(year1.value),
            year2: Number(year2.value),
            max_cloud: Number(cloud.value),
            area_name:
                document.getElementById("areaName").value.trim() ||
                "Selected Satara study area"
        });

        render(result);

        if (result.status === "completed") {
            setStatus("Analysis completed and saved.");
        } else {
            setStatus(result.message || "No suitable satellite data found.");
        }

        await loadHistory();

    } catch (error) {
        setStatus(error.message);

    } finally {
        setButtonsDisabled(false);
    }
};

// Render analysis results
function render(result) {
    const element = document.getElementById("results");

    if (result.status !== "completed") {
        element.innerHTML = `
            <div class="panel-head">
                <div>
                    <p class="eyebrow">03 / INVESTIGATION OUTPUT</p>
                    <h2>Change intelligence</h2>
                </div>
                <span class="tag">NO DATA</span>
            </div>
            <p class="warning">${escapeHTML(result.message)}</p>
        `;
        return;
    }

    const metrics = result.metrics;

    const cards = [
        ["Vegetation proxy", metrics.vegetation_percent],
        ["Built-up proxy", metrics.built_up_proxy_percent],
        ["Water proxy", metrics.water_proxy_percent]
    ];

    const scene1 = result.scenes.earlier;
    const scene2 = result.scenes.later;

    element.innerHTML = `
        <div class="panel-head">
            <div>
                <p class="eyebrow">03 / INVESTIGATION OUTPUT</p>
                <h2>Change intelligence</h2>
            </div>
            <span class="tag">ANALYSIS ${escapeHTML(result.analysis_id)}</span>
        </div>

        <h3>Satellite scenes used</h3>

        <div class="finding">
            <b>${escapeHTML(result.years.earlier)}</b>:
            ${escapeHTML(scene1.date)}
            · Cloud cover: ${escapeHTML(scene1.cloud_cover)}%
        </div>

        <div class="finding">
            <b>${escapeHTML(result.years.later)}</b>:
            ${escapeHTML(scene2.date)}
            · Cloud cover: ${escapeHTML(scene2.cloud_cover)}%
        </div>

        <div class="cards">
            ${cards.map(([name, value]) => `
                <div class="metric">
                    <small>${escapeHTML(name)}</small>
                    <h2>
                        ${value.change_pp > 0 ? "+" : ""}
                        ${escapeHTML(value.change_pp)} pp
                    </h2>
                    <p>
                        ${escapeHTML(result.years.earlier)}:
                        ${escapeHTML(value.earlier)}%
                        →
                        ${escapeHTML(result.years.later)}:
                        ${escapeHTML(value.later)}%
                    </p>
                </div>
            `).join("")}
        </div>

        <p class="warning">
            Valid pixel coverage:
            ${escapeHTML(result.valid_coverage_percent)}%.
            ${escapeHTML(result.blind_spots.warning)}
        </p>

        <h3>Findings</h3>

        ${result.findings.map(item => `
            <div class="finding">${escapeHTML(item)}</div>
        `).join("")}

        <h3>Data quality and limitations</h3>

        ${result.limitations.map(item => `
            <div class="finding">• ${escapeHTML(item)}</div>
        `).join("")}

        <p>
            <a target="_blank" rel="noopener"
               href="/api/report/${encodeURIComponent(result.analysis_id)}">
                Open printable investigation report ↗
            </a>
        </p>
    `;
}

// Database history
async function loadHistory() {
    try {
        const response = await fetch("/api/history");

        if (!response.ok) {
            throw new Error("History could not be loaded.");
        }

        const records = await response.json();

        const element = document.getElementById("history");

        if (!records.length) {
            element.textContent = "No saved analyses yet.";
            return;
        }

        element.innerHTML = records.map(record => `
            <div class="history-row">
                <span>
                    ${escapeHTML(record.area_name)}
                    · ${escapeHTML(record.start_year)}
                    vs ${escapeHTML(record.end_year)}
                </span>
                <span>
                    ${escapeHTML(record.created_at)}
                    · ${escapeHTML(record.status)}
                    · <a href="/api/report/${encodeURIComponent(record.id)}">
                        Report
                    </a>
                </span>
            </div>
        `).join("");

    } catch (error) {
        document.getElementById("history").textContent =
            "History is temporarily unavailable.";
    }
}

document.getElementById("refresh").onclick = loadHistory;

loadHistory();
