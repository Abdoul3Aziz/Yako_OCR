(() => {
  const SCHEMAS = {
    cni: [
      "numero",
      "nom",
      "prenoms",
      "date_naissance",
      "sexe",
      "taille",
      "nationalite",
      "lieu_naissance",
      "date_expiration",
      "nni",
      "profession",
      "date_emission",
      "lieu_emission",
    ],
    passeport: [
      "numero",
      "nom",
      "prenoms",
      "nationalite",
      "date_naissance",
      "date_expiration",
      "sexe",
      "lieu_naissance",
      "profession",
      "adresse",
      "taille",
    ],
  };

  const FIELD_LABELS = {
    numero: "Numéro",
    nom: "Nom",
    prenoms: "Prénoms",
    nationalite: "Nationalité",
    date_naissance: "Date de naissance",
    date_expiration: "Date d'expiration",
    sexe: "Sexe",
    taille: "Taille",
    lieu_naissance: "Lieu de naissance",
    nni: "NNI",
    profession: "Profession",
    date_emission: "Date d'émission",
    lieu_emission: "Lieu d'émission",
    adresse: "Adresse",
  };

  const form = document.getElementById("ocrForm");
  const apiBaseInput = document.getElementById("apiBase");
  const statusEl = document.getElementById("status");
  const submitBtn = document.getElementById("submitBtn");
  const resetBtn = document.getElementById("resetBtn");
  const copyBtn = document.getElementById("copyBtn");
  const fieldsGrid = document.getElementById("fieldsGrid");
  const jsonOut = document.getElementById("jsonOut");

  const sides = {
    recto: {
      input: document.getElementById("rectoInput"),
      cameraNative: document.getElementById("rectoCameraNative"),
      preview: document.getElementById("rectoPreview"),
      hint: document.getElementById("rectoHint"),
      zone: document.querySelector('.dropzone[data-side="recto"]'),
    },
    verso: {
      input: document.getElementById("versoInput"),
      cameraNative: document.getElementById("versoCameraNative"),
      preview: document.getElementById("versoPreview"),
      hint: document.getElementById("versoHint"),
      zone: document.querySelector('.dropzone[data-side="verso"]'),
    },
  };

  const cameraModal = document.getElementById("cameraModal");
  const cameraVideo = document.getElementById("cameraVideo");
  const cameraCanvas = document.getElementById("cameraCanvas");
  const cameraClose = document.getElementById("cameraClose");
  const cameraCapture = document.getElementById("cameraCapture");
  const cameraSwitch = document.getElementById("cameraSwitch");
  const cameraTitle = document.getElementById("cameraTitle");

  let documentType = "cni";
  let lastResult = null;
  let cameraSide = null;
  let cameraStream = null;
  let facingMode = "environment";

  // Toujours l'origine courante (local ou Render)
  apiBaseInput.value = window.location.origin;

  function setStatus(message, kind = "") {
    statusEl.textContent = message || "";
    statusEl.classList.remove("is-error", "is-ok");
    if (kind) statusEl.classList.add(kind);
  }

  function buildEmptyFields() {
    const keys = SCHEMAS[documentType] || SCHEMAS.cni;
    fieldsGrid.innerHTML = "";

    keys.forEach((key, index) => {
      const row = document.createElement("label");
      row.className = "field";
      row.style.animationDelay = `${Math.min(index, 12) * 0.03}s`;
      row.dataset.key = key;

      const k = document.createElement("span");
      k.className = "field-key";
      k.textContent = FIELD_LABELS[key] || key;

      const input = document.createElement("input");
      input.className = "field-input";
      input.type = "text";
      input.name = key;
      input.id = `field-${key}`;
      input.value = "";
      input.placeholder = "—";
      input.autocomplete = "off";
      input.addEventListener("input", syncJsonFromInputs);

      row.append(k, input);
      fieldsGrid.appendChild(row);
    });

    lastResult = null;
    jsonOut.textContent = "{}";
  }

  function collectFormData() {
    const data = { document_type: documentType };
    fieldsGrid.querySelectorAll(".field-input").forEach((input) => {
      const value = input.value.trim();
      data[input.name] = value || null;
    });
    return data;
  }

  function syncJsonFromInputs() {
    const data = collectFormData();
    lastResult = data;
    jsonOut.textContent = JSON.stringify(data, null, 2);
  }

  function fillFields(data) {
    const missing = new Set(data.champs_manquants || []);
    lastResult = data;

    fieldsGrid.querySelectorAll(".field").forEach((row) => {
      const key = row.dataset.key;
      const input = row.querySelector(".field-input");
      if (!input) return;

      const value = data[key];
      input.value = value === null || value === undefined ? "" : String(value);

      const empty = !input.value;
      row.classList.toggle("is-missing", missing.has(key) || empty);
      row.classList.toggle("is-filled", !empty);
    });

    jsonOut.textContent = JSON.stringify(data, null, 2);
  }

  function resetFields() {
    buildEmptyFields();
    fieldsGrid.querySelectorAll(".field").forEach((row) => {
      row.classList.remove("is-missing", "is-filled");
    });
  }

  function applyFileToSide(side, file) {
    const target = sides[side];
    if (!target || !file) return;

    const dt = new DataTransfer();
    dt.items.add(file);
    target.input.files = dt.files;

    const url = URL.createObjectURL(file);
    target.preview.src = url;
    target.preview.hidden = false;
    target.hint.textContent = file.name || "Photo capturée";
    target.zone.classList.add("has-file");
  }

  function clearSide(side) {
    const target = sides[side];
    target.input.value = "";
    target.cameraNative.value = "";
    target.preview.hidden = true;
    target.preview.removeAttribute("src");
    target.hint.textContent = "Fichier ou photo";
    target.zone.classList.remove("has-file");
  }

  function bindSide(side) {
    const target = sides[side];

    target.input.addEventListener("change", () => {
      const file = target.input.files?.[0];
      if (!file) {
        clearSide(side);
        return;
      }
      applyFileToSide(side, file);
    });

    target.cameraNative.addEventListener("change", () => {
      const file = target.cameraNative.files?.[0];
      if (!file) return;
      applyFileToSide(side, file);
    });

    target.zone.addEventListener("dragover", (e) => {
      e.preventDefault();
      target.zone.classList.add("is-dragover");
    });
    target.zone.addEventListener("dragleave", () => {
      target.zone.classList.remove("is-dragover");
    });
    target.zone.addEventListener("drop", (e) => {
      e.preventDefault();
      target.zone.classList.remove("is-dragover");
      const file = e.dataTransfer?.files?.[0];
      if (file && file.type.startsWith("image/")) {
        applyFileToSide(side, file);
      }
    });
  }

  bindSide("recto");
  bindSide("verso");

  async function stopCamera() {
    if (cameraStream) {
      cameraStream.getTracks().forEach((track) => track.stop());
      cameraStream = null;
    }
    cameraVideo.srcObject = null;
  }

  async function startCamera() {
    await stopCamera();
    cameraStream = await navigator.mediaDevices.getUserMedia({
      audio: false,
      video: {
        facingMode: { ideal: facingMode },
        width: { ideal: 1920 },
        height: { ideal: 1080 },
      },
    });
    cameraVideo.srcObject = cameraStream;
    await cameraVideo.play();
  }

  async function openCameraModal(side) {
    cameraSide = side;
    cameraTitle.textContent = `Photo — ${side === "recto" ? "Recto" : "Verso"}`;
    cameraModal.hidden = false;

    try {
      await startCamera();
    } catch (err) {
      await closeCameraModal();
      // Fallback mobile / navigateurs sans getUserMedia fiable
      sides[side].cameraNative.click();
      setStatus(
        "Caméra web indisponible — ouverture de l’appareil photo du téléphone.",
        ""
      );
    }
  }

  async function closeCameraModal() {
    cameraModal.hidden = true;
    cameraSide = null;
    await stopCamera();
  }

  function capturePhoto() {
    if (!cameraSide || !cameraStream) return;

    const width = cameraVideo.videoWidth || 1280;
    const height = cameraVideo.videoHeight || 720;
    cameraCanvas.width = width;
    cameraCanvas.height = height;
    const ctx = cameraCanvas.getContext("2d");
    ctx.drawImage(cameraVideo, 0, 0, width, height);

    cameraCanvas.toBlob(
      (blob) => {
        if (!blob) {
          setStatus("Échec de la capture photo.", "is-error");
          return;
        }
        const file = new File(
          [blob],
          `${cameraSide}-${Date.now()}.jpg`,
          { type: "image/jpeg" }
        );
        applyFileToSide(cameraSide, file);
        setStatus(`Photo ${cameraSide} capturée.`, "is-ok");
        closeCameraModal();
      },
      "image/jpeg",
      0.92
    );
  }

  document.querySelectorAll(".btn-source").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation();
      const side = btn.dataset.side;
      const action = btn.dataset.action;
      if (action === "file") {
        sides[side].input.click();
      } else if (action === "camera") {
        if (!navigator.mediaDevices?.getUserMedia) {
          sides[side].cameraNative.click();
          return;
        }
        openCameraModal(side);
      }
    });
  });

  cameraClose.addEventListener("click", () => closeCameraModal());
  cameraCapture.addEventListener("click", () => capturePhoto());
  cameraSwitch.addEventListener("click", async () => {
    facingMode = facingMode === "environment" ? "user" : "environment";
    try {
      await startCamera();
    } catch {
      setStatus("Impossible de basculer la caméra.", "is-error");
    }
  });

  cameraModal.addEventListener("click", (e) => {
    if (e.target === cameraModal) closeCameraModal();
  });

  document.querySelectorAll(".doc-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".doc-btn").forEach((b) => {
        b.classList.toggle("is-active", b === btn);
        b.setAttribute("aria-selected", b === btn ? "true" : "false");
      });
      documentType = btn.dataset.type;
      resetFields();
      setStatus(`Type sélectionné : ${documentType === "cni" ? "CNI" : "Passeport"}`);
    });
  });

  resetBtn.addEventListener("click", () => {
    form.reset();
    clearSide("recto");
    clearSide("verso");
    resetFields();
    setStatus("Formulaire réinitialisé.");
  });

  copyBtn.addEventListener("click", async () => {
    const payload = lastResult || collectFormData();
    try {
      await navigator.clipboard.writeText(JSON.stringify(payload, null, 2));
      setStatus("JSON copié dans le presse-papiers.", "is-ok");
    } catch {
      setStatus("Impossible de copier le JSON.", "is-error");
    }
  });

  form.addEventListener("submit", async (e) => {
    e.preventDefault();

    const recto = sides.recto.input.files?.[0];
    const verso = sides.verso.input.files?.[0];
    if (!recto || !verso) {
      setStatus("Ajoutez le recto et le verso (fichier ou photo).", "is-error");
      return;
    }

    const base = (apiBaseInput.value || window.location.origin).replace(/\/$/, "");
    const endpoint = documentType === "cni" ? "/ocr/cni" : "/ocr/passeport";
    const url = `${base}${endpoint}`;

    const body = new FormData();
    body.append("recto", recto);
    body.append("verso", verso);

    submitBtn.disabled = true;
    setStatus("Analyse OCR en cours… cela peut prendre quelques secondes.");

    try {
      const response = await fetch(url, {
        method: "POST",
        body,
      });

      let payload;
      try {
        payload = await response.json();
      } catch {
        throw new Error("Réponse non JSON de l'API.");
      }

      if (!response.ok) {
        const detail =
          typeof payload.detail === "string"
            ? payload.detail
            : JSON.stringify(payload.detail || payload);
        throw new Error(detail || `Erreur HTTP ${response.status}`);
      }

      fillFields(payload);
      const missing = payload.champs_manquants?.length || 0;
      setStatus(
        missing
          ? `Extraction terminée — ${missing} champ(s) manquant(s).`
          : "Extraction terminée avec succès.",
        missing ? "" : "is-ok"
      );
    } catch (err) {
      setStatus(err.message || "Échec de la requête.", "is-error");
    } finally {
      submitBtn.disabled = false;
    }
  });

  buildEmptyFields();
})();
