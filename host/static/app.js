"use strict";

const config = JSON.parse(document.getElementById("config-data").textContent);
const CHART_POINTS = config.CHART_POINTS || 200;
const MAX_CAR_LOGS = 500;

const socket = io();

socket.on("connect", () => {
    console.log("[WS] connected");
    socket.emit("get_status");
});

socket.on("disconnect", () => {
    console.log("[WS] disconnected");
});

const chartColors = [
    "#6bd6d0", "#e4b363", "#82d173", "#f36b5f",
    "#7ca8ff", "#c48cff", "#d9e76c", "#f18f9f",
];

function makeChart(canvasId, datasets) {
    const canvas = document.getElementById(canvasId);
    return new Chart(canvas.getContext("2d"), {
        type: "line",
        data: {
            labels: Array(CHART_POINTS).fill(""),
            datasets: datasets.map((ds, i) => ({
                label: ds.label,
                data: Array(CHART_POINTS).fill(null),
                borderColor: ds.color || chartColors[i % chartColors.length],
                backgroundColor: "transparent",
                borderWidth: 1.6,
                pointRadius: 0,
                tension: 0.26,
            })),
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            animation: false,
            interaction: { intersect: false, mode: "nearest" },
            plugins: {
                legend: {
                    labels: { color: "#a49f90", boxWidth: 10, font: { size: 10 } },
                },
            },
            scales: {
                x: {
                    display: false,
                    grid: { color: "rgba(255,255,255,0.06)" },
                },
                y: {
                    grid: { color: "rgba(255,255,255,0.06)" },
                    ticks: { color: "#767266", font: { size: 10 } },
                },
            },
        },
    });
}

const chartAdc = makeChart(
    "chart-adc",
    Array.from({ length: 8 }, (_, i) => ({ label: `AD${i}`, color: chartColors[i] }))
);
const chartError = makeChart("chart-error", [
    { label: "le", color: "#6bd6d0" },
    { label: "po", color: "#e4b363" },
]);
const chartGyro = makeChart("chart-gyro", [
    { label: "gz", color: "#82d173" },
]);
const chartEncoder = makeChart("chart-encoder", [
    { label: "el", color: "#7ca8ff" },
    { label: "er", color: "#f36b5f" },
]);

function pushData(chart, values) {
    values.forEach((value, index) => {
        const dataset = chart.data.datasets[index];
        if (!dataset) return;
        dataset.data.push(value);
        if (dataset.data.length > CHART_POINTS) dataset.data.shift();
    });
    chart.update("none");
}

let frameCount = 0;

socket.on("telemetry", (tele) => {
    frameCount += 1;
    document.getElementById("frame-counter").textContent = `帧: ${frameCount}`;

    pushData(chartAdc, tele.adc || []);
    pushData(chartError, [tele.le, tele.po]);
    pushData(chartGyro, [tele.gz]);
    pushData(chartEncoder, [tele.el, tele.er]);

    const stateMap = {
        ID: "空闲",
        LF: "循迹",
        RA: "直角弯",
        LL: "丢线",
        SL: "起点",
        CR: "十字",
        FN: "完成",
    };
    document.getElementById("track-state").textContent =
        `状态: ${stateMap[tele.st] || tele.st || "-"}`;
});

socket.on("client_status", (data) => {
    const el = document.getElementById("car-status");
    if (data.connected) {
        el.textContent = `小车: 已连接 ${data.addr}`;
        el.className = "status-pill status-connected";
    } else {
        el.textContent = "小车: 未连接";
        el.className = "status-pill status-disconnected";
    }
});

socket.on("status", (data) => {
    document.getElementById("engine-info").textContent = `引擎: ${data.engine}`;
    if (typeof data.frame_count === "number" && data.frame_count > frameCount) {
        document.getElementById("frame-counter").textContent = `帧: ${data.frame_count}`;
    }
});

document.querySelectorAll(".param-slider").forEach((slider) => {
    const name = slider.dataset.name;
    const input = document.querySelector(`.param-input[data-name="${name}"]`);
    slider.addEventListener("input", () => {
        input.value = slider.value;
    });
    input.addEventListener("input", () => {
        slider.value = input.value;
    });
});

