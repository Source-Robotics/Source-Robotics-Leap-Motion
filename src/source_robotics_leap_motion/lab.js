const token = document.querySelector("meta[name=local-session]").content,
  $ = (id) => document.getElementById(id);
let data = null,
  online = false,
  busy = false,
  requestError = "",
  keyClutch = false,
  actionChain = Promise.resolve(),
  trail = [],
  lastSequence = -1;
const reasons = {
  not_armed: "Place your hand, then arm to capture a reference.",
  armed: "Hand movement is mapped from your calibrated reference.",
  clutch_engaged: "Target held. Reposition your hand, then resume.",
  waiting_for_reanchor:
    "Waiting for a fresh hand frame to capture a new reference.",
  clutch_reanchored: "Reference updated. Movement resumes from the held pose.",
  hand_missing: "Hand tracking lost. Place your hand and arm again.",
  hand_changed: "A different hand was detected. Arm again to calibrate.",
  tracking_gap: "Tracking paused. Arm again when frames are fresh.",
  stale_frame: "Frames expired. Fresh tracking and rearming are required.",
  disconnected: "Controller disconnected. Reconnect tracking, then arm again.",
  source_gap: "Source timing changed. Arm again to calibrate.",
  source_clock_reset: "Source clock restarted. Arm again to calibrate.",
  source_changed: "Tracking source changed. Arm again to calibrate.",
  disarmed: "Session disarmed. Arm to capture a fresh reference.",
};
function action(name) {
  actionChain = actionChain.then(async () => {
    try {
      const r = await fetch("/action", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Source-Leap-Token": token,
        },
        body: JSON.stringify({ action: name }),
      });
      if (!r.ok) throw Error((await r.json()).error);
      requestError = "";
      $("message").textContent = "";
    } catch (e) {
      requestError = e.message;
      $("message").textContent = e.message;
    }
  });
  return actionChain;
}
function toggleClutch() {
  if (data) action(data.state === "clutched" ? "resume" : "clutch");
}
document.addEventListener("keydown", (e) => {
  if (e.code === "Escape") {
    action("disarm");
    keyClutch = false;
  }
  if (e.code === "Space") {
    e.preventDefault();
    if (online && !e.repeat && data?.state === "active") {
      keyClutch = true;
      action("clutch");
    }
  }
});
document.addEventListener("keyup", (e) => {
  if (e.code === "Space" && keyClutch) {
    e.preventDefault();
    keyClutch = false;
    action("resume");
  }
});
window.addEventListener("blur", () => {
  if (keyClutch) {
    keyClutch = false;
    action("disarm");
  }
});
async function poll() {
  if (busy) return;
  busy = true;
  try {
    const response = await fetch("/state", { cache: "no-store" });
    if (!response.ok) throw Error("Session unavailable");
    const next = await response.json();
    if (!next.robot) return;
    data = next;
    online = true;
    update();
  } catch (e) {
    online = false;
    $("connection").textContent = "Session ended";
    $("connection-dot").className = "dot";
    $("state").textContent = "OFFLINE";
    $("state").className = "badge";
    $("reason").textContent =
      "The lab connection ended. Restart the command and reload this page.";
    $("arm").disabled = $("clutch").disabled = $("disarm").disabled = true;
  } finally {
    busy = false;
  }
}
function update() {
  const d = data,
    t = d.tracking,
    c = d.control,
    p = d.robot.pose.position;
  $("connection").textContent = "Local session";
  $("connection-dot").className = "dot on";
  $("source").textContent = d.source;
  $("hand-label").textContent = d.hand
    ? `${d.handedness} hand · #${d.hand.id}`
    : `No ${d.handedness} hand visible`;
  $("fps").textContent = t.received_fps.toFixed(0);
  $("age").textContent =
    t.last_frame_age_s === null ? "—" : (t.last_frame_age_s * 1000).toFixed(0);
  $("state").textContent = d.state.replaceAll("_", " ").toUpperCase();
  $("state").className = "badge " + d.state;
  $("reason").textContent = reasons[d.reason] || d.reason.replaceAll("_", " ");
  $("message").textContent = d.message || requestError;
  $("arm").disabled =
    !["disarmed", "tracking_lost"].includes(d.state) ||
    !d.hand ||
    t.status !== "streaming";
  $("clutch").disabled = !["active", "clutched"].includes(d.state);
  $("clutch").textContent =
    d.state === "clutched"
      ? "Resume · re-anchor hand"
      : "Clutch · reposition hand";
  $("disarm").disabled = ["closed", "fault"].includes(d.state);
  for (const a of ["x", "y", "z"])
    $(a).innerHTML = p[a].toFixed(3) + "<small>m</small>";
  $("sequence").textContent = c.sequence;
  const limited = c.workspace_limited || c.speed_limited;
  $("limit").textContent = c.workspace_limited
    ? "Workspace limit applied"
    : c.speed_limited
      ? "Speed limit applied"
      : d.state === "active"
        ? "Following calibrated hand"
        : "Output held";
  $("limit").className = limited ? "limit" : "";
  $("grip").style.width = (d.robot.gripper ?? 0) * 100 + "%";
  $("grip-label").textContent =
    d.robot.gripper === null
      ? "Not controlled"
      : Math.round(d.robot.gripper * 100) + "% open";
  $("mapping").replaceChildren();
  const rotation = d.config.mapping.rotation;
  $("frame-rotation").textContent =
    !rotation ||
    Math.abs(rotation.x) + Math.abs(rotation.y) + Math.abs(rotation.z) < 1e-9
      ? "Frame rotation: identity"
      : "Frame rotation (xyzw): " +
        [rotation.x, rotation.y, rotation.z, rotation.w]
          .map((value) => value.toFixed(3))
          .join(", ");
  d.config.mapping.axes.forEach((axis, i) => {
    const row = document.createElement("div");
    row.className = "mapping-row";
    const label = document.createElement("span");
    label.className = "axis";
    label.textContent = axis.toUpperCase() + " → " + ["X", "Y", "Z"][i];
    const gain = document.createElement("span");
    gain.className = "gain";
    gain.textContent = Object.values(d.config.mapping.gain)[i].toFixed(2) + "×";
    row.append(label, gain);
    $("mapping").append(row);
  });
  if (c.sequence !== lastSequence) {
    lastSequence = c.sequence;
    if (c.sequence === 0) trail = [];
    trail.push({ ...p });
    if (trail.length > 240) trail.shift();
  }
}
const canvas = $("scene"),
  ctx = canvas.getContext("2d");
