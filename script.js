const API_BASE = "http://localhost:8000";

const up = document.getElementById("up");
const result = document.getElementById("result");
const statusEl = document.getElementById("status");
const fileInput = document.getElementById("fileInput");
const sendBtn = document.getElementById("sendBtn");

const ok = document.getElementById("ok");
const nameEl = document.getElementById("name");
const strengthEl = document.getElementById("strength");
const whatForEl = document.getElementById("whatFor");
const warnEl = document.getElementById("warn");
const useCasesEl = document.getElementById("useCases");
const again = document.getElementById("again");

// cámara
const openCam = document.getElementById("openCam");
const camBox = document.getElementById("camBox");
const video = document.getElementById("cam");
const snap = document.getElementById("snap");
const closeCam = document.getElementById("closeCam");
const canvas = document.getElementById("canvas");

let stream = null;
let capturedBlob = null; // si existe, se usa en vez del fileInput

function view(v){ [up,result].forEach(x=>x.classList.remove("active")); (v==="result"?result:up).classList.add("active"); }

// --- FUNCIÓN MODIFICADA ---
function status(t, type = 'info'){
  statusEl.textContent = t || "";
  statusEl.classList.remove('confirm');
  
  if(t){
    statusEl.classList.add("visible");
    if (type === 'confirm') {
        statusEl.classList.add('confirm');
    }
  } else {
    statusEl.classList.remove("visible");
  }
}

// --- NUEVO EVENT LISTENER ---
// Muestra confirmación cuando se selecciona un archivo.
fileInput.addEventListener("change", () => {
    if (fileInput.files && fileInput.files.length > 0) {
        const fileName = fileInput.files[0].name;
        status(`✅ Imagen seleccionada: ${fileName}`, 'confirm');
        capturedBlob = null; // Invalida la foto de la cámara si se elige un archivo
        if (stream) closeCam.click(); // Cierra la cámara si está abierta
    }
});


openCam.addEventListener("click", async ()=>{
  try{
    stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment" }, audio: false });
    video.srcObject = stream;
    camBox.hidden = false;
    capturedBlob = null;
    status(""); // Limpia cualquier estado anterior
  }catch(e){
    alert("No se pudo abrir la cámara.");
  }
});

closeCam.addEventListener("click", ()=>{
  if(stream){ stream.getTracks().forEach(t=>t.stop()); stream = null; }
  camBox.hidden = true;
});

snap.addEventListener("click", ()=>{
  if(!video.videoWidth){ alert("Cámara aún no lista."); return; }
  const w = video.videoWidth, h = video.videoHeight;
  canvas.width = w; canvas.height = h;
  const ctx = canvas.getContext("2d");
  ctx.drawImage(video, 0, 0, w, h);
  canvas.toBlob(b=>{
    capturedBlob = b;
    fileInput.value = ""; // Invalida el archivo si se toma foto
    status("📸 Foto capturada. Lista para analizar.", 'confirm'); // Usa la nueva función de estado
    closeCam.click(); // Cierra la cámara después de tomar la foto
  }, "image/jpeg", 0.92);
});

sendBtn.addEventListener("click", async ()=>{
  let blob = null;
  // prioriza foto capturada
  if(capturedBlob){
    blob = capturedBlob;
  }else{
    const f = fileInput.files?.[0];
    if(!f){ alert("Selecciona una imagen o usa la cámara."); return; }
    blob = f;
  }

  status("Analizando imagen con Vision..."); 
  const fd = new FormData(); fd.append("image", blob, "photo.jpg");
  try{
    const r = await fetch(`${API_BASE}/analyze`, { method:"POST", body: fd });
    let errText = `HTTP ${r.status}`;
    if(!r.ok){
      try{ const j = await r.json(); errText = j?.detail || errText; }catch{}
      throw new Error(errText);
    }
    const j = await r.json();
    render(j.info);
  }catch(e){
    console.error(e);
    alert(e.message || "Error al analizar la imagen.");
  }finally{
    status("");
  }
});

function render(info){
  view("result");
  ok.style.display = "block";
  nameEl.textContent = info?.name || "—";
  strengthEl.textContent = info?.strength || "";
  whatForEl.textContent = info?.what_for || "—";
  useCasesEl.innerHTML = (info?.use_cases || []).map(x=>`<li>${x}</li>`).join("");
  warnEl.innerHTML = (info?.common_warnings || []).map(x=>`<li>${x}</li>`).join("");
}

again.addEventListener("click", ()=>{
  view("up");
  ok.style.display="none";
  fileInput.value="";
  capturedBlob = null;
  status("");
});