function collectParams() {
    const params = {};
    document.querySelectorAll(".param-input").forEach((input) => {
        const value = Number.parseFloat(input.value);
        if (!Number.isNaN(value)) params[input.dataset.name] = value;
    });
    return params;
}

document.getElementById("btn-apply").addEventListener("click", () => {
    const params = collectParams();
    socket.emit("send_params", params);
    console.log("[SEND] params:", params);
});

function sendCmd(cmd) {
    if (["start", "stop"].includes(cmd) && !confirm(`确认发送指令: ${cmd}?`)) return;
    socket.emit("send_cmd", { cmd });
    console.log("[SEND] cmd:", cmd);
}

document.getElementById("btn-start").addEventListener("click", () => sendCmd("start"));
document.getElementById("btn-stop").addEventListener("click", () => sendCmd("stop"));
document.getElementById("btn-whitecal").addEventListener("click", () => sendCmd("whitecal"));
document.getElementById("btn-blackcal").addEventListener("click", () => sendCmd("blackcal"));
document.getElementById("btn-reconnect").addEventListener("click", () => sendCmd("reconnect"));

let lastSuggestion = null;

document.getElementById("btn-analyze").addEventListener("click", () => {
    const btn = document.getElementById("btn-analyze");
    btn.disabled = true;
    btn.textContent = "分析中";
    socket.emit("ai_analyze");
});

socket.on("ai_result", (data) => {
    const btn = document.getElementById("btn-analyze");
    const box = document.getElementById("ai-result");
    btn.disabled = false;
    btn.textContent = "分析";

    if (data.error) {
        box.innerHTML = `<p class="error">错误: ${data.error}</p>`;
        lastSuggestion = null;
        document.getElementById("btn-adopt").disabled = true;
        return;
    }

    lastSuggestion = data;
    const params = data.params || {};
    const paramsText = Object.keys(params).length ? JSON.stringify(params, null, 2) : "无需调整";
    box.innerHTML = `
        <div class="params">建议参数:<pre></pre></div>
        <div class="reason"></div>
        <div class="confidence"></div>
    `;
    box.querySelector("pre").textContent = paramsText;
    box.querySelector(".reason").textContent = data.reason || "";
    box.querySelector(".confidence").textContent =
        `置信度: ${(data.confidence || 0).toFixed(2)} | 引擎: ${data.engine || "?"}`;
    document.getElementById("btn-adopt").disabled = Object.keys(params).length === 0;
});

document.getElementById("btn-adopt").addEventListener("click", () => {
    if (!lastSuggestion || !lastSuggestion.params) return;
    for (const [name, value] of Object.entries(lastSuggestion.params)) {
        const input = document.querySelector(`.param-input[data-name="${name}"]`);
        const slider = document.querySelector(`.param-slider[data-name="${name}"]`);
        if (input) input.value = value;
        if (slider) slider.value = value;
    }
});

socket.on("params_update", (params) => {
    for (const [name, value] of Object.entries(params)) {
        const input = document.querySelector(`.param-input[data-name="${name}"]`);
        const slider = document.querySelector(`.param-slider[data-name="${name}"]`);
        if (input) input.value = value;
        if (slider) slider.value = value;
    }
});

socket.on("log", (entry) => {
    const box = document.getElementById("log-box");
    const div = document.createElement("div");
    div.className = `log-${entry.level}`;
    div.textContent = `[${entry.time}] ${entry.msg}`;
    box.appendChild(div);
    box.scrollTop = box.scrollHeight;
    while (box.children.length > 200) box.removeChild(box.firstChild);
});

const carLogBox = document.getElementById("car-log-box");
const carLogCount = document.getElementById("car-log-count");
const carLogFilter = document.getElementById("car-log-filter");
const carLogAutoscroll = document.getElementById("car-log-autoscroll");
const carLogPauseBtn = document.getElementById("btn-car-log-pause");
const carLogClearBtn = document.getElementById("btn-car-log-clear");
const carLogExportBtn = document.getElementById("btn-car-log-export");