let yaw = -0.75,
  pitch = 0.55,
  zoom = 1,
  drag = null;
canvas.addEventListener("pointerdown", (e) => {
  drag = { x: e.clientX, y: e.clientY };
  canvas.setPointerCapture(e.pointerId);
});
canvas.addEventListener("pointermove", (e) => {
  if (drag) {
    yaw += (e.clientX - drag.x) * 0.008;
    pitch = Math.max(0.15, Math.min(1.3, pitch + (e.clientY - drag.y) * 0.006));
    drag = { x: e.clientX, y: e.clientY };
  }
});
canvas.addEventListener("pointerup", () => (drag = null));
canvas.addEventListener("pointercancel", () => (drag = null));
canvas.addEventListener(
  "wheel",
  (e) => {
    e.preventDefault();
    zoom = Math.max(0.6, Math.min(2, zoom * Math.exp(-e.deltaY * 0.001)));
  },
  { passive: false },
);
function draw() {
  const rect = canvas.getBoundingClientRect(),
    dpr = window.devicePixelRatio || 1,
    w = rect.width,
    h = rect.height;
  if (
    canvas.width !== Math.round(w * dpr) ||
    canvas.height !== Math.round(h * dpr)
  ) {
    canvas.width = Math.round(w * dpr);
    canvas.height = Math.round(h * dpr);
  }
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, w, h);
  if (!data) {
    ctx.fillStyle = "#8da0aa";
    ctx.font = "13px Segoe UI";
    ctx.textAlign = "center";
    ctx.fillText("Waiting for the tracking session…", w / 2, h / 2);
    requestAnimationFrame(draw);
    return;
  }
  const lo = data.config.workspace.minimum,
    hi = data.config.workspace.maximum,
    mid = { x: (lo.x + hi.x) / 2, y: (lo.y + hi.y) / 2, z: (lo.z + hi.z) / 2 },
    extent = Math.max(hi.x - lo.x, hi.y - lo.y, hi.z - lo.z, 0.1),
    scale = ((Math.min(w, h) * 0.58) / extent) * zoom;
  function project(p) {
    const x = p.x - mid.x,
      y = p.y - mid.y,
      z = p.z - mid.z;
    const a = Math.cos(yaw) * x - Math.sin(yaw) * y,
      b = Math.sin(yaw) * x + Math.cos(yaw) * y;
    return [
      w / 2 + a * scale,
      h * 0.5 + (Math.sin(pitch) * b - Math.cos(pitch) * z) * scale,
    ];
  }
  function line(a, b, color, width = 1, dash = []) {
    const pa = project(a),
      pb = project(b);
    ctx.beginPath();
    ctx.strokeStyle = color;
    ctx.lineWidth = width;
    ctx.setLineDash(dash);
    ctx.moveTo(...pa);
    ctx.lineTo(...pb);
    ctx.stroke();
    ctx.setLineDash([]);
  }
  for (let i = 0; i <= 10; i++) {
    const f = i / 10;
    line(
      { x: lo.x + (hi.x - lo.x) * f, y: lo.y, z: lo.z },
      { x: lo.x + (hi.x - lo.x) * f, y: hi.y, z: lo.z },
      "#dde7e9",
    );
    line(
      { x: lo.x, y: lo.y + (hi.y - lo.y) * f, z: lo.z },
      { x: hi.x, y: lo.y + (hi.y - lo.y) * f, z: lo.z },
      "#dde7e9",
    );
  }
  const corners = [];
  for (const x of [lo.x, hi.x])
    for (const y of [lo.y, hi.y])
      for (const z of [lo.z, hi.z]) corners.push({ x, y, z });
  for (let i = 0; i < 8; i++)
    for (const bit of [1, 2, 4])
      if ((i ^ bit) > i)
        line(corners[i], corners[i ^ bit], "#cad9de", 1, [3, 4]);
  for (let i = 1; i < trail.length; i++)
    line(trail[i - 1], trail[i], "#9dc9b9", 2);
  const p = data.robot.pose.position,
    ground = { x: p.x, y: p.y, z: lo.z };
  line(ground, p, "#b7ccc4", 1, [4, 4]);
  const [sx, sy] = project(p);
  ctx.beginPath();
  ctx.arc(sx, sy, 18, 0, Math.PI * 2);
  ctx.fillStyle = online ? "#d5eae380" : "#dde3e780";
  ctx.fill();
  ctx.beginPath();
  ctx.arc(sx, sy, 7, 0, Math.PI * 2);
  ctx.fillStyle =
    data.state === "active"
      ? "#177d67"
      : data.state === "clutched"
        ? "#ba8a35"
        : "#7d969f";
  ctx.fill();
  ctx.strokeStyle = "#fff";
  ctx.lineWidth = 2;
  ctx.stroke();
  const length = extent * 0.13,
    q = data.robot.pose.orientation;
  function rot(v) {
    const u = { x: q.x, y: q.y, z: q.z },
      uv = {
        x: u.y * v.z - u.z * v.y,
        y: u.z * v.x - u.x * v.z,
        z: u.x * v.y - u.y * v.x,
      },
      uuv = {
        x: u.y * uv.z - u.z * uv.y,
        y: u.z * uv.x - u.x * uv.z,
        z: u.x * uv.y - u.y * uv.x,
      };
    return {
      x: p.x + v.x + 2 * (q.w * uv.x + uuv.x),
      y: p.y + v.y + 2 * (q.w * uv.y + uuv.y),
      z: p.z + v.z + 2 * (q.w * uv.z + uuv.z),
    };
  }
  for (const [v, color] of [
    [{ x: length, y: 0, z: 0 }, "#c8746f"],
    [{ x: 0, y: length, z: 0 }, "#5f9e86"],
    [{ x: 0, y: 0, z: length }, "#608bb2"],
  ])
    line(p, rot(v), color, 2);
  const origin = { ...lo };
  for (const [a, color] of [
    ["x", "#b57875"],
    ["y", "#5d9681"],
    ["z", "#678ba5"],
  ]) {
    const endpoint = { ...origin, [a]: lo[a] + extent * 0.18 };
    line(origin, endpoint, color, 2);
    const screen = project(endpoint);
    ctx.fillStyle = color;
    ctx.font = "11px Segoe UI";
    ctx.textAlign = "center";
    ctx.fillText(a.toUpperCase(), screen[0], screen[1] - 8);
  }
  requestAnimationFrame(draw);
}
$("arm").addEventListener("click", () => action("arm"));
$("clutch").addEventListener("click", toggleClutch);
$("disarm").addEventListener("click", () => action("disarm"));
$("reconnect").addEventListener("click", () => action("reconnect"));
poll();
setInterval(poll, 50);
requestAnimationFrame(draw);
