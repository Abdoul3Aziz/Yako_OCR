(() => {
  const SCHEMAS = {
    cni: [
      "document_type",
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
      "document_type",
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
    cmu: [
      "document_type",
      "numero_securite_sociale",
      "nom",
      "prenoms",
      "date_naissance",
      "date_emission",
    ],
    permis: [
      "document_type",
      "numero_permis",
      "nom",
      "prenoms",
      "date_naissance",
      "lieu_naissance",
      "date_delivrance",
      "lieu_delivrance",
      "groupe_sanguin",
    ],
  };

  const FIELD_LABELS = {
    document_type: "Type de document",
    numero: "Numéro",
    numero_securite_sociale: "Numéro de sécurité sociale",
    numero_permis: "Numéro du permis",
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
    date_delivrance: "Date de délivrance",
    lieu_emission: "Lieu d'émission",
    lieu_delivrance: "Lieu de délivrance",
    groupe_sanguin: "Groupe sanguin",
    adresse: "Adresse",
  };

  const form = document.getElementById("ocrForm");
  const apiBaseInput = document.getElementById("apiBase");
  const statusEl = document.getElementById("status");
  const submitBtn = document.getElementById("submitBtn");
  const resetBtn = document.getElementById("resetBtn");
  const copyBtn = document.getElementById("copyBtn");
  const fieldsGrid = document.getElementById("fieldsGrid");
  const documentAssets = document.getElementById("documentAssets");
  const assetsGrid = document.getElementById("assetsGrid");
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
  const cameraFrame = document.getElementById("cameraFrame");
  const cameraGuide = document.getElementById("cameraGuide");

  let documentType = null;
  let lastResult = null;
  let cameraSide = null;
  let cameraStream = null;
  let facingMode = "environment";

  const analysisCanvas = document.createElement("canvas");
  let alignRafId = null;
  let lastAnalysisAt = 0;
  let isCapturing = false;

  // Toujours l'origine courante (local ou Render)
  apiBaseInput.value = window.location.origin;

  function setStatus(message, kind = "") {
    statusEl.textContent = message || "";
    statusEl.classList.remove("is-error", "is-ok");
    if (kind) statusEl.classList.add(kind);
  }

  function buildEmptyFields() {
    const keys = SCHEMAS[documentType] || [];
    fieldsGrid.innerHTML = "";

    if (!keys.length) {
      const message = document.createElement("p");
      message.className = "empty-result";
      message.textContent =
        "Le type du document et ses informations apparaîtront après l’analyse.";
      fieldsGrid.appendChild(message);
    }

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
      input.readOnly = key === "document_type";
      input.addEventListener("input", syncJsonFromInputs);

      row.append(k, input);
      fieldsGrid.appendChild(row);
    });

    lastResult = null;
    jsonOut.textContent = "{}";
    assetsGrid.innerHTML = "";
    documentAssets.hidden = true;
  }

  function collectFormData() {
    const data = { document_type: documentType };
    fieldsGrid.querySelectorAll(".field-input").forEach((input) => {
      const value = input.value.trim();
      data[input.name] =
        input.name === "document_type" ? value.toLowerCase() || null : value || null;
    });
    return data;
  }

  function syncJsonFromInputs() {
    const data = collectFormData();
    lastResult = data;
    jsonOut.textContent = JSON.stringify(data, null, 2);
  }

  function renderDocumentAssets(data) {
    assetsGrid.innerHTML = "";
    const labels = { photo: "Photo", signature: "Signature" };

    ["photo", "signature"].forEach((key) => {
      const asset = data[key];
      if (!asset?.base64 || !asset?.content_type) return;

      const figure = document.createElement("figure");
      figure.className = `asset-card asset-${key}`;
      const image = document.createElement("img");
      image.src = `data:${asset.content_type};base64,${asset.base64}`;
      image.alt = `${labels[key]} extraite du document`;
      const caption = document.createElement("figcaption");
      caption.textContent = labels[key];
      figure.append(image, caption);
      assetsGrid.appendChild(figure);
    });

    documentAssets.hidden = assetsGrid.children.length === 0;
  }

  function fillFields(data) {
    if (SCHEMAS[data.document_type]) {
      documentType = data.document_type;
      buildEmptyFields();
    }

    const missing = new Set(data.champs_manquants || []);
    lastResult = data;

    fieldsGrid.querySelectorAll(".field").forEach((row) => {
      const key = row.dataset.key;
      const input = row.querySelector(".field-input");
      if (!input) return;

      const value = data[key];
      input.value =
        value === null || value === undefined
          ? ""
          : key === "document_type"
            ? String(value).toUpperCase()
            : String(value);

      const empty = !input.value;
      row.classList.toggle("is-missing", missing.has(key) || empty);
      row.classList.toggle("is-filled", !empty);
    });

    renderDocumentAssets(data);
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

  async function optimizeCameraPhoto(file) {
    if (!file?.type?.startsWith("image/") || !window.createImageBitmap) {
      return file;
    }

    let bitmap;
    try {
      try {
        bitmap = await createImageBitmap(file, { imageOrientation: "from-image" });
      } catch {
        bitmap = await createImageBitmap(file);
      }

      const maxSide = 2200;
      const longest = Math.max(bitmap.width, bitmap.height);
      if (longest <= maxSide && file.size <= 2_500_000) {
        return file;
      }

      const scale = Math.min(1, maxSide / longest);
      const width = Math.round(bitmap.width * scale);
      const height = Math.round(bitmap.height * scale);
      const canvas = document.createElement("canvas");
      canvas.width = width;
      canvas.height = height;
      const ctx = canvas.getContext("2d");
      ctx.imageSmoothingEnabled = true;
      ctx.imageSmoothingQuality = "high";
      ctx.drawImage(bitmap, 0, 0, width, height);

      const blob = await new Promise((resolve) =>
        canvas.toBlob(resolve, "image/jpeg", 0.9)
      );
      if (!blob) return file;
      return new File([blob], file.name.replace(/\.[^.]+$/, "") + ".jpg", {
        type: "image/jpeg",
        lastModified: Date.now(),
      });
    } catch {
      return file;
    } finally {
      bitmap?.close?.();
    }
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

    target.cameraNative.addEventListener("change", async () => {
      const file = target.cameraNative.files?.[0];
      if (!file) return;
      setStatus("Optimisation de la photo…");
      const optimized = await optimizeCameraPhoto(file);
      applyFileToSide(side, optimized);
      setStatus(`Photo ${side} prête.`, "is-ok");
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
    stopAlignmentLoop();
    if (cameraStream) {
      cameraStream.getTracks().forEach((track) => track.stop());
      cameraStream = null;
    }
    cameraVideo.srcObject = null;
  }

  function isMobileDevice() {
    return (
      /Android|iPhone|iPad|iPod|Mobile/i.test(navigator.userAgent) ||
      (navigator.maxTouchPoints > 1 && window.matchMedia("(max-width: 900px)").matches)
    );
  }

  async function startCamera() {
    await stopCamera();
    cameraStream = await navigator.mediaDevices.getUserMedia({
      audio: false,
      video: {
        facingMode: { ideal: facingMode },
        width: { ideal: 3840 },
        height: { ideal: 2160 },
      },
    });
    cameraVideo.srcObject = cameraStream;
    await cameraVideo.play();
    isCapturing = false;
    setFramingState("place");
    startAlignmentLoop();
  }

  async function openCameraModal(side) {
    // Caméra intégrée guidée (cadre rouge/vert), y compris sur mobile.
    cameraSide = side;
    cameraTitle.textContent = `Photo — ${side === "recto" ? "Recto" : "Verso"}`;
    cameraModal.hidden = false;
    setFramingState("place");

    try {
      await startCamera();
    } catch (err) {
      await closeCameraModal();
      sides[side].cameraNative.click();
      setStatus(
        `Caméra web indisponible (${err?.name || "erreur"}) — ouverture de l’appareil photo du téléphone.`,
        "is-error"
      );
    }
  }

  async function closeCameraModal() {
    cameraModal.hidden = true;
    cameraSide = null;
    await stopCamera();
  }

  // Zone du cadre-guide ramenée aux pixels réels de la vidéo (object-fit: cover)
  function getGuideSampleRect() {
    const vW = cameraVideo.videoWidth;
    const vH = cameraVideo.videoHeight;
    if (!vW || !vH) return null;

    const vRect = cameraVideo.getBoundingClientRect();
    const fRect = cameraFrame.getBoundingClientRect();
    if (!vRect.width || !vRect.height) return null;

    const scale = Math.max(vRect.width / vW, vRect.height / vH);
    const dispW = vW * scale;
    const dispH = vH * scale;
    const offX = (dispW - vRect.width) / 2;
    const offY = (dispH - vRect.height) / 2;

    const sx = (fRect.left - vRect.left + offX) / scale;
    const sy = (fRect.top - vRect.top + offY) / scale;
    const sw = fRect.width / scale;
    const sh = fRect.height / scale;
    return { sx, sy, sw, sh };
  }

  // Analyse le cadrage et la netteté. Renvoie un statut :
  //  - "place" : document absent / mal positionné dans le cadre
  //  - "blur"  : document bien cadré mais flou
  //  - "ready" : document bien cadré et net -> capture autorisée
  function evaluateFraming() {
    const rect = getGuideSampleRect();
    if (!rect) return "place";

    const aw = 200;
    const ah = Math.max(60, Math.round(aw * (rect.sh / rect.sw)));
    analysisCanvas.width = aw;
    analysisCanvas.height = ah;
    const ctx = analysisCanvas.getContext("2d", { willReadFrequently: true });

    try {
      ctx.drawImage(
        cameraVideo,
        rect.sx,
        rect.sy,
        rect.sw,
        rect.sh,
        0,
        0,
        aw,
        ah
      );
    } catch {
      return "place";
    }

    let data;
    try {
      data = ctx.getImageData(0, 0, aw, ah).data;
    } catch {
      return "place";
    }

    const gray = new Float32Array(aw * ah);
    let brightSum = 0;
    let brightCount = 0;
    for (let i = 0, p = 0; i < gray.length; i++, p += 4) {
      const v = 0.299 * data[p] + 0.587 * data[p + 1] + 0.114 * data[p + 2];
      gray[i] = v;
      brightSum += v;
      if (v > 110) brightCount++;
    }
    const brightness = brightSum / gray.length;
    const brightFraction = brightCount / gray.length;

    // Un document (papier/carte) remplit le cadre de zones claires : on rejette
    // les scènes sombres/vides (main, bureau, vide).
    if (brightness < 95 || brightness > 245 || brightFraction < 0.5) {
      return "place";
    }

    // Gradient (bords) + variance du Laplacien (netteté)
    const band = Math.round(Math.min(aw, ah) * 0.14);
    let total = 0;
    let count = 0;
    let lapSum = 0;
    let lapSqSum = 0;
    let lapCount = 0;
    const bands = { top: 0, bottom: 0, left: 0, right: 0 };
    const bandCount = { top: 0, bottom: 0, left: 0, right: 0 };

    for (let y = 1; y < ah - 1; y++) {
      for (let x = 1; x < aw - 1; x++) {
        const idx = y * aw + x;
        const gx = gray[idx + 1] - gray[idx - 1];
        const gy = gray[idx + aw] - gray[idx - aw];
        const mag = Math.abs(gx) + Math.abs(gy);
        total += mag;
        count++;

        const lap =
          4 * gray[idx] -
          gray[idx - 1] -
          gray[idx + 1] -
          gray[idx - aw] -
          gray[idx + aw];
        lapSum += lap;
        lapSqSum += lap * lap;
        lapCount++;

        if (y < band) {
          bands.top += mag;
          bandCount.top++;
        }
        if (y >= ah - band) {
          bands.bottom += mag;
          bandCount.bottom++;
        }
        if (x < band) {
          bands.left += mag;
          bandCount.left++;
        }
        if (x >= aw - band) {
          bands.right += mag;
          bandCount.right++;
        }
      }
    }

    const meanGrad = total / Math.max(1, count);
    const sides = ["top", "bottom", "left", "right"];
    const bordersCovered = sides.every((s) => {
      const m = bands[s] / Math.max(1, bandCount[s]);
      return m >= 8 && m >= meanGrad * 0.45;
    });

    if (!bordersCovered) return "place";

    // Variance du Laplacien : faible = image floue
    const lapMean = lapSum / Math.max(1, lapCount);
    const lapVar = lapSqSum / Math.max(1, lapCount) - lapMean * lapMean;
    const SHARP_THRESHOLD = 130;
    if (lapVar < SHARP_THRESHOLD) return "blur";

    return "ready";
  }

  function setFramingState(status) {
    const ready = status === "ready";
    const blur = status === "blur";
    cameraFrame.classList.toggle("is-good", ready);
    cameraFrame.classList.toggle("is-blur", blur);
    cameraGuide.classList.toggle("is-good", ready);
    cameraGuide.classList.toggle("is-blur", blur);
    cameraGuide.textContent = ready
      ? "Document net — appuyez sur Capturer"
      : blur
        ? "Image floue — stabilisez l’appareil"
        : "Placez le document dans le cadre";
    cameraCapture.disabled = !ready;
  }

  function stopAlignmentLoop() {
    if (alignRafId) {
      cancelAnimationFrame(alignRafId);
      alignRafId = null;
    }
  }

  function startAlignmentLoop() {
    stopAlignmentLoop();
    const tick = (ts) => {
      alignRafId = requestAnimationFrame(tick);
      if (isCapturing) return;
      if (ts - lastAnalysisAt < 160) return;
      lastAnalysisAt = ts;

      // Guide visuel + activation du bouton uniquement si net et bien cadré.
      // La capture reste manuelle (pas de déclenchement automatique).
      setFramingState(evaluateFraming());
    };
    alignRafId = requestAnimationFrame(tick);
  }

  function capturePhoto() {
    if (!cameraSide || !cameraStream || isCapturing) return;
    if (cameraCapture.disabled) {
      setStatus("Cadrez le document et attendez qu’il soit net.", "");
      return;
    }
    isCapturing = true;
    stopAlignmentLoop();

    const vW = cameraVideo.videoWidth || 1280;
    const vH = cameraVideo.videoHeight || 720;

    // On ne conserve que l'intérieur du cadre-guide (+ petite marge de sécurité)
    // pour exclure l'arrière-plan situé hors du cadre.
    let sx = 0;
    let sy = 0;
    let sw = vW;
    let sh = vH;
    const rect = getGuideSampleRect();
    if (rect) {
      sx = Math.max(0, Math.round(rect.sx));
      sy = Math.max(0, Math.round(rect.sy));
      sw = Math.min(vW - sx, Math.round(rect.sw));
      sh = Math.min(vH - sy, Math.round(rect.sh));
      if (sw <= 0 || sh <= 0) {
        sx = 0;
        sy = 0;
        sw = vW;
        sh = vH;
      }
    }

    cameraCanvas.width = sw;
    cameraCanvas.height = sh;
    const ctx = cameraCanvas.getContext("2d");
    ctx.imageSmoothingEnabled = true;
    ctx.imageSmoothingQuality = "high";
    ctx.drawImage(cameraVideo, sx, sy, sw, sh, 0, 0, sw, sh);

    cameraCanvas.toBlob(
      async (blob) => {
        if (!blob) {
          isCapturing = false;
          setStatus("Échec de la capture photo.", "is-error");
          startAlignmentLoop();
          return;
        }
        const file = new File(
          [blob],
          `${cameraSide}-${Date.now()}.jpg`,
          { type: "image/jpeg" }
        );
        const optimized = await optimizeCameraPhoto(file);
        applyFileToSide(cameraSide, optimized);
        setStatus(`Photo ${cameraSide} capturée.`, "is-ok");
        closeCameraModal();
      },
      "image/jpeg",
      0.95
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
          const insecure = window.isSecureContext === false;
          setStatus(
            insecure
              ? "Caméra guidée indisponible : la page doit être ouverte en HTTPS. Utilisation de l’appareil photo du téléphone."
              : "Caméra guidée non prise en charge par ce navigateur. Utilisation de l’appareil photo du téléphone.",
            "is-error"
          );
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

  resetBtn.addEventListener("click", () => {
    form.reset();
    clearSide("recto");
    clearSide("verso");
    documentType = null;
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
    const url = `${base}/ocr/document`;

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
      const detectedLabel =
        {
          cni: "CNI",
          passeport: "Passeport",
          cmu: "CMU",
          permis: "Permis de conduire",
        }[payload.document_type] || "Document";
      setStatus(
        missing
          ? `${detectedLabel} détecté — ${missing} champ(s) manquant(s).`
          : `${detectedLabel} détecté — extraction terminée avec succès.`,
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