let carLogs = [];
let carLogPaused = false;

function normalizeLogLevel(level, line) {
    const textLevel = String(level || "").toLowerCase();
    if (["error", "assert"].includes(textLevel)) return "error";
    if (["warning", "warn"].includes(textLevel)) return "warning";
    if (["debug", "trace", "verbose"].includes(textLevel)) return "debug";
    if (/\b(error|err|fail|fault)\b/i.test(line) || /^E\//.test(line)) return "error";
    if (/\b(warn|warning)\b/i.test(line) || /^W\//.test(line)) return "warning";
    if (/\b(debug|trace)\b/i.test(line) || /^D\//.test(line)) return "debug";
    return "info";
}

function appendCarLog(entry) {
    const line = entry.line || entry.msg || "";
    const message = entry.msg || line;
    const time = entry.time || new Date().toLocaleTimeString("zh-CN", { hour12: false });
    const level = normalizeLogLevel(entry.level, line);
    const tag = entry.tag || "";
    const mcuTime = entry.mcu_time || "";
    const row = document.createElement("div");
    row.className = `log-line level-${level}`;
    row.dataset.raw = `${time} ${entry.level || level} ${tag} ${mcuTime} ${line}`.toLowerCase();

    const timeEl = document.createElement("span");
    timeEl.className = "log-time";
    timeEl.textContent = time;

    const levelEl = document.createElement("span");
    levelEl.className = "log-level";
    levelEl.textContent = (entry.level || level).toUpperCase().slice(0, 4);

    const tagEl = document.createElement("span");
    tagEl.className = "log-tag";
    tagEl.textContent = tag || "-";

    const mcuEl = document.createElement("span");
    mcuEl.className = "log-mcu";
    mcuEl.textContent = mcuTime ? `${mcuTime}ms` : "-";

    const msgEl = document.createElement("span");
    msgEl.className = "log-message";
    msgEl.textContent = message;

    row.append(timeEl, levelEl, tagEl, mcuEl, msgEl);
    carLogBox.appendChild(row);
}

function applyCarLogFilter() {
    const needle = carLogFilter.value.trim().toLowerCase();
    [...carLogBox.children].forEach((row) => {
        row.classList.toggle("is-hidden", Boolean(needle) && !row.dataset.raw.includes(needle));
    });
}

function renderCarLogs() {
    carLogBox.replaceChildren();
    carLogs.forEach(appendCarLog);
    applyCarLogFilter();
    carLogCount.textContent = `${carLogs.length} 行`;
    if (carLogAutoscroll.checked) carLogBox.scrollTop = carLogBox.scrollHeight;
}

socket.on("car_log", (entry) => {
    carLogs.push(entry);
    if (carLogs.length > MAX_CAR_LOGS) carLogs.shift();
    carLogCount.textContent = `${carLogs.length} 行`;
    if (!carLogPaused) {
        appendCarLog(entry);
        while (carLogBox.children.length > MAX_CAR_LOGS) {
            carLogBox.removeChild(carLogBox.firstChild);
        }
        applyCarLogFilter();
        if (carLogAutoscroll.checked) carLogBox.scrollTop = carLogBox.scrollHeight;
    }
});

carLogFilter.addEventListener("input", applyCarLogFilter);

carLogPauseBtn.addEventListener("click", () => {
    carLogPaused = !carLogPaused;
    carLogPauseBtn.textContent = carLogPaused ? "继续" : "暂停";
    if (!carLogPaused) renderCarLogs();
});

carLogClearBtn.addEventListener("click", () => {
    carLogs = [];
    renderCarLogs();
});

carLogExportBtn.addEventListener("click", () => {
    const text = carLogs.map((entry) => `[${entry.time || ""}] ${entry.line || ""}`).join("\n");
    const blob = new Blob([text], { type: "text/plain;charset=utf-8" });
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = `esp01s-log-${new Date().toISOString().replace(/[:.]/g, "-")}.txt`;
    link.click();
    URL.revokeObjectURL(link.href);
});

const PRESETS = {
    conservative: {
        KP: 3.0, KI: 0.0, KD: 2.0, GDAMP: 0.20,
        VBASE: 30, VSTR: 40, VCUR: 20, RATHR: 2.5,
    },
    balanced: {
        KP: 5.0, KI: 0.0, KD: 1.0, GDAMP: 0.15,
        VBASE: 40, VSTR: 50, VCUR: 30, RATHR: 2.5,
    },
    aggressive: {
        KP: 8.0, KI: 0.0, KD: 0.5, GDAMP: 0.10,
        VBASE: 60, VSTR: 70, VCUR: 45, RATHR: 3.0,
    },
};

document.querySelectorAll(".btn-preset").forEach((btn) => {
    btn.addEventListener("click", () => {
        const params = PRESETS[btn.dataset.preset];
        if (!params) return;
        if (!confirm(`加载 ${btn.textContent} 预设？参数只填入面板，不自动下发。`)) return;
        for (const [name, value] of Object.entries(params)) {
            const slider = document.querySelector(`.param-slider[data-name="${name}"]`);
            const input = document.querySelector(`.param-input[data-name="${name}"]`);
            if (slider) slider.value = value;
            if (input) input.value = value;
        }
    });
});

const btnAutoStart = document.getElementById("btn-auto-start");
const btnAutoStop = document.getElementById("btn-auto-stop");
const autoStatusEl = document.getElementById("auto-status");
const autoRoundsLog = document.getElementById("auto-rounds-log");

btnAutoStart.addEventListener("click", () => {
    const interval = Number.parseFloat(document.getElementById("auto-interval").value) || 5;
    const maxRounds = Number.parseInt(document.getElementById("auto-rounds").value, 10) || 10;
    if (!confirm(`启动自动调参？AI 将每 ${interval} 秒分析并下发参数。`)) return;
    socket.emit("auto_tuning_start", { interval, max_rounds: maxRounds });
    btnAutoStart.disabled = true;
    btnAutoStop.disabled = false;
    autoRoundsLog.replaceChildren();
});

btnAutoStop.addEventListener("click", () => {
    socket.emit("auto_tuning_stop");
});

socket.on("auto_tuning_status", (data) => {
    if (data.active) {
        autoStatusEl.innerHTML = `<span class="status-active">第${data.rounds}轮 ${data.status || "running"}</span>`;
        btnAutoStart.disabled = true;
        btnAutoStop.disabled = false;
        return;
    }

    let summary = `<span class="status-done">已结束（共${data.rounds}轮）</span>`;
    if (data.snapshots && data.snapshots.length > 0) {
        summary += `<div class="snapshot-summary">`;
        data.snapshots.forEach((snapshot) => {
            const params = JSON.stringify(snapshot.params_suggested || {});
            summary += `<div class="snapshot-row">R${snapshot.round}: ${params} (conf=${snapshot.confidence.toFixed(2)})</div>`;
        });
        summary += `</div>`;
    }
    autoStatusEl.innerHTML = summary;
    btnAutoStart.disabled = false;
    btnAutoStop.disabled = true;
});

socket.on("auto_tuning_round", (snapshot) => {
    const div = document.createElement("div");
    div.className = "round-entry";
    const params = JSON.stringify(snapshot.params_suggested || {});
    div.innerHTML =
        `<span class="round-num">R${snapshot.round}</span> ` +
        `<span class="round-params"></span> ` +
        `<span class="round-conf">conf=${snapshot.confidence.toFixed(2)}</span>`;
    div.querySelector(".round-params").textContent = params || "无需调整";
    autoRoundsLog.appendChild(div);
    autoRoundsLog.scrollTop = autoRoundsLog.scrollHeight;
    while (autoRoundsLog.children.length > 50) autoRoundsLog.removeChild(autoRoundsLog.firstChild);
});

setInterval(() => {
    socket.emit("get_status");
}, 2000);

console.log("[INIT] host frontend ready");